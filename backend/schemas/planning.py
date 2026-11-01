"""项目日程契约：正式事实、计划日期和模型建议分开表达。"""
from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Settings(Contract):
    shoot_start: Date | None = None
    shoot_end: Date | None = None
    close_date: Date | None = None
    context: str = Field(default='', max_length=12000)

    @model_validator(mode='after')
    def dates(self):
        values = [d for d in (self.shoot_start, self.shoot_end, self.close_date) if d]
        if values != sorted(values):
            raise ValueError('开拍、杀青和收尾日期必须先后有序')
        return self


class Dependency(Contract):
    task_id: str = Field(min_length=1, max_length=100)
    relation: Literal['finish_to_start'] = 'finish_to_start'


class Constraint(Contract):
    kind: Literal['start_on_or_after', 'finish_by', 'relative_to_milestone']
    date: Date | None = None
    milestone: Literal['shoot_start', 'shoot_end', 'close_date'] | None = None
    offset_days: int = Field(default=0, ge=-365, le=365)
    strength: Literal['hard', 'soft'] = 'soft'
    confirmation: Literal['pending', 'confirmed'] = 'pending'
    source: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def target(self):
        if self.kind == 'relative_to_milestone':
            if self.milestone is None or self.date is not None:
                raise ValueError('相对约束需要项目节点，不接受固定日期')
        elif self.date is None or self.milestone is not None:
            raise ValueError('固定约束需要日期，不接受项目节点')
        if self.confirmation == 'confirmed' and not self.source:
            raise ValueError('已确认约束需要注明来源')
        return self


class SceneRef(Contract):
    script_id: str = Field(min_length=1, max_length=36)
    scene_id: str = Field(min_length=1, max_length=36)
    scene_number: str = Field(default='', max_length=50)
    location: str = Field(default='', max_length=500)


class ResourceRef(Contract):
    type: Literal['equipment', 'prop', 'location', 'costume', 'other'] = 'other'
    name: str = Field(min_length=1, max_length=200)
    record_id: str | None = Field(default=None, max_length=36)


class Origin(Contract):
    type: Literal['manual', 'model'] = 'manual'
    generation_id: str | None = Field(default=None, max_length=36)


class Details(Contract):
    dependencies: list[Dependency] = Field(default_factory=list, max_length=100)
    constraints: list[Constraint] = Field(default_factory=list, max_length=30)
    scene_refs: list[SceneRef] = Field(default_factory=list, max_length=200)
    resource_refs: list[ResourceRef] = Field(default_factory=list, max_length=100)
    estimate_days: int | None = Field(default=None, ge=1, le=365)
    rationale: str = Field(default='', max_length=2000)
    checklist_refs: list[str] = Field(default_factory=list, max_length=50)
    origin: Origin = Field(default_factory=Origin)


class TaskData(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    phase: Literal['preparation', 'shooting', 'closing'] = 'preparation'
    category: Literal['script', 'people', 'location', 'equipment', 'art', 'logistics', 'shooting', 'finance', 'other'] = 'other'
    status: Literal['todo', 'in_progress', 'completed', 'cancelled'] = 'todo'
    planned_start: Date | None = None
    planned_end: Date | None = None
    completion_criteria: str = Field(default='', max_length=2000)
    details: Details = Field(default_factory=Details)

    @model_validator(mode='after')
    def dates(self):
        if self.planned_start and self.planned_end and self.planned_start > self.planned_end:
            raise ValueError('任务开始日期不能晚于完成日期')
        return self


class Revision(Contract):
    revision: int = Field(ge=0)


class SettingsInput(Revision):
    settings: Settings


class TaskInput(Revision):
    task: TaskData


class PatchInput(Revision):
    changes: dict


class GenerateInput(Revision):
    instruction: str = Field(default='', max_length=4000)


class Operation(Contract):
    action: Literal['add', 'update', 'cancel']
    ref: str = Field(min_length=1, max_length=100)
    task: TaskData | None = None
    changes: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def shape(self):
        if self.action == 'add' and (self.task is None or self.changes):
            raise ValueError('新增需要完整任务，不接受 changes')
        if self.action != 'add' and self.task is not None:
            raise ValueError('修改和取消不接受 task')
        if self.action == 'update' and not self.changes:
            raise ValueError('修改需要指定字段')
        if self.action == 'cancel' and self.changes:
            raise ValueError('取消不接受 changes')
        return self


class Coverage(Contract):
    check_id: str = Field(min_length=1, max_length=100)
    status: Literal['addressed', 'done', 'not_applicable', 'unknown']
    reason: str = Field(min_length=1, max_length=1000)
    task_refs: list[str] = Field(default_factory=list, max_length=100)


class PlanResult(Contract):
    operations: list[Operation] = Field(default_factory=list, max_length=300)
    questions: list[str] = Field(default_factory=list, max_length=50)
    coverage: list[Coverage] = Field(max_length=100)


class DraftInput(Revision):
    draft_id: str
    result: PlanResult


class ConfirmInput(Revision):
    draft_id: str
