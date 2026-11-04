# 查询和新增剧本版本，提供 revision 条件更新及版本事件记录。
from backend.dao.project import get_project as project, lock_project
from backend.dao.event import add_event
from sqlalchemy import select, update
from backend.models.script import Script


# 按 pid 返回倒序版本列表；current=True 使用加锁当前读，避免校验旧快照。
def list_versions(session, pid, *, current=False):
    statement = select(Script).where(Script.project_id == pid).order_by(Script.version_number.desc())
    if current:
        # MySQL可重复读下普通SELECT可能保留旧快照；修改校验必须使用当前读。
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalars(statement).all()


# 按 pid/sid 查询本项目剧本版本，返回对象或 None。
def get(session, pid, sid):
    return session.scalar(select(Script).where(Script.id == sid, Script.project_id == pid))


# 按 values 创建版本并加入 session，flush 后返回对象；不提交。
def add(session, **values):
    row = Script(**values)
    session.add(row)
    session.flush()
    return row


# 按 sid/revision 条件递增剧本版本，返回是否成功，供外层并发检查。
def claim(session, sid, revision):
    return session.execute(update(Script).where(Script.id == sid, Script.revision == revision)
                           .values(revision=Script.revision + 1)).rowcount == 1


# 为 pid 追加 script_ 前缀 action 事件，载荷为 data；不提交 session，无返回值。
def log(session, pid, action, data):
    add_event(session, pid, 'script_' + action, data)
