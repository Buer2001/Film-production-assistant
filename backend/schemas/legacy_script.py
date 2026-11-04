# 定义旧剧本输入及模型提取结构，提取内容仍须经过原文证据校验。
from pydantic import BaseModel, ConfigDict, Field


# 旧版结构契约基类，拒绝未声明字段。
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


# 旧剧本请求：原文最多 50000 字符，附来源名称和项目基准版本。
class ScriptInput(Strict):
    text: str = Field(min_length=1, max_length=50000)
    source_name: str = Field(default='粘贴剧本', min_length=1, max_length=200)
    base_revision: int = Field(ge=0)


# 旧版模型场次：必填标题及连续原文证据，人物、场地、道具和疑问受长度限制。
class Scene(Strict):
    title: str = Field(min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=10000)
    characters: list[str] = Field(default_factory=list, max_length=100)
    location: str = Field(default='', max_length=300)
    props: list[str] = Field(default_factory=list, max_length=100)
    time: str = Field(default='', max_length=100)
    interior: str = Field(default='', max_length=100)
    questions: list[str] = Field(default_factory=list, max_length=20)


# 旧版提取结果必须包含 1 至 50 场，不允许空结果或静默超限。
class Extraction(Strict):
    scenes: list[Scene] = Field(min_length=1, max_length=50)

