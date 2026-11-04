# 文件职责：保存计划安排和实际日志；扩展字段经过 Schema 校验后写入 JSON。
from datetime import datetime, date
from sqlalchemy import String, JSON, DateTime, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


# 一条安排只关联一个正式场次；非拍摄事项允许没有场次，跨日用完整本地日期时间表达。
class ShootingItem(Base):
    __tablename__ = 'shooting_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey('scene_breakdowns.id'))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


# 日志独立于计划保存实际事实；临时加拍没有 item_id，仍必须关联本项目正式场次。
class ShootingLog(Base):
    __tablename__ = 'shooting_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey('scene_breakdowns.id'))
    item_id: Mapped[str | None] = mapped_column(ForeignKey('shooting_items.id'), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)

