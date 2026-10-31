from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)
