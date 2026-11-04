# 定义人工人员资料和携带项目版本的写入请求。
"""人员人工资料和版本化写入请求的契约。"""
from pydantic import BaseModel, ConfigDict, Field
from backend.schemas.availability import Availability


# 人工人员资料：姓名必填，角色和可用时段默认为空列表；联系方式不触发自动身份绑定。
class PersonData(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    department: str = ''
    roles: list[str] = Field(default_factory=list)
    phone: str = ''
    contact: str = ''
    availability: list[Availability] = Field(default_factory=list)
    notes: str = ''


# 人员写入携带非负项目 revision 和完整 PersonData，禁止额外字段。
class PersonInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    person: PersonData
