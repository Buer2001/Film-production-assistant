"""V1 增量建表：只新增两张表，不推测或覆盖旧 records 数据。"""
from sqlalchemy import inspect
from backend.models.script import Script, SceneBreakdown


def upgrade(engine):
    tables = (Script.__table__, SceneBreakdown.__table__)
    with engine.begin() as connection:
        for table in tables:
            table.create(connection, checkfirst=True)
            # create(checkfirst=True) 不会升级旧列；结构不兼容时明确报错。
            actual = {column['name'] for column in inspect(connection).get_columns(table.name)}
            missing = set(table.columns.keys()) - actual
            if missing:
                raise RuntimeError(f'{table.name} 缺少字段 {sorted(missing)}，请先执行对应版本迁移，禁止清库替代')
