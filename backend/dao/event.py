# 追加和读取项目事件，供历史审计、会话和业务确认记录复用。
"""事件追加及读取，不自行提交事务。"""
from backend.models.event import Event
from backend.dao.record import rows


# 用 s 按 eid 获取事件，返回对象或 None。
def get_event(s, eid):
    return s.get(Event, eid)


# 为 pid 创建 event_type 类型、data 载荷的事件并加入 s，返回待持久化对象；不提交。
def add_event(s, pid, event_type, data):
    event = Event(project_id=pid, type=event_type, data=data)
    s.add(event)
    return event


# 按 pid 返回项目事件列表；s 为调用方管理的会话。
def list_events(s, pid):
    return rows(s, Event, pid)


# 用 data 整体替换 event 的 JSON 载荷；依赖外层会话提交，无返回值。
def set_event_data(event, data):
    event.data = data
