"""事件追加及读取，不自行提交事务。"""
from backend.models.event import Event
from backend.dao.record import rows


def get_event(s, eid):
    return s.get(Event, eid)


def add_event(s, pid, event_type, data):
    event = Event(project_id=pid, type=event_type, data=data)
    s.add(event)
    return event


def list_events(s, pid):
    return rows(s, Event, pid)


def set_event_data(event, data):
    event.data = data
