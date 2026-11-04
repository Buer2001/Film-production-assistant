# 封装项目记录查询及单项操作落库，操作合法性由调用方先行校验。
from sqlalchemy import select
from backend.models.record import Record


# 用 s 查询 model 中 project_id 等于 pid 的全部行，返回对象列表。
def rows(s, model, pid):
    return s.scalars(select(model).where(model.project_id == pid)).all()


# 将已校验的 operation 应用于 pid 项目记录，支持删除、整体替换 data 和新建；修改 s，不提交也不再次检查归属。
def apply_operation(s, pid, operation):
    record = s.get(Record, operation['id']) if operation.get('id') else None
    if operation.get('delete'):
        s.delete(record)
    elif record:
        record.data = operation['data']
    else:
        s.add(Record(project_id=pid, kind=operation['kind'], data=operation['data']))
