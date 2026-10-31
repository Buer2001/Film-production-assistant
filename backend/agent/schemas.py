from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None

