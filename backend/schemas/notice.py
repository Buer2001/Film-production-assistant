from datetime import date as Date
from pydantic import BaseModel, Field


class NoticeInput(BaseModel):
    date: Date
    base_revision: int = Field(ge=0)
    notes: str = Field(default='', max_length=20000)

