"""日程两表；详情使用有 Schema 的 JSON，不混入旧 records。"""
from datetime import date
from sqlalchemy import String, Integer, Text, JSON, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


class ProjectPlan(Base):
    __tablename__ = 'project_plans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), unique=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    shoot_start: Mapped[date | None] = mapped_column(Date)
    shoot_end: Mapped[date | None] = mapped_column(Date)
    close_date: Mapped[date | None] = mapped_column(Date)
    context: Mapped[str] = mapped_column(Text, default='')
    source_script_id: Mapped[str | None] = mapped_column(ForeignKey('scripts.id'))
    source_script_revision: Mapped[int | None] = mapped_column(Integer)
    draft: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)


class ProjectTask(Base):
    __tablename__ = 'project_tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    plan_id: Mapped[str] = mapped_column(ForeignKey('project_plans.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    phase: Mapped[str] = mapped_column(String(20), default='preparation')
    category: Mapped[str] = mapped_column(String(30), default='other')
    status: Mapped[str] = mapped_column(String(20), default='todo')
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    completion_criteria: Mapped[str] = mapped_column(Text, default='')
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    completed_at: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)
