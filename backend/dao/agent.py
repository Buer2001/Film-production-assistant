# 文件职责：V5 运行、草稿和执行凭据的数据库读写；条件更新承担并发推进保护，不自行提交。
"""运行状态与联合草稿的存取；所有条件更新失败都表示并发冲突。"""
from sqlalchemy import select, update
from backend.models.agent import AgentRun, AgentDraft, AgentExecution
from backend.common.database.base import now


# 新建一次工作记录并 flush 取得 ID；提交由业务服务决定。
def add_run(session, pid, *, mode, request_text, state):
    row = AgentRun(project_id=pid, mode=mode, request_text=request_text, state_json=state)
    session.add(row)
    session.flush()
    return row


# 按项目和运行 ID 取记录；跨项目 ID 与不存在都返回 None，避免越权恢复。
def get_run(session, pid, run_id):
    return session.scalar(select(AgentRun).where(AgentRun.project_id == pid, AgentRun.id == run_id))


# 取项目最近的工作记录；列表只用于入口展示，不代替检查点状态。
def list_runs(session, pid, limit=20):
    return session.scalars(select(AgentRun).where(AgentRun.project_id == pid)
                           .order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(limit)).all()


# 按 version 条件推进运行状态并递增版本；返回影响行数，0 表示其他请求已经推进。
def claim_run(session, run_id, version, *, fields):
    return session.execute(update(AgentRun).where(AgentRun.id == run_id, AgentRun.version == version)
                           .values(version=version + 1, updated_at=now(), **fields)).rowcount


# 无条件修正运行状态；只用于幂等命中或放弃等不需要竞争的场景。
def set_run(session, run_id, *, fields):
    return session.execute(update(AgentRun).where(AgentRun.id == run_id)
                           .values(updated_at=now(), **fields)).rowcount


# 登记联合草稿；同一运行的新草稿由服务层把旧 pending 草稿置为失效。
def add_draft(session, pid, run_id, *, operations, validation, source, rationale):
    row = AgentDraft(project_id=pid, run_id=run_id, operations_json=operations,
                     validation_json=validation, source_json=source, rationale_json=rationale)
    session.add(row)
    session.flush()
    return row


# 按项目和草稿 ID 取草稿；跨项目 ID 返回 None。
def get_draft(session, pid, draft_id):
    return session.scalar(select(AgentDraft).where(AgentDraft.project_id == pid, AgentDraft.id == draft_id))


# 取指定运行的待处理草稿，用于恢复后展示当前建议。
def pending_draft(session, run_id):
    return session.scalar(select(AgentDraft).where(AgentDraft.run_id == run_id, AgentDraft.status == 'pending')
                          .order_by(AgentDraft.created_at.desc()))


# 按 revision 与 pending 状态条件领取草稿；0 表示版本已变或已被处理，不能再执行。
def claim_draft(session, draft_id, revision, *, status):
    return session.execute(update(AgentDraft).where(AgentDraft.id == draft_id, AgentDraft.revision == revision,
                                                   AgentDraft.status == 'pending')
                           .values(status=status, updated_at=now())).rowcount


# 把同一运行里除 keep_id 之外的待处理草稿标为失效，避免并存两份可确认建议。
def invalidate_pending(session, run_id, keep_id):
    return session.execute(update(AgentDraft).where(AgentDraft.run_id == run_id, AgentDraft.id != keep_id,
                                                   AgentDraft.status == 'pending')
                           .values(status='invalidated', updated_at=now())).rowcount


# 按 revision 条件更新草稿内容并递增版本；0 表示人工修改与执行发生竞争。
def revise_draft(session, draft_id, revision, *, fields):
    return session.execute(update(AgentDraft).where(AgentDraft.id == draft_id, AgentDraft.revision == revision)
                           .values(revision=revision + 1, updated_at=now(), **fields)).rowcount


# 按 draft_id 与 revision 查询成功执行凭据；命中即表示该版草稿已经执行过。
def get_execution(session, draft_id, revision):
    return session.scalar(select(AgentExecution).where(AgentExecution.draft_id == draft_id,
                                                       AgentExecution.draft_revision == revision))


# 登记执行凭据；与业务修改在同一事务提交，唯一约束由数据库保证。
def add_execution(session, pid, draft_id, revision, result):
    row = AgentExecution(project_id=pid, draft_id=draft_id, draft_revision=revision, result_json=result)
    session.add(row)
    session.flush()
    return row
