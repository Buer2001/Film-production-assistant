from pydantic import BaseModel, ConfigDict, Field
from backend.production.project.schemas import ChangeInput
from backend.production.service import state, propose, rows
from backend.common.database.store import Event
from backend.production.analysis import ImpactInput, analyze_impact


class Search(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = ''
    kind: str = ''
    offset: int = Field(default=0, ge=0)


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


TOOLS = {
    'search_records': ('查询当前项目事实，按标题、来源、备注、资源搜索；支持翻页。', Search),
    'check_schedule': ('检查当前正式排期的时间冲突和筹备缺口，不修改数据。', Empty),
    'search_events': ('查找项目历史事件和决策依据，不把历史当当前事实。', Search),
    'propose_change': ('生成待制片确认的修改草稿；不会正式修改项目。更新记录须提交完整字段。', ChangeInput),
    'analyze_impact': ('只读分析记录、资源或待确认草稿影响的场次、筹备、排期和通告，返回关联路径。', ImpactInput),
}


def schemas():
    return [{'type': 'function', 'function': {'name': name, 'description': desc,
            'parameters': schema.model_json_schema()}} for name, (desc, schema) in TOOLS.items()]


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
    if name == 'search_events':
        records = [{'id': e.id, 'type': e.type, 'created_at': e.created_at, 'data': e.data}
                   for e in rows(s, Event, pid) if e.type != 'chat']
    else:
        records = [r for r in state(s, pid)['records'] if not args.kind or r['kind'] == args.kind]
    found = [r for r in records if args.query.lower() in json.dumps(r, ensure_ascii=False).lower()]
    return {'items': found[args.offset:args.offset + 30], 'total': len(found), 'offset': args.offset}
