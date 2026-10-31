from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import LONGTEXT
from backend.common.database.base import Base, uid, now


class Script(Base):
    """一条记录是一版不可变原文；拆解草稿可编辑。"""
    __tablename__ = 'scripts'
    __table_args__ = (UniqueConstraint('project_id', 'version_number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    previous_script_id: Mapped[str | None] = mapped_column(ForeignKey('scripts.id'))
    version_number: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str] = mapped_column(String(100), default='')
    title: Mapped[str] = mapped_column(String(200))
    source_name: Mapped[str] = mapped_column(String(300), default='')
    # MySQL TEXT 只有约 64KB，无法容纳上限 50,000 字的中文剧本。
    content: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), 'mysql'))
    status: Mapped[str] = mapped_column(String(30), default='pending')
    revision: Mapped[int] = mapped_column(Integer, default=0)
    deleted_reviewed: Mapped[bool] = mapped_column(default=False)
    review_issues: Mapped[list] = mapped_column(JSON, default=list)
    parse_error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    confirmed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class SceneBreakdown(Base):
    __tablename__ = 'scene_breakdowns'
    __table_args__ = (UniqueConstraint('script_id', 'sort_order'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    script_id: Mapped[str] = mapped_column(ForeignKey('scripts.id'), index=True)
    previous_scene_id: Mapped[str | None] = mapped_column(ForeignKey('scene_breakdowns.id'))
    sort_order: Mapped[int] = mapped_column(Integer)
    # 单值字段方便检索；多项拍摄信息使用有 Schema 的 JSON，不拆角色、道具实体表。
    scene_number: Mapped[str] = mapped_column(String(50), default='')
    interior_exterior: Mapped[str] = mapped_column(String(30), default='')
    atmosphere: Mapped[str] = mapped_column(String(50), default='')
    location: Mapped[str] = mapped_column(String(500), default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    extracted_data: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    review_issues: Mapped[list] = mapped_column(JSON, default=list)
    match_status: Mapped[str] = mapped_column(String(30), default='first')
    change_reviewed: Mapped[bool] = mapped_column(default=False)
