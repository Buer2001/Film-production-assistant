# 约束新建项目名称，拒绝空字符串和超长名称。
from pydantic import BaseModel, Field


# 新建项目请求，name 长度为 1 至 200 字符。
class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)

