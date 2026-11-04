# 定义修改草稿表，保存基准版本、操作、修改前快照和确认状态。
from sqlalchemy import String, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid, now


# 草稿实体；base_revision 保护正式项目版本，before/operations 保留审阅依据，status 控制确认流程。
class Change(Base):
    __tablename__ = 'changes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    # 并发基准和审阅依据：提交时校验基准，operations/before 支持展示操作和修改前事实。
    base_revision: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    operations: Mapped[list] = mapped_column(JSON)
    before: Mapped[list] = mapped_column(JSON)
    # 流程状态默认 pending；确认或拒绝由业务服务通过条件更新领取。
    status: Mapped[str] = mapped_column(String(20), default='pending')
    created_at: Mapped[str] = mapped_column(String(50), default=now)
