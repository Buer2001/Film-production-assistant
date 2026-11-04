# 约束通告发布日期、项目基准版本和补充备注。
from datetime import date as Date
from pydantic import BaseModel, Field


# 发布请求：日期、非负项目基准版本及最多 20000 字符备注。
class NoticeInput(BaseModel):
    date: Date
    base_revision: int = Field(ge=0)
    notes: str = Field(default='', max_length=20000)

