# 定义通用记录、资源落实资料和修改操作，根据种类选择写入结构。
"""通用记录契约及资源落实资料；按记录种类限制可写字段。"""
from datetime import date as Date, time as Time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from backend.schemas.availability import Availability


# 通用记录：标题/状态、责任和关联、排期时段、金额及来源备注；金额非负且保留两位小数。
class Item(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=300)
    category: str = ''
    status: Literal['待确认', '进行中', '已确认', '已完成', '待补拍'] = '待确认'
    owner: str = ''
    # 关联及排期字段可被不同 kind 复用；是否可写和跨记录引用由业务层继续检查。
    scene_ids: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    date: Date | None = None
    start: Time | None = None
    minutes: int = Field(default=60, gt=0, le=1440)
    # 金额使用 Decimal 限定精度和非负范围，避免浮点误差进入账目。
    amount: Decimal = Field(default=Decimal('0'), ge=0, max_digits=12, decimal_places=2)
    source: str = ''
    notes: str = ''



# 人工资源落实信息：联系资料、可用时段和费用状态；金额必须匹配费用确认状态。
class Preparation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['pending', 'contacting', 'confirmed', 'unavailable'] = 'pending'
    # 稳定人员 ID 和手填联系信息并存；是否属于当前项目由业务层检查。
    contact_person_id: str | None = Field(default=None, min_length=1, max_length=36)
    contact_name: str = Field(default='', max_length=200)
    contact: str = Field(default='', max_length=1000)
    availability: list[Availability] = Field(default_factory=list, max_length=100)
    # 费用状态区分未知、免费、报价和已确定，不能仅凭数字推断落实程度。
    cost_status: Literal['unknown', 'free', 'quoted', 'confirmed'] = 'unknown'
    cost_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    notes: str = Field(default='', max_length=10000)

    # 检查当前费用状态和金额是否一致；未知、免费及报价分别处理，非法抛 ValueError，否则返回 self。
    @model_validator(mode='after')
    def consistent_cost(self):
        # 金额属于落实事实，不能把未知的历史金额误解为报价或免费。
        if self.cost_status == 'unknown' and self.cost_amount is not None:
            raise ValueError('费用未知时不能填写金额')
        if self.cost_status == 'free' and self.cost_amount not in (None, Decimal('0')):
            raise ValueError('免费资源的金额只能为零或留空')
        if self.cost_status in ('quoted', 'confirmed') and self.cost_amount is None:
            raise ValueError('已报价或已确定费用必须填写金额')
        return self


# 资源记录沿用 Item，并可附带人工 preparation；空值表示尚无落实资料。
class ResourceData(Item):
    preparation: Preparation | None = None


# 记录修改项：kind/id/delete 指定操作目标，data 按 kind 选择资源或通用记录契约。
class Operation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['scene', 'requirement', 'resource', 'task', 'schedule', 'expense', 'decision']
    id: str | None = None
    delete: bool = False
    data: ResourceData | Item | None = None

    # 接收原始 value 和校验 info，按 kind 选择 ResourceData 或 Item，返回校验对象；保留 None，错误向上传递。
    @field_validator('data', mode='before')
    @classmethod
    def data_for_kind(cls, value, info):
        # 按种类选择 Schema，避免资源新字段漏入其他通用记录。
        if value is None:
            return None
        schema = ResourceData if info.data.get('kind') == 'resource' else Item
        if isinstance(value, BaseModel):
            value = value.model_dump(mode='json', exclude_unset=True)
        return schema.model_validate(value)

