# 约束修改草稿的项目基准版本、原因和有界操作列表。
from pydantic import BaseModel, Field
from backend.schemas.record import Operation


# 修改请求：非负 base_revision、非空 reason，以及 1 至 50 项完整操作。
class ChangeInput(BaseModel):
    base_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=10000)
    operations: list[Operation] = Field(min_length=1, max_length=50)

