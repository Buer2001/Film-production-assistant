# 提供计划及任务查询、乐观版本领取和项目内引用检查，不自行提交。
"""计划和任务读写；不自行提交，不接受跨计划任务操作。"""
from sqlalchemy import select, update
from backend.models.planning import ProjectPlan, ProjectTask
from backend.common.database.base import now


# 按 pid 获取计划；current=True 使用加锁当前读刷新 session 缓存，返回对象或 None。
def get(session, pid, *, current=False):
    statement = select(ProjectPlan).where(ProjectPlan.project_id == pid)
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalar(statement)


# 为 pid 新建计划并加入 session，flush 后返回对象；不提交。
def create(session, pid):
    row = ProjectPlan(project_id=pid)
    session.add(row)
    session.flush()
    return row


# 按 plan_id 返回稳定排序的任务列表；current=True 加锁并刷新缓存。
def tasks(session, plan_id, *, current=False):
    statement = select(ProjectTask).where(ProjectTask.plan_id == plan_id).order_by(ProjectTask.created_at, ProjectTask.id)
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalars(statement).all()


# 按 row.id 和 revision 条件递增计划版本及更新时间，返回是否成功领取；不提交 session。
def claim(session, row, revision):
    return session.execute(update(ProjectPlan).where(ProjectPlan.id == row.id, ProjectPlan.revision == revision)
                           .values(revision=revision + 1, updated_at=now())).rowcount == 1


# 用 plan_id/key/data 新建或更新 existing 任务，维护完成和更新时间并返回对象；完成状态退出时清空完成时间。
def write_task(session, plan_id, key, data, existing=None):
    row = existing if existing is not None else ProjectTask(id=key, plan_id=plan_id)
    old_status = row.status
    for field, value in data.items():
        setattr(row, field, value)
    # 首次进入 completed 记录时间；重复保存已完成任务保留原值，离开完成状态则清空。
    row.completed_at = (row.completed_at if old_status == 'completed' else now()) if row.status == 'completed' else None
    row.updated_at = now()
    session.add(row)
    return row


# 检查 pid/script_id/scene_id 是否指向本项目已确认版本场次；返回对象或 None。
def scene_reference(session, pid, script_id, scene_id):
    from backend.models.script import Script, SceneBreakdown
    return session.scalar(select(SceneBreakdown).join(Script, Script.id == SceneBreakdown.script_id)
        .where(Script.project_id == pid, Script.id == script_id, Script.status == 'confirmed', SceneBreakdown.id == scene_id))


# 检查 record_id 是否是 pid 项目资源，返回布尔值。
def resource_exists(session, pid, record_id):
    from backend.models.record import Record
    return session.scalar(select(Record.id).where(Record.id == record_id, Record.project_id == pid, Record.kind == 'resource')) is not None


# 检查 pid 的确认事件是否已记录 draft_id，返回布尔值供重复确认判定。
def confirmed(session, pid, draft_id):
    from backend.models.event import Event
    events = session.scalars(select(Event).where(Event.project_id == pid, Event.type == 'planning_confirm')
        .execution_options(populate_existing=True)).all()
    return any(e.data.get('draft_id') == draft_id for e in events)


# 按 pid 和 task_id 联表查询归属明确的任务，返回对象或 None。
def task_for_project(session, pid, task_id):
    return session.scalar(select(ProjectTask).join(ProjectPlan, ProjectTask.plan_id == ProjectPlan.id)
        .where(ProjectPlan.project_id == pid, ProjectTask.id == task_id))
