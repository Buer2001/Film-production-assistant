from sqlalchemy import select
from backend.models.record import Record


def rows(s, model, pid):
    return s.scalars(select(model).where(model.project_id == pid)).all()


def apply_operation(s, pid, operation):
    record = s.get(Record, operation['id']) if operation.get('id') else None
    if operation.get('delete'):
        s.delete(record)
    elif record:
        record.data = operation['data']
    else:
        s.add(Record(project_id=pid, kind=operation['kind'], data=operation['data']))
