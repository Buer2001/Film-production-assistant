# 文件职责：保存 V5 运行进度、联合草稿和执行凭据；不复制项目事实，正式数据仍在原业务表。
"""V5 三表：运行状态、联合草稿、唯一执行凭据。"""
from sqlalchemy import String, Integer, Text, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


# 一次独立编排工作对应一行；version 用于并发推进保护，state_json 只存本次工作所需信息。
class AgentRun(Base):
    __tablename__ = 'agent_runs'
    __table_args__ = (Index('ix_agent_runs_project_created', 'project_id', 'created_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    mode: Mapped[str] = mapped_column(String(20), default='compose')
    request_text: Mapped[str] = mapped_column(Text, default='')
    # status 表示运行、等待输入、等待审阅、完成等阶段；current_step 表示流程位置。
    status: Mapped[str] = mapped_column(String(20), default='running')
    current_step: Mapped[str] = mapped_column(String(30), default='understand')
    version: Mapped[int] = mapped_column(Integer, default=0)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # 本次工作依据的两个版本号；任务用计划版本，拍摄安排用项目版本，不能混用。
    base_plan_revision: Mapped[int] = mapped_column(Integer, default=0)
    base_project_revision: Mapped[int] = mapped_column(Integer, default=0)
    source_json: Mapped[dict] = mapped_column(JSON, default=dict)
    draft_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)


# 联合草稿：任务与拍摄安排共用一份，revision 由人工编辑递增，使旧检查和旧确认失效。
class AgentDraft(Base):
    __tablename__ = 'agent_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id'), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    operations_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)


# 成功执行的唯一凭据；(draft_id, draft_revision) 唯一约束由数据库兜底重复确认。
class AgentExecution(Base):
    __tablename__ = 'agent_executions'
    __table_args__ = (UniqueConstraint('draft_id', 'draft_revision', name='uq_agent_execution_draft_revision'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey('agent_drafts.id'))
    draft_revision: Mapped[int] = mapped_column(Integer)
    # 只记录正式 ID、临时 ID 映射和事件号，不保存业务事实副本。
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    executed_at: Mapped[str] = mapped_column(String(50), default=now)
