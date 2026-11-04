# 读写项目人员并检查正式任务、待审草稿及资源联系人引用。
"""人员 SQL 和引用查询；事务提交由业务服务统一决定。"""
from sqlalchemy import select
from backend.models.person import ProjectPerson
from backend.models.planning import ProjectPlan, ProjectTask
from backend.models.record import Record


# 用 s 按 pid 和 person_id 查询项目内人员，返回对象或 None，避免跨项目获取。
def get_person(s, pid, person_id):
    return s.scalar(select(ProjectPerson).where(ProjectPerson.project_id == pid, ProjectPerson.id == person_id))


# 用 s 返回 pid 项目下按 ID 排序的人员列表。
def list_people(s, pid):
    return s.scalars(select(ProjectPerson).where(ProjectPerson.project_id == pid).order_by(ProjectPerson.id)).all()


# 检查 pid 下 person_id 是否被任务、待审草稿或资源联系人引用，返回布尔值；按项目到计划顺序加锁，调用方须先领取项目版本。
def referenced(s, pid, person_id):
    from backend.dao.shooting import referenced as shooting_referenced
    if shooting_referenced(s, pid, 'person_ids', person_id):
        return True
    # 调用前已领取项目版本；保持项目→计划锁顺序，覆盖正式和待审资料。
    plan = s.scalar(select(ProjectPlan).where(ProjectPlan.project_id == pid).with_for_update().execution_options(populate_existing=True))
    details = []
    if plan:
        tasks = s.scalars(select(ProjectTask).where(ProjectTask.plan_id == plan.id).with_for_update().execution_options(populate_existing=True)).all()
        details.extend(t.details for t in tasks)
        if plan.draft and plan.draft.get('status') == 'pending':
            for op in plan.draft.get('result', {}).get('operations', []):
                details.extend([(op.get('task') or {}).get('details', {}), (op.get('changes') or {}).get('details', {})])
    if any(person_id in (d or {}).get('person_ids', []) for d in details):
        return True
    resources = s.scalars(select(Record).where(Record.project_id == pid, Record.kind == 'resource')).all()
    from backend.models.change import Change
    drafts = s.scalars(select(Change).where(Change.project_id == pid, Change.status == 'pending')).all()
    data = [r.data for r in resources]
    data.extend(op.get('data') or {} for draft in drafts for op in draft.operations if op.get('kind') == 'resource' and not op.get('delete'))
    return any((d.get('preparation') or {}).get('contact_person_id') == person_id for d in data)


# 用 data 新建或更新 current 人员并 flush，返回对象；s/pid 指定会话和归属，不提交。
def write(s, pid, data, current=None):
    if current is None:
        current = ProjectPerson(project_id=pid)
        s.add(current)
    for key, value in data.items():
        setattr(current, key, value)
    s.flush()
    return current


# 将 person 标记为待删除；s 的提交由服务层决定，无返回值。
def delete(s, person):
    s.delete(person)
