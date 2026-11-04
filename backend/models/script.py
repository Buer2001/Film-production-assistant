# 定义剧本版本和正式场次，保留版本关联、原文证据及人工审阅状态。
from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import LONGTEXT
from backend.common.database.base import Base, uid, now


# 项目内剧本版本；项目和版本号组合唯一，previous_script_id 形成版本链，revision 支持正式版本校验。
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
    # 剧本正式状态及 revision 独立于文件草稿的进度序号和编辑版本。
    status: Mapped[str] = mapped_column(String(30), default='pending')
    revision: Mapped[int] = mapped_column(Integer, default=0)
    deleted_reviewed: Mapped[bool] = mapped_column(default=False)
    review_issues: Mapped[list] = mapped_column(JSON, default=list)
    parse_error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    confirmed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


# 正式场次；版本内 sort_order 唯一，保留前版场次引用、证据和初始模型结果以供人工审阅。
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
    # 分别保留初始模型结果和可信原文证据，支持人工编辑后追溯，不能用客户端展示值覆盖来源。
    extracted_data: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    review_issues: Mapped[list] = mapped_column(JSON, default=list)
    # 前后版本匹配及审阅状态供改版人工确认，不能仅凭相似度自动视为已核对。
    match_status: Mapped[str] = mapped_column(String(30), default='first')
    change_reviewed: Mapped[bool] = mapped_column(default=False)
