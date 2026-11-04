# 定义通告快照表，记录发布日期、通告版本及对应项目版本。
from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


# 通告实体；date/version 为发布版本，revision 为来源项目版本，snapshot 固化发布事实。
class Notice(Base):
    __tablename__ = 'notices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    # 通告自身日期和版本与项目 revision 分开保存；snapshot 固定发布时的内容。
    date: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
