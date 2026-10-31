from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=0)
