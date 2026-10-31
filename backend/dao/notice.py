"""通告快照持久化，版本分配由服务层串行化。"""
from backend.models.notice import Notice


def get_notice(s, nid):
    return s.get(Notice, nid)


def add_notice(s, **values):
    notice = Notice(**values)
    s.add(notice)
    return notice
