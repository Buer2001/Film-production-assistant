# 定义计划设置、任务事实、模型建议和草稿确认契约，禁止未声明字段。
"""项目日程契约：正式事实、计划日期和模型建议分开表达。"""
from datetime import date as Date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from backend.schemas.availability import UsagePeriod


# 日程共用契约，拒绝额外字段并去除字符串首尾空白。
class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


# 项目开拍、杀青、收尾节点可缺省；已填写日期必须顺序合理，context 为补充背景。
class Settings(Contract):
    shoot_start: Date | None = None
    shoot_end: Date | None = None
    close_date: Date | None = None
    context: str = Field(default='', max_length=12000)

    # 检查已填写日期的先后顺序；倒置时抛 ValueError，通过后返回 self。
    @model_validator(mode='after')
    def dates(self):
        values = [d for d in (self.shoot_start, self.shoot_end, self.close_date) if d]
        if values != sorted(values):
            raise ValueError('开拍、杀青和收尾日期必须先后有序')
        return self


# 前置任务引用，仅支持前置完成后开始的 finish_to_start 关系。
class Dependency(Contract):
    task_id: str = Field(min_length=1, max_length=100)
    relation: Literal['finish_to_start'] = 'finish_to_start'


# 日期约束区分固定日期和相对里程碑；强度及确认状态分开记录，确认必须有来源。
class Constraint(Contract):
    kind: Literal['start_on_or_after', 'finish_by', 'relative_to_milestone']
    date: Date | None = None
    milestone: Literal['shoot_start', 'shoot_end', 'close_date'] | None = None
    offset_days: int = Field(default=0, ge=-365, le=365)
    strength: Literal['hard', 'soft'] = 'soft'
    confirmation: Literal['pending', 'confirmed'] = 'pending'
    source: str = Field(default='', max_length=1000)

    # 检查约束种类对应的日期/里程碑组合及确认来源；非法抛 ValueError，否则返回 self。
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


# 场次稳定 ID 引用；剧本/场次 ID 必填，场号和场地作为展示信息。
class SceneRef(Contract):
    script_id: str = Field(min_length=1, max_length=36)
    scene_id: str = Field(min_length=1, max_length=36)
    scene_number: str = Field(default='', max_length=50)
    location: str = Field(default='', max_length=500)


# 资源分类和名称必填语义由契约约束；record_id 可选，用于关联已有资源事实。
class ResourceRef(Contract):
    type: Literal['equipment', 'prop', 'location', 'costume', 'other'] = 'other'
    name: str = Field(min_length=1, max_length=200)
    record_id: str | None = Field(default=None, max_length=36)


# 标记任务人工或模型来源，可记录生成批次 generation_id。
class Origin(Contract):
    type: Literal['manual', 'model'] = 'manual'
    generation_id: str | None = Field(default=None, max_length=36)


PersonOrDepartment = Annotated[str, Field(min_length=1, max_length=50)]


# 任务扩展信息：责任分工、人员/时段、依赖/约束、场次/资源依据及估算来源。
class Details(Contract):
    # 责任分工保留部门和手填姓名；稳定 person_ids 显式关联人员档案，不自动按姓名匹配。
    department: str = Field(default='', max_length=50, description='根据具体任务判断主责部门，如摄影组/灯光组/制片组；工作类别不是部门，确实无法判断时留空')
    collaborating_departments: list[PersonOrDepartment] = Field(default_factory=list, max_length=8)
    assignees: list[PersonOrDepartment] = Field(default_factory=list, max_length=20)
    # 姓名保留历史手填内容；稳定 ID 负责关联人员资料，绝不按同名自动绑定。
    person_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(default_factory=list, max_length=20)
    requires_people: bool = False
    usage_period: UsagePeriod | None = None
    result_notes: str = Field(default='', max_length=2000)

    # 接收 values 并按首次出现顺序去重，返回列表，不自动关联同名人员。
    @field_validator('collaborating_departments', 'assignees', 'person_ids')
    @classmethod
    def unique_names(cls, values):
        return list(dict.fromkeys(values))

    # 排期依据：任务依赖、时间约束、场次及资源引用；这里校验结构，归属和存在性由业务层检查。
    dependencies: list[Dependency] = Field(default_factory=list, max_length=100)
    constraints: list[Constraint] = Field(default_factory=list, max_length=30)
    scene_refs: list[SceneRef] = Field(default_factory=list, max_length=200)
    resource_refs: list[ResourceRef] = Field(default_factory=list, max_length=100)
    # 估时、理由、检查清单及来源用于解释建议，不自动升级为已确认事实。
    estimate_days: int | None = Field(default=None, ge=1, le=365)
    rationale: str = Field(default='', max_length=2000)
    checklist_refs: list[str] = Field(default_factory=list, max_length=50)
    origin: Origin = Field(default_factory=Origin)


