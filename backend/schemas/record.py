from datetime import date as Date, time as Time
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Item(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=300)
    category: str = ''
    status: Literal['待确认', '进行中', '已确认', '已完成', '待补拍'] = '待确认'
    owner: str = ''
    scene_ids: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    date: Date | None = None
    start: Time | None = None
    minutes: int = Field(default=60, gt=0, le=1440)
    amount: Decimal = Field(default=Decimal('0'), ge=0, max_digits=12, decimal_places=2)
    source: str = ''
    notes: str = ''



class Operation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['scene', 'requirement', 'resource', 'task', 'schedule', 'expense', 'decision']
    id: str | None = None
    delete: bool = False
    data: Item | None = None

