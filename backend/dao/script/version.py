from backend.dao.project import get_project as project, lock_project
from backend.dao.event import add_event
from sqlalchemy import select, update
from backend.models.script import Script


def list_versions(session, pid, *, current=False):
    statement = select(Script).where(Script.project_id == pid).order_by(Script.version_number.desc())
    if current:
        # MySQL可重复读下普通SELECT可能保留旧快照；修改校验必须使用当前读。
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalars(statement).all()


def get(session, pid, sid):
    return session.scalar(select(Script).where(Script.id == sid, Script.project_id == pid))


def add(session, **values):
    row = Script(**values)
    session.add(row)
    session.flush()
    return row


def claim(session, sid, revision):
    return session.execute(update(Script).where(Script.id == sid, Script.revision == revision)
                           .values(revision=Script.revision + 1)).rowcount == 1


def log(session, pid, action, data):
    add_event(session, pid, 'script_' + action, data)