# 任务事实包含阶段、类别、状态、可选计划日期和完成条件；日期前后顺序必须合法。
class TaskData(Contract):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    phase: Literal['preparation', 'shooting', 'closing'] = 'preparation'
    category: Literal['script', 'people', 'location', 'equipment', 'art', 'logistics', 'shooting', 'finance', 'other'] = 'other'
    status: Literal['todo', 'in_progress', 'completed', 'cancelled'] = 'todo'
    # 计划日期允许暂缺；填写两个端点时再校验前后关系。
    planned_start: Date | None = None
    planned_end: Date | None = None
    completion_criteria: str = Field(default='', max_length=2000)
    details: Details = Field(default_factory=Details)

    # 检查已填写日期的先后顺序；倒置时抛 ValueError，通过后返回 self。
    @model_validator(mode='after')
    def dates(self):
        if self.planned_start and self.planned_end and self.planned_start > self.planned_end:
            raise ValueError('任务开始日期不能晚于完成日期')
        return self


# 日程写入的非负并发版本；与项目及剧本 revision 分开使用。
class Revision(Contract):
    revision: int = Field(ge=0)


# 携带日程 revision 的完整计划设置请求。
class SettingsInput(Revision):
    settings: Settings


# 携带日程 revision 的完整任务新建请求。
class TaskInput(Revision):
    task: TaskData


# 携带日程 revision 和局部 changes；可写字段由业务层继续校验。
class PatchInput(Revision):
    changes: dict


# 携带日程 revision 和最多 4000 字符补充指令，生成结果只进入待审草稿。
class GenerateInput(Revision):
    instruction: str = Field(default='', max_length=4000)


# 模型建议项：add 使用完整 task，update 使用非空 changes，cancel 不接收数据载荷。
class Operation(Contract):
    action: Literal['add', 'update', 'cancel']
    ref: str = Field(min_length=1, max_length=100)
    task: TaskData | None = None
    changes: dict = Field(default_factory=dict)

    # 检查 action 对应 task/changes 的互斥和必填关系；非法抛 ValueError，否则返回 self。
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


# 检查清单覆盖项，保存处理状态、理由和关联任务引用，避免把未知当已完成。
class Coverage(Contract):
    check_id: str = Field(min_length=1, max_length=100)
    status: Literal['addressed', 'done', 'not_applicable', 'unknown']
    reason: str = Field(min_length=1, max_length=1000)
    task_refs: list[str] = Field(default_factory=list, max_length=100)


# 模型建议结果：最多 300 项操作和 50 个问题，coverage 必须显式提供。
class PlanResult(Contract):
    operations: list[Operation] = Field(default_factory=list, max_length=300)
    questions: list[str] = Field(default_factory=list, max_length=50)
    coverage: list[Coverage] = Field(max_length=100)


# 按 revision/draft_id 编辑指定草稿，result 必须符合完整建议契约。
class DraftInput(Revision):
    draft_id: str
    result: PlanResult


# 用 revision 和 draft_id 共同定位要确认或废弃的草稿，防止处理错版建议。
class ConfirmInput(Revision):
    draft_id: str


# 按任务 ref 提交主责部门、协作部门和理由；无法判断时允许主责部门为空。
class DepartmentAssignment(Contract):
    ref: str = Field(min_length=1, max_length=100)
    department: str = Field(max_length=50, description='建议主责部门；无法判断时必须为空字符串')
    collaborating_departments: list[PersonOrDepartment] = Field(default_factory=list, max_length=8)
    reason: str = Field(min_length=1, max_length=500)


# 部门建议结果必须显式提供 assignments，最多 500 项。
class DepartmentResult(Contract):
    assignments: list[DepartmentAssignment] = Field(max_length=500)
