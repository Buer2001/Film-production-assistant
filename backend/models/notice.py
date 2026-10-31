from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


class Notice(Base):
    __tablename__ = 'notices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    date: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
