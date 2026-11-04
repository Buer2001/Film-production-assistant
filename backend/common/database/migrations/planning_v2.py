# 增量创建日程表并检查字段及项目唯一约束，避免带错表结构启动。
"""V2 增量建表；不修改旧表，不以清库替代升级。"""
from sqlalchemy import inspect
from backend.models.planning import ProjectPlan, ProjectTask


# 使用 engine 的事务连接增量建表并校验现存结构；缺字段或关键约束时抛 RuntimeError，无返回值。
def upgrade(engine):
    with engine.begin() as connection:
        for table in (ProjectPlan.__table__, ProjectTask.__table__):
            table.create(connection, checkfirst=True)
            actual = {c['name'] for c in inspect(connection).get_columns(table.name)}
            missing = set(table.columns.keys()) - actual
            if missing:
                raise RuntimeError(f'{table.name} 缺少字段 {sorted(missing)}，请执行对应迁移，禁止清库替代')
        inspector = inspect(connection)
        unique = inspector.get_unique_constraints('project_plans') + inspector.get_indexes('project_plans')
        if not any(x.get('column_names') == ['project_id'] and x.get('unique', True) for x in unique):
            raise RuntimeError('project_plans 缺少项目唯一约束，请先修复结构')
