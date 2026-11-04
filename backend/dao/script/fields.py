# 将项目拆解自定义字段保存在独立种类记录中，支持加锁读取。
from sqlalchemy import select
from backend.models.record import Record

KIND = 'script_fields'


# 按 pid 获取自定义字段记录；current=True 加锁刷新 session，返回记录或 None。
def get(session, pid, *, current=False):
    statement = select(Record).where(Record.project_id == pid, Record.kind == KIND)
    if current:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalar(statement)


# 按 pid 和 data 新建或替换 row 的字段载荷，修改 session；不提交，无返回值。
def save(session, pid, row, data):
    if row is None:
        session.add(Record(project_id=pid, kind=KIND, data=data))
    else:
        row.data = data
