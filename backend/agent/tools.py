# 定义模型工具白名单、参数契约和业务分发，查询结果按页返回。
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from backend.schemas.change import ChangeInput
from backend.schemas.record import Item
from backend.service.project import state, rows
from backend.service.change import propose
from backend.models.event import Event
from backend.service.impact import ImpactInput, analyze_impact


# 工具搜索参数：query 为文本、kind 为记录种类，offset 非负；禁止额外字段。
class Search(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = ''
    kind: str = ''
    offset: int = Field(default=0, ge=0)


# 无参数工具的空对象契约，禁止模型提交未声明字段。
class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


# 模型修改项；使用通用 Item，避免开放人工资源落实资料。
class AgentOperation(BaseModel):
    """保留原工具写入边界：V3 人工落实字段不开放给模型，保存仍走共用业务校验。"""
    model_config = ConfigDict(extra='forbid')
    kind: Literal['scene', 'requirement', 'resource', 'task', 'schedule', 'expense', 'decision']
    id: str | None = None
    delete: bool = False
    data: Item | None = None


# 模型草稿请求，沿用项目基准版本和原因，操作限制为 1 至 50 项。
class AgentChangeInput(ChangeInput):
    operations: list[AgentOperation] = Field(min_length=1, max_length=50)


TOOLS = {
    'search_records': ('查询当前项目事实，按标题、来源、备注、资源搜索；支持翻页。', Search),
    'check_schedule': ('检查当前正式排期的时间冲突和筹备缺口，不修改数据。', Empty),
    'search_events': ('查找项目历史事件和决策依据，不把历史当当前事实。', Search),
    'propose_change': ('生成待制片确认的修改草稿；不会正式修改项目。禁止维护旧task筹备任务，任务请到项目日程操作。更新记录须提交完整字段。', AgentChangeInput),
    'analyze_impact': ('只读分析记录、资源或待确认草稿影响的场次、筹备、排期和通告，返回关联路径。', ImpactInput),
}


# 把工具白名单转为模型 function-calling 参数列表；返回各工具的 JSON Schema。
def schemas():
    return [{'type': 'function', 'function': {'name': name, 'description': desc,
            'parameters': schema.model_json_schema()}} for name, (desc, schema) in TOOLS.items()]


# 按项目 pid 校验并执行白名单 name 和 arguments；返回业务结果或分页查询，未知工具抛 ValueError，修改仅生成草稿。
def execute(s, pid, name, arguments):
    if name not in TOOLS:
        raise ValueError('工具不在允许范围')
    args = TOOLS[name][1].model_validate(arguments)
    if name == 'analyze_impact':
        return analyze_impact(s, pid, args)
    if name == 'propose_change':
        return propose(s, pid, args)
    if name == 'check_schedule':
        return state(s, pid)['checks']
    import json

    # 历史事件排除聊天内容；当前记录从项目状态取值，避免把审计历史当作当前事实。
    if name == 'search_events':
        records = [{'id': e.id, 'type': e.type, 'created_at': e.created_at, 'data': e.data}
                   for e in rows(s, Event, pid) if e.type != 'chat']
    else:
        records = [r for r in state(s, pid)['records'] if not args.kind or r['kind'] == args.kind]
    found = [r for r in records if args.query.lower() in json.dumps(r, ensure_ascii=False).lower()]
    # 固定每页 30 项并返回总数，模型可继续使用 offset 读取剩余结果。
    return {'items': found[args.offset:args.offset + 30], 'total': len(found), 'offset': args.offset}
