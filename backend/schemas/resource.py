"""资源维护使用项目revision，与日程revision分别校验。"""
from pydantic import BaseModel, ConfigDict, Field
from backend.schemas.record import Item


class ResourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    resource: Item
