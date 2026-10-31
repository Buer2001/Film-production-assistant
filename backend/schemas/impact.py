from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.tools.normalization import unique


class ImpactInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    record_ids: list[str] = Field(default_factory=list, max_length=50)
    resources: list[str] = Field(default_factory=list, max_length=50)
    change_id: str | None = None
    base_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def has_target(self):
        self.resources = unique(self.resources)
        if not self.record_ids and not self.resources and not self.change_id:
            raise ValueError('请指定记录、资源名称或修改草稿')
        return self

