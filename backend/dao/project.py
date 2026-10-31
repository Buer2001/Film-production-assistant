"""项目的数据库访问；提交由业务服务决定。"""
from sqlalchemy import select, update
from backend.models.project import Project


def get_project(s, pid):
    return s.get(Project, pid)


def list_projects(s):
    return s.scalars(select(Project)).all()


def add_project(s, name):
    project = Project(name=name)
    s.add(project)
    return project


def claim_revision(s, pid, revision, *, increment=False):
    # 条件更新同时承担项目级串行化和乐观版本检查。
    return s.execute(update(Project).where(Project.id == pid, Project.revision == revision)
        .values(revision=Project.revision + 1 if increment else Project.revision)).rowcount


def lock_project(s, pid):
    return s.execute(update(Project).where(Project.id == pid).values(revision=Project.revision)).rowcount


