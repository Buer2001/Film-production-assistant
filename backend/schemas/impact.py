# 约束影响分析目标，支持记录 ID、资源名或待确认修改草稿。
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.tools.normalization import unique


# 分析目标至少提供一种；record_ids/resources 各最多 50 项，base_revision 可用于检查快照。
class ImpactInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    record_ids: list[str] = Field(default_factory=list, max_length=50)
    resources: list[str] = Field(default_factory=list, max_length=50)
    change_id: str | None = None
    base_revision: int | None = Field(default=None, ge=0)

    # 原地去重资源名并验证至少指定一种目标；不满足时抛 ValueError，否则返回 self。
    @model_validator(mode='after')
    def has_target(self):
        self.resources = unique(self.resources)
        if not self.record_ids and not self.resources and not self.change_id:
            raise ValueError('请指定记录、资源名称或修改草稿')
        return self

