# 文件职责：只增量创建 V4 两表并检查关键字段和外键，不更改旧数据或清库。
from sqlalchemy import inspect
from backend.models.shooting import ShootingItem, ShootingLog


# 创建顺序先安排后日志；补拍来源保存在经服务校验的 JSON，避免循环建表外键。
def upgrade(engine):
    with engine.begin() as connection:
        for table in (ShootingItem.__table__, ShootingLog.__table__):
            table.create(connection, checkfirst=True)
            inspector = inspect(connection)
            missing = set(table.columns.keys()) - {c['name'] for c in inspector.get_columns(table.name)}
            if missing:
                raise RuntimeError(f'{table.name} 缺少字段 {sorted(missing)}，请执行迁移，禁止清库替代')
            actual = {(tuple(f['constrained_columns']), f['referred_table']) for f in inspector.get_foreign_keys(table.name)}
            for fk in table.foreign_key_constraints:
                if (tuple(c.name for c in fk.columns), fk.referred_table.name) not in actual:
                    raise RuntimeError(f'{table.name} 缺少必要外键，请执行对应迁移')
