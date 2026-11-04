# 文件职责：读取正式任务、资源和人员供缺口检查，不读取待审日程草稿。
"""汇集本项目正式事实供纯规则检查；GET 不写入、不中途提交、不读取待审草稿。"""
from backend.dao import planning, person, resource
from backend.service.planning import require_project, task_data
from backend.tools.preparation import check_preparation


# 用途：汇集正式事实并检查筹备缺口。
# 参数：session/pid 为会话及项目 ID。
# 返回及副作用：返回 issues 及非取消任务数量；项目不存在抛 BusinessError，不写数据库。
def read(session, pid):
    require_project(session, pid)
    plan = planning.get(session, pid)
    tasks = [task_data(t) for t in planning.tasks(session, plan.id)] if plan else []
    resources = [{'id': r.id, 'data': r.data} for r in resource.list_resources(session, pid)]
    people = [{'id': p.id, 'name': p.name, 'availability': p.availability} for p in person.list_people(session, pid)]
    return {'issues': check_preparation(tasks, resources, people),
            'checked_tasks': sum(t['status'] != 'cancelled' for t in tasks)}
