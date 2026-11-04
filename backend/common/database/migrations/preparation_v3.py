# 增量创建人员表并检查字段，不覆盖历史资源资料。
"""V3 仅增量创建人员表，不改写历史资源。"""
from sqlalchemy import inspect
from backend.models.person import ProjectPerson


# 使用 engine 的事务连接增量建表并校验现存列名；缺字段时抛 RuntimeError，无返回值。
def upgrade(engine):
    with engine.begin() as connection:
        table = ProjectPerson.__table__
        table.create(connection, checkfirst=True)
        actual = {c['name'] for c in inspect(connection).get_columns(table.name)}
        missing = set(table.columns.keys()) - actual
        if missing:
            raise RuntimeError(f'project_people 缺少字段 {sorted(missing)}，禁止清库替代迁移')
