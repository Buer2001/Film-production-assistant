# 读写项目，并通过条件更新提供项目串行化和版本检查。
"""项目的数据库访问；提交由业务服务决定。"""
from sqlalchemy import select, update
from backend.models.project import Project


# 用 s 按 pid 获取项目对象，不存在时返回 None。
def get_project(s, pid):
    return s.get(Project, pid)


# 用 s 返回全部项目对象列表，不额外排序。
def list_projects(s):
    return s.scalars(select(Project)).all()


# 以 name 创建项目并加入 s，返回对象；外层业务负责 flush/提交。
def add_project(s, name):
    project = Project(name=name)
    s.add(project)
    return project


# 按 pid 和 revision 条件更新项目；increment 决定是否递增版本，返回影响行数，不提交。
def claim_revision(s, pid, revision, *, increment=False):
    # 条件更新同时承担项目级串行化和乐观版本检查。
    return s.execute(update(Project).where(Project.id == pid, Project.revision == revision)
        .values(revision=Project.revision + 1 if increment else Project.revision)).rowcount


# 对 pid 执行保持版本不变的更新以取得数据库写锁；返回影响行数，锁随外层事务释放。
def lock_project(s, pid):
    return s.execute(update(Project).where(Project.id == pid).values(revision=Project.revision)).rowcount


