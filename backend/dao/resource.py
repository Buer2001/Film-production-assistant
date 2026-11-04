# 查询通用记录中的资源，并检查日程及待确认草稿的稳定 ID 引用。
"""资源沿用records；日程引用检查只读取数据，不提交事务。"""
from sqlalchemy import select
from backend.models.record import Record
from backend.models.planning import ProjectPlan, ProjectTask


# 用 s 返回 pid 项目中 kind 为 resource 的记录列表，按 ID 排序。
def list_resources(s, pid):
    return s.scalars(select(Record).where(Record.project_id == pid, Record.kind == 'resource').order_by(Record.id)).all()


# 用 s 按 pid/rid 查询资源对象，非资源或跨项目时返回 None。
def get_resource(s, pid, rid):
    return s.scalar(select(Record).where(Record.id == rid, Record.project_id == pid, Record.kind == 'resource'))


# 检查 pid 下 rid 是否被正式任务或待审日程草稿引用；返回布尔值，同时锁定计划及任务直至外层事务结束。
def referenced(s, pid, rid):
    # V4 可先于 V2 计划存在，必须在旧逻辑的提前返回之前检查拍摄引用。
    from backend.dao.shooting import referenced as shooting_referenced
    if shooting_referenced(s, pid, 'resource_ids', rid):
        return True
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
