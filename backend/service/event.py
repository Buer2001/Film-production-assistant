from backend.service.project import get_project
from backend.dao import event as dao


def list_events(s, pid):
    get_project(s, pid)
    return [{'id': event.id, 'type': event.type, 'data': event.data, 'created_at': event.created_at}
            for event in sorted(dao.list_events(s, pid), key=lambda event: event.created_at, reverse=True)[:100]]


def save_chat(s, pid, data):
    # 一次对话仅在最终回答生成后记录；工具草稿各自保留原有提交边界。
    dao.add_event(s, pid, 'chat', data)
    s.commit()
