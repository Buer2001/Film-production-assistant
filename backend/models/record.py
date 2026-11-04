# 定义按 kind 区分的通用业务记录，具体 data 结构由 Schema 和服务层约束。
from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


# 通用项目记录；project_id/kind 负责归属和分类，JSON data 承载经业务校验的字段。
class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)
