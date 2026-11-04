# 定义每项目一份计划及其任务，日期使用数据库日期类型，扩展详情保存在 JSON。
"""日程两表；详情使用有 Schema 的 JSON，不混入旧 records。"""
from datetime import date
from sqlalchemy import String, Integer, Text, JSON, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


# 每项目唯一的计划；独立 revision、项目节点、剧本来源和待审 draft 支持并发审阅。
class ProjectPlan(Base):
    __tablename__ = 'project_plans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), unique=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    # 项目节点和补充背景用于制定日程，日期可为空，不代表模型已经确认时间。
    shoot_start: Mapped[date | None] = mapped_column(Date)
    shoot_end: Mapped[date | None] = mapped_column(Date)
    close_date: Mapped[date | None] = mapped_column(Date)
    context: Mapped[str] = mapped_column(Text, default='')
    # 保留生成依据的剧本版本和 revision，后续审阅可检查来源变化。
    source_script_id: Mapped[str | None] = mapped_column(ForeignKey('scripts.id'))
    source_script_revision: Mapped[int | None] = mapped_column(Integer)
    # 待审建议整体存为 JSON；确认前不等同于正式任务事实。
    draft: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)


# 计划内任务；基本事实、计划日期、完成条件及 JSON 详情分组保存，完成时间由 DAO 维护。
class ProjectTask(Base):
    __tablename__ = 'project_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    plan_id: Mapped[str] = mapped_column(ForeignKey('project_plans.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    phase: Mapped[str] = mapped_column(String(20), default='preparation')
    category: Mapped[str] = mapped_column(String(30), default='other')
    status: Mapped[str] = mapped_column(String(20), default='todo')
    # 任务计划日期与 completed_at 实际完成时间分离，details 承载经 Schema 校验的扩展字段。
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    completion_criteria: Mapped[str] = mapped_column(Text, default='')
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    completed_at: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)
