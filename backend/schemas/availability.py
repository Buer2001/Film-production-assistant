# 约束人员和资源的本地使用时段及可用状态，禁止不完整或倒置区间。
"""人员和资源共享的时间段契约，集中校验日期和时刻边界。"""
from datetime import date, time, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator


# 闭区间日期和可选成对本地时刻；含时刻时要求整体结束时间严格晚于开始。
class UsagePeriod(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_date: date
    end_date: date
    start_time: time | None = None
    end_time: time | None = None

    # 校验当前对象的日期、时刻组合；不合法抛 ValueError，通过后返回 self。
    @model_validator(mode='after')
    def valid_period(self):
        # 日期为闭区间；没有时刻表示整天，不能只提交半个时刻。
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError('开始和结束时刻必须成对填写')
        if self.end_date < self.start_date:
            raise ValueError('结束日期不能早于开始日期')
        if self.start_time is not None:
            if self.start_time.tzinfo or self.end_time.tzinfo:
                raise ValueError('请使用本地时刻')
            if datetime.combine(self.end_date, self.end_time) <= datetime.combine(self.start_date, self.start_time):
                raise ValueError('结束时间必须晚于开始时间')
        return self


# 继承合法时段，state 明确表示可用或不可用，供人员和资源共同使用。
class Availability(UsagePeriod):
    state: Literal['available', 'unavailable']
