from pydantic import BaseModel, Field
from backend.schemas.record import Operation


class ChangeInput(BaseModel):
    base_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=10000)
    operations: list[Operation] = Field(min_length=1, max_length=50)

