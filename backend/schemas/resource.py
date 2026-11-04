# 定义资源维护请求，使用项目版本而非日程版本。
"""资源维护使用项目revision，与日程revision分别校验。"""
from pydantic import BaseModel, ConfigDict, Field
from backend.schemas.record import ResourceData


# 资源完整写入请求，revision 对应项目版本，resource 包含资源及可选落实资料。
class ResourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    resource: ResourceData
