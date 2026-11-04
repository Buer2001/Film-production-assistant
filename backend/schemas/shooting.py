# 文件职责：定义安排、日志和通告补充信息，拒绝未知字段及含时区的本地时间。
from datetime import datetime, date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


# 校验成对的本地起止时间；日志允许均未录入，计划则由字段类型强制必填。
def check_times(start, end):
    if (start is None) != (end is None):
        raise ValueError('开始和结束时间必须成对填写')
    if start is not None:
        if start.tzinfo or end.tzinfo:
            raise ValueError('请使用本地日期时间')
        if end <= start:
            raise ValueError('结束时间必须晚于开始时间')


# 安排内的稳定 ID 用于身份及占用检查，场地文字和镜头数只用于人工说明及估时。
class ItemData(Contract):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal['shoot', 'transfer', 'meal', 'makeup', 'lighting', 'set', 'other'] = 'shoot'
    status: Literal['planned', 'cancelled'] = 'planned'
    start_at: datetime
    end_at: datetime
    scene_id: str | None = Field(default=None, min_length=1, max_length=36)
    person_ids: list[str] = Field(default_factory=list, max_length=100)
    resource_ids: list[str] = Field(default_factory=list, max_length=100)
    location: str = Field(default='', max_length=500)
    shots: int | None = Field(default=None, ge=0, le=10000)
    reshoot_log_id: str | None = Field(default=None, min_length=1, max_length=36)
    notes: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def valid(self):
        check_times(self.start_at, self.end_at)
        if self.kind == 'shoot' and not self.scene_id:
            raise ValueError('拍摄安排必须关联正式场次')
        if len(set(self.person_ids)) != len(self.person_ids) or len(set(self.resource_ids)) != len(self.resource_ids):
            raise ValueError('人员和资源不能重复选择')
        return self


# 完成情况属于本次实际结果，不等于宣布整个正式场次永久完成。
class LogData(Contract):
    scene_id: str = Field(min_length=1, max_length=36)
    item_id: str | None = Field(default=None, min_length=1, max_length=36)
    date: date
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    status: Literal['completed', 'partial', 'not_shot'] = 'completed'
    remaining: str = Field(default='', max_length=10000)
    reshoot_reason: str = Field(default='', max_length=10000)
    notes: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def valid(self):
        check_times(self.actual_start, self.actual_end)
        if self.actual_start and self.actual_start.date() != self.date:
            raise ValueError('日志日期应为实际开拍日期，结束时间可跨午夜')
        return self


class Revision(Contract):
    revision: int = Field(ge=0)


class ItemInput(Revision):
    item: ItemData


class LogInput(Revision):
    log: LogData


# 执行补充信息与计划分开，不借修改通告去静默调整正式安排。
class NoticeDetails(Contract):
    assembly: str = Field(default='', max_length=5000)
    makeup: str = Field(default='', max_length=5000)
    transport: str = Field(default='', max_length=5000)
    meals: str = Field(default='', max_length=5000)
    notes: str = Field(default='', max_length=10000)


class DraftInput(Revision):
    details: NoticeDetails


class PublishInput(DraftInput):
    fingerprint: str = Field(min_length=64, max_length=64)

