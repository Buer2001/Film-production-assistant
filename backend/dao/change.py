"""草稿读写，不自行提交事务。"""
from sqlalchemy import update
from backend.models.change import Change


def get_change(s, cid):
    return s.get(Change, cid)


def add_change(s, **values):
    change = Change(**values)
    s.add(change)
    s.flush()
    return change


def claim_status(s, cid, status, pid=None):
    query = update(Change).where(Change.id == cid, Change.status == 'pending')
    if pid is not None:
        query = query.where(Change.project_id == pid)
    return s.execute(query.values(status=status)).rowcount
