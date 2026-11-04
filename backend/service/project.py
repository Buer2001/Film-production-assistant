# 文件职责：提供项目入口及概览聚合，统一项目、记录和草稿返回结构。
from decimal import Decimal
from backend.common.errors import BusinessError
from backend.models.record import Record
from backend.models.change import Change
from backend.models.notice import Notice
from backend.dao import project as dao
from backend.dao.record import rows
from backend.tools.scheduling import check_schedule
from backend.tools.notice import notice_status
from backend.dao import planning as planning_dao
from backend.tools.planning import today


# 用途：读取必须存在的项目。
# 参数：s/pid 为会话及项目 ID。
# 返回及副作用：返回项目模型，不存在抛 BusinessError(404)，不提交。
def get_project(s, pid):
    p = dao.get_project(s, pid)
    if not p:
        raise BusinessError(404, '项目不存在')
    return p


# 用途：提取通用记录接口字段。
# 参数：r 为记录模型。
# 返回及副作用：返回 id、kind、data 字典；嵌套 JSON 沿用原值。
def record_dict(r):
    return {'id': r.id, 'kind': r.kind, 'data': r.data}


# 用途：提取变更草稿接口字段。
# 参数：c 为变更模型。
# 返回及副作用：返回标识、基准版本、操作、原值、状态及创建时间字典。
def change_dict(c):
    return {k: getattr(c, k) for k in ('id', 'base_revision', 'reason', 'operations', 'before', 'status', 'created_at')}


# 用途：聚合项目概览及正式安排检查。
# 参数：s/pid 为会话及项目 ID。
# 返回及副作用：返回记录、变更、通告状态、费用合计和正式任务统计；项目不存在抛 BusinessError，不提交。
def state(s, pid):
    p = get_project(s, pid)
    plan = planning_dao.get(s, pid)
    tasks = planning_dao.tasks(s, plan.id) if plan else []
    # 概览只汇总正式任务，草稿不算已安排；取消和完成项均不再计入待办。
    active = [t for t in tasks if t.status not in ('completed', 'cancelled')]
    summary = {'total': len(tasks), 'unfinished': len(active),
               'overdue': sum(t.planned_end is not None and t.planned_end < today() for t in active)}
    records = [record_dict(r) for r in rows(s, Record, pid) if r.kind != 'script_fields']
    # 延迟导入避免项目聚合与拍摄/通告服务形成初始化循环；草稿不是已发布通告。
    from backend.service.notice import published_dict
    notices = [published_dict(s, pid, n, records) for n in rows(s, Notice, pid) if n.version > 0]
    return {'id': p.id, 'name': p.name, 'revision': p.revision, 'records': records,
            'changes': [change_dict(c) for c in rows(s, Change, pid)], 'notices': notices,
            'checks': check_schedule(records), 'planning_summary': summary,
            # 金额以 Decimal 累加并转为字符串，避免浮点误差进入概览。
            'totals': {category: str(sum((Decimal(r['data']['amount']) for r in records
                if r['kind'] == 'expense' and r['data']['category'] == category), Decimal(0)))
                for category in ('预算', '报价', '已确定', '实际支出')}}


# 用途：提取项目简要字段。
# 参数：project 为项目模型。
# 返回及副作用：返回 id、name、revision 字典。
def project_dict(project):
    return {'id': project.id, 'name': project.name, 'revision': project.revision}


# 用途：列出项目简要信息。
# 参数：s 为数据库会话。
# 返回及副作用：返回项目字典列表，不提交。
def list_projects(s):
    return [project_dict(project) for project in dao.list_projects(s)]


# 用途：创建项目并持久化。
# 参数：s 为会话，name 为项目名称。
# 返回及副作用：提交后返回项目简要字典。
def create_project(s, name):
    project = dao.add_project(s, name)
    s.commit()
    return project_dict(project)
