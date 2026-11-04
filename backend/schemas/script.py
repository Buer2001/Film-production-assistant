# 定义剧本原文、结构化拆解、场次编辑及草稿确认请求。
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# 剧本契约共用基类，拒绝未声明字段，降低模型输出和客户端数据混入风险。
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


# 演员需求按角色名称记录，类别只能取主要角色、配角、群演或待确认。
class Cast(Strict):
    name: str = Field(min_length=1, max_length=200)
    category: Literal['主要角色', '配角', '群演', '待确认'] = '待确认'


# 按 character 关联妆造需求，description 限制长度。
class Makeup(Strict):
    character: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=3000)


# 道具名称必填，description 可留空，用于动作及其他道具列表。
class Prop(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=3000)


# 单场业务字段：场号、内外景、氛围、场地、摘要、人物、妆造、道具和备注。
class SceneData(Strict):
    scene_number: str = Field(default='', max_length=50)
    interior_exterior: str = Field(default='', max_length=30)
    atmosphere: str = Field(default='', max_length=50)
    location: str = Field(default='', max_length=500)
    summary: str = Field(default='', max_length=5000)
    # 多项拍摄需求使用有界结构列表，人物、妆造和两类道具分别表达。
    cast: list[Cast] = Field(default_factory=list, max_length=200)
    makeup_costume: list[Makeup] = Field(default_factory=list, max_length=200)
    action_props: list[Prop] = Field(default_factory=list, max_length=200)
    other_props: list[Prop] = Field(default_factory=list, max_length=200)
    notes: str = Field(default='', max_length=10000)


# 模型单场输出必须提供非空 evidence_text，后续与原文核对而非信任模型偏移。
class ExtractedScene(SceneData):
    evidence_text: str = Field(min_length=1, max_length=50000)


# 模型结构化输出要求 1 至 200 场，每场包含业务字段和证据原文。
class Extraction(Strict):
    scenes: list[ExtractedScene] = Field(min_length=1, max_length=200)


# 场次编辑载荷，含自定义列、版本匹配、解析及人工处置状态；展示证据由服务层重新取可信来源。
class SceneEdit(SceneData):
    # 人工自定义列和版本匹配状态独立保存；字数可空，但不接受负数。
    custom_values: dict[str, str] = Field(default_factory=dict, max_length=50)
    word_count: int | None = Field(default=None, ge=0)
    id: str | None = None
    previous_scene_id: str | None = None
    match_status: Literal['first', 'pending', 'matched', 'new'] = 'first'
    change_reviewed: bool = False
    # 单场解析状态和人工处置分开：失败场可人工补录或明确排除，再决定是否确认。
    parse_status: Literal['pending', 'running', 'succeeded', 'failed'] = 'succeeded'
    parse_error: str = Field(default='', max_length=10000)
    resolution: Literal['pending', 'manual', 'excluded'] = 'pending'
    # 以下只用于展示；服务层不相信客户端提交的证据和初始模型结果。
    evidence: dict = Field(default_factory=dict)
    extracted_data: dict = Field(default_factory=dict)
    review_issues: list[str] = Field(default_factory=list)

    # 接收原始 value；若为字典，返回剔除历史 page_count 的副本，否则原样返回。
    @model_validator(mode='before')
    @classmethod
    def discard_legacy_page_count(cls, value):
        # 兼容仍打开旧页面的保存请求，但不再输出或保存页数。
        return {key: item for key, item in value.items() if key != 'page_count'} if isinstance(value, dict) else value

    # 接收自定义列 value，限制键长和内容长度；超限抛 ValueError，否则返回原字典。
    @field_validator('custom_values')
    @classmethod
    def bounded_custom_values(cls, value):
        if any(len(key) > 36 or len(text) > 3000 for key, text in value.items()):
            raise ValueError('自定义内容过长')
        return value


# 自定义列定义：可选稳定 ID、非空名称、说明及启用状态。
class CustomField(Strict):
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default='', max_length=300)
    active: bool = True


# 项目自定义列保存请求，非负 revision 用于并发检查，最多 50 列。
class CustomFieldsInput(Strict):
    revision: int = Field(ge=0)
    fields: list[CustomField] = Field(max_length=50)


# 不可变剧本原文输入，含标题、版本标签、来源及可选前版 ID；原文最多 50000 字符。
class ScriptInput(Strict):
    title: str = Field(min_length=1, max_length=200)
    version_label: str = Field(default='', max_length=100)
    source_name: str = Field(default='', max_length=300)
    content: str = Field(min_length=1, max_length=50000)
    previous_script_id: str | None = None

    # 接收 value 并拒绝纯空白标题或原文；通过后返回原字符串，不改写内容。
    @field_validator('title', 'content')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('内容不能为空')
        return value


# 草稿操作的非负 revision；服务层按操作区分文件草稿和正式基准版本。
class RevisionInput(Strict):
    revision: int = Field(ge=0)


# 文件草稿保存请求，最多 200 场；edited_fields 记录人工保护字段，deleted_reviewed 标记删除项审阅。
class SaveInput(RevisionInput):
    scenes: list[SceneEdit] = Field(max_length=200)
    deleted_reviewed: bool = False
    # 保护用户已经改过的字段，后续重试解析时不能直接覆盖人工值。
    edited_fields: dict[str, list[str]] = Field(default_factory=dict)


# 草稿确认请求；accept_missing/accept_unreviewed 显式控制接受缺失或未审阅项。
class ConfirmInput(RevisionInput):
    accept_missing: bool = False
    accept_unreviewed: bool = False
