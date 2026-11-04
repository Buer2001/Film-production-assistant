# 持久化通告版本快照，版本分配和事务提交留给业务服务。
"""通告快照持久化，版本分配由服务层串行化。"""
from backend.models.notice import Notice
from sqlalchemy import select


# 用会话 s 按 nid 查询通告快照，返回对象或 None。
def get_notice(s, nid):
    return s.get(Notice, nid)


# 按 values 创建通告并加入会话 s，返回对象；不分配版本也不提交。
def add_notice(s, **values):
    notice = Notice(**values)
    s.add(notice)
    return notice


# version=0 专门承载 V4 当日执行信息草稿，不计入已发布通告；外层须先领取项目锁。
def get_draft(s, pid, day):
    return s.scalar(select(Notice).where(Notice.project_id == pid, Notice.date == day,
                                        Notice.version == 0).order_by(Notice.id))


# 分配版本和正式列表均排除草稿；与历史通告共享当天递增版本，避免同日版本重名。
def list_published(s, pid, day=None):
    statement = select(Notice).where(Notice.project_id == pid, Notice.version > 0)
    if day:
        statement = statement.where(Notice.date == day)
    return s.scalars(statement.order_by(Notice.date.desc(), Notice.version.desc())).all()


# 完整替换 JSON 使 SQLAlchemy 能检测变化；不更改正式历史通告。
def write_draft(s, pid, day, revision, details):
    draft = get_draft(s, pid, day)
    if draft is None:
        draft = add_notice(s, project_id=pid, date=day, version=0, revision=revision,
                           snapshot={'format': 'shooting_v4_draft', 'details': details})
    else:
        draft.revision = revision
        draft.snapshot = {'format': 'shooting_v4_draft', 'details': details}
    s.flush()
    return draft
