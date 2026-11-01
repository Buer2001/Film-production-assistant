"""计划和任务读写；不自行提交，不接受跨计划任务操作。"""
from sqlalchemy import select, update
from backend.models.planning import ProjectPlan, ProjectTask
from backend.common.database.base import now


def get(session, pid, *, current=False):
    statement = select(ProjectPlan).where(ProjectPlan.project_id == pid)
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalar(statement)


def create(session, pid):
    row = ProjectPlan(project_id=pid)
    session.add(row)
    session.flush()
    return row


def tasks(session, plan_id, *, current=False):
    statement = select(ProjectTask).where(ProjectTask.plan_id == plan_id).order_by(ProjectTask.created_at, ProjectTask.id)
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalars(statement).all()


def claim(session, row, revision):
    return session.execute(update(ProjectPlan).where(ProjectPlan.id == row.id, ProjectPlan.revision == revision)
                           .values(revision=revision + 1, updated_at=now())).rowcount == 1


def write_task(session, plan_id, key, data, existing=None):
    row = existing if existing is not None else ProjectTask(id=key, plan_id=plan_id)
    old_status = row.status
    for field, value in data.items():
        setattr(row, field, value)
    row.completed_at = (row.completed_at if old_status == 'completed' else now()) if row.status == 'completed' else None
    row.updated_at = now()
    session.add(row)
    return row


def scene_reference(session, pid, script_id, scene_id):
    from backend.models.script import Script, SceneBreakdown
    return session.scalar(select(SceneBreakdown).join(Script, Script.id == SceneBreakdown.script_id)
        .where(Script.project_id == pid, Script.id == script_id, Script.status == 'confirmed', SceneBreakdown.id == scene_id))


def resource_exists(session, pid, record_id):
    from backend.models.record import Record
    return session.scalar(select(Record.id).where(Record.id == record_id, Record.project_id == pid, Record.kind == 'resource')) is not None


def confirmed(session, pid, draft_id):
    from backend.models.event import Event
    events = session.scalars(select(Event).where(Event.project_id == pid, Event.type == 'planning_confirm')
        .execution_options(populate_existing=True)).all()
    return any(e.data.get('draft_id') == draft_id for e in events)


def task_for_project(session, pid, task_id):
    return session.scalar(select(ProjectTask).join(ProjectPlan, ProjectTask.plan_id == ProjectPlan.id)
        .where(ProjectPlan.project_id == pid, ProjectTask.id == task_id))
