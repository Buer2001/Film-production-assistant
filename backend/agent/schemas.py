# 文件职责：定义 V5 运行、联合草稿、审阅和恢复的输入契约，拒绝未声明的字段。
"""V5 请求契约；候选操作只表达允许的对象和动作，正式执行另由业务服务决定。"""
from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


# 旧对话入口的输入；长度上限沿用原有约束，避免一次塞入过长文本。
class AgentInput(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None


# 编排范围：阶段加日期区间；跨度上限避免一次生成过多对象。
class Scope(Contract):
    phase: Literal['all', 'preparation', 'shooting', 'closing'] = 'all'
    start_date: Date | None = None
    end_date: Date | None = None
    include_tasks: bool = True
    include_shooting: bool = True
    targets: list[str] = Field(default_factory=list, max_length=50)

    # 日期必须成对且先后有序，跨度不超过 120 天；不合法抛 ValueError。
    @model_validator(mode='after')
    def span(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError('范围开始和结束日期必须成对填写')
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError('范围开始日期不能晚于结束日期')
            if (self.end_date - self.start_date).days > 120:
                raise ValueError('单次编排范围不超过 120 天')
        return self


# 一条草稿操作；before 只用于审阅展示，不作为执行依据。
class DraftOperation(Contract):
    op_id: str = Field(min_length=1, max_length=50)
    entity: Literal['project_task', 'shooting_item']
    action: Literal['add', 'update', 'cancel']
    target_id: str | None = Field(default=None, max_length=36)
    temp_id: str | None = Field(default=None, max_length=50)
    before: dict | None = None
    patch: dict = Field(default_factory=dict)
    reason: str = Field(default='', max_length=1000)

    # 新增用临时编号，修改和取消用正式 ID；取消不接受字段载荷。
    @model_validator(mode='after')
    def shape(self):
        if self.action == 'add':
            if not self.temp_id or self.target_id:
                raise ValueError('新增操作需要临时编号，不能指定正式 ID')
            if not self.patch:
                raise ValueError('新增操作需要完整字段')
        else:
            if not self.target_id or self.temp_id:
                raise ValueError('修改和取消需要正式 ID，不能指定临时编号')
            if self.action == 'cancel' and self.patch:
                raise ValueError('取消不接受字段载荷')
            if self.action == 'update' and not self.patch:
                raise ValueError('修改需要指定字段')
        return self


# 制片声明的目标及其处理状态；未知必须显式标记，不能缺省。
class CoverageItem(Contract):
    target: str = Field(min_length=1, max_length=100)
    status: Literal['addressed', 'done', 'not_applicable', 'unknown']
    reason: str = Field(default='', max_length=1000)


# 联合候选方案；origin 决定模型保护是否生效，manual 表示制片直接提交。
class Candidate(Contract):
    origin: Literal['manual', 'model'] = 'manual'
    operations: list[DraftOperation] = Field(default_factory=list, max_length=100)
    coverage: list[CoverageItem] = Field(default_factory=list, max_length=100)
    summary: str = Field(default='', max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    questions: list[str] = Field(default_factory=list, max_length=50)

    # 临时编号和操作编号在整份草稿内唯一，重复会让执行映射产生歧义。
    @model_validator(mode='after')
    def unique_ids(self):
        temps = [op.temp_id for op in self.operations if op.temp_id]
        ids = [op.op_id for op in self.operations]
        if len(set(ids)) != len(ids):
            raise ValueError('操作编号不能重复')
        if len(set(temps)) != len(temps):
            raise ValueError('临时编号不能重复')
        return self


# 发起一次工作；mode 为空时按首次编排处理。
class RunInput(Contract):
    mode: Literal['compose', 'reschedule'] | None = None
    message: str = Field(default='', max_length=4000)
    scope: Scope | None = None
    candidate: Candidate | None = None


# 恢复一次暂停的工作；expected_version 防止两个请求同时推进同一次工作。
class ResumeInput(Contract):
    expected_version: int = Field(ge=0)
    decision: Literal['provide_input', 'discard']
    message: str = Field(default='', max_length=4000)
    scope: Scope | None = None
    candidate: Candidate | None = None


# 人工修改草稿；revision 必须匹配，旧检查和旧确认随之失效。
class DraftEditInput(Contract):
    revision: int = Field(ge=0)
    candidate: Candidate


# 确认草稿；仍有未排场次时必须显式知情保留。
class DraftConfirmInput(Contract):
    revision: int = Field(ge=0)
    accept_uncovered: bool = False


# 放弃草稿。
class DraftDiscardInput(Contract):
    revision: int = Field(ge=0)


# 模型对要求的理解结果；范围仍受 Scope 约束，问题交制片补充。
class UnderstandResult(Contract):
    mode: Literal['compose', 'reschedule'] = 'compose'
    scope: Scope | None = None
    constraints: list[str] = Field(default_factory=list, max_length=30)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    questions: list[str] = Field(default_factory=list, max_length=10)
    reason: str = Field(default='', max_length=1000)


# 模型复核发现的问题；只描述偏差，不修改程序检查级别。
class ReviewFinding(Contract):
    kind: Literal['requirement', 'omission', 'unrelated', 'invented', 'explanation']
    message: str = Field(min_length=1, max_length=500)
    operation_ids: list[str] = Field(default_factory=list, max_length=20)
    needs_user: bool = False


# 复核结论：通过、可自行修正、需要制片决定。
class ReflectResult(Contract):
    verdict: Literal['ok', 'fixable', 'need_user'] = 'ok'
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=20)
    summary: str = Field(default='', max_length=1000)
