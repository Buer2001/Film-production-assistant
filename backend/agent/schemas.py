# 约束用户对话输入长度和可选会话标识。
from pydantic import BaseModel, Field


# 用户消息限制为 1 至 20000 字符；session_id 为空时由运行器创建新会话。
class AgentInput(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None

