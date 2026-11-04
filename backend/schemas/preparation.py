# 定义筹备检查报告及关联问题，不将推断内容持久化为事实。
"""筹备检查仅返回已有事实的提示，不持久化第二套状态。"""
from pydantic import BaseModel


# 单项筹备提示，code/message 描述规则，task_id 及可选人员/资源 ID 用于定位。
class PreparationIssue(BaseModel):
    code: str
    message: str
    task_id: str
    resource_id: str | None = None
    person_id: str | None = None


# 返回问题列表及实际检查任务数，不额外创建筹备状态。
class PreparationReport(BaseModel):
    issues: list[PreparationIssue]
    checked_tasks: int
