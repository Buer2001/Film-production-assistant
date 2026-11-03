"""资源沿用records；日程引用检查只读取数据，不提交事务。"""
from sqlalchemy import select
from backend.models.record import Record
from backend.models.planning import ProjectPlan, ProjectTask


def list_resources(s, pid):
    return s.scalars(select(Record).where(Record.project_id == pid, Record.kind == 'resource').order_by(Record.id)).all()


def get_resource(s, pid, rid):
    return s.scalar(select(Record).where(Record.id == rid, Record.project_id == pid, Record.kind == 'resource'))


def referenced(s, pid, rid):
    # 正式任务（含已完成项）和待确认草稿都要保留依据，不能删除其引用对象。
    plan = s.scalar(select(ProjectPlan).where(ProjectPlan.project_id == pid).with_for_update().execution_options(populate_existing=True))
    if plan is None:
        return False
    tasks = s.scalars(select(ProjectTask).where(ProjectTask.plan_id == plan.id).with_for_update().execution_options(populate_existing=True)).all()
    details = [t.details for t in tasks]
    if plan.draft and plan.draft.get('status') == 'pending':
        for op in plan.draft.get('result', {}).get('operations', []):
            details.append((op.get('task') or {}).get('details', {}))
            details.append((op.get('changes') or {}).get('details', {}))
    return any(ref.get('record_id') == rid for detail in details for ref in detail.get('resource_refs', []))
