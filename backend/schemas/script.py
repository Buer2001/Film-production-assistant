from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Cast(Strict):
    name: str = Field(min_length=1, max_length=200)
    category: Literal['主要角色', '配角', '群演', '待确认'] = '待确认'


class Makeup(Strict):
    character: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=3000)


class Prop(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=3000)


class SceneData(Strict):
    scene_number: str = Field(default='', max_length=50)
    interior_exterior: str = Field(default='', max_length=30)
    atmosphere: str = Field(default='', max_length=50)
    page_count: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=3)
    location: str = Field(default='', max_length=500)
    summary: str = Field(default='', max_length=5000)
    cast: list[Cast] = Field(default_factory=list, max_length=200)
    makeup_costume: list[Makeup] = Field(default_factory=list, max_length=200)
    action_props: list[Prop] = Field(default_factory=list, max_length=200)
    other_props: list[Prop] = Field(default_factory=list, max_length=200)
    notes: str = Field(default='', max_length=10000)


class ExtractedScene(SceneData):
    evidence_text: str = Field(min_length=1, max_length=50000)


class Extraction(Strict):
    scenes: list[ExtractedScene] = Field(min_length=1, max_length=200)


class SceneEdit(SceneData):
    id: str | None = None
    previous_scene_id: str | None = None
    match_status: Literal['first', 'pending', 'matched', 'new'] = 'first'
    change_reviewed: bool = False
    parse_status: Literal['pending', 'running', 'succeeded', 'failed'] = 'succeeded'
    parse_error: str = Field(default='', max_length=10000)
    resolution: Literal['pending', 'manual', 'excluded'] = 'pending'
    # 以下只用于展示；服务层不相信客户端提交的证据和初始模型结果。
    evidence: dict = Field(default_factory=dict)
    extracted_data: dict = Field(default_factory=dict)
    review_issues: list[str] = Field(default_factory=list)


class ScriptInput(Strict):
    title: str = Field(min_length=1, max_length=200)
    version_label: str = Field(default='', max_length=100)
    source_name: str = Field(default='', max_length=300)
    content: str = Field(min_length=1, max_length=50000)
    previous_script_id: str | None = None

    @field_validator('title', 'content')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('内容不能为空')
        return value


class RevisionInput(Strict):
    revision: int = Field(ge=0)


class SaveInput(RevisionInput):
    scenes: list[SceneEdit] = Field(max_length=200)
    deleted_reviewed: bool = False
    edited_fields: dict[str, list[str]] = Field(default_factory=dict)


class ConfirmInput(RevisionInput):
    accept_missing: bool = False
