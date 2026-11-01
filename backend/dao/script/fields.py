from sqlalchemy import select
from backend.models.record import Record

KIND = 'script_fields'


def get(session, pid, *, current=False):
    statement = select(Record).where(Record.project_id == pid, Record.kind == KIND)
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalar(statement)


def save(session, pid, row, data):
    if row is None:
        session.add(Record(project_id=pid, kind=KIND, data=data))
    else:
        row.data = data
