from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


class Change(Base):
    __tablename__ = 'changes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    base_revision: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    operations: Mapped[list] = mapped_column(JSON)
    before: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[str] = mapped_column(String(50), default=now)
