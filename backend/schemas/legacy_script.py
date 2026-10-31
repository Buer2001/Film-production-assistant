from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ScriptInput(Strict):
    text: str = Field(min_length=1, max_length=50000)
    source_name: str = Field(default='粘贴剧本', min_length=1, max_length=200)
    base_revision: int = Field(ge=0)


class Scene(Strict):
    title: str = Field(min_length=1, max_length=300)
    evidence: str = Field(min_length=1, max_length=10000)
    characters: list[str] = Field(default_factory=list, max_length=100)
    location: str = Field(default='', max_length=300)
    props: list[str] = Field(default_factory=list, max_length=100)
    time: str = Field(default='', max_length=100)
    interior: str = Field(default='', max_length=100)
    questions: list[str] = Field(default_factory=list, max_length=20)


class Extraction(Strict):
    scenes: list[Scene] = Field(min_length=1, max_length=50)

