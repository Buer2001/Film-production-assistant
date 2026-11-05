# 文件职责：只增量创建 V5 三表并检查字段、外键和唯一约束，不改旧数据或清库。
from sqlalchemy import inspect
from backend.models.agent import AgentRun, AgentDraft, AgentExecution


# 按运行、草稿、凭据的顺序建表，后表外键依赖前表；随后逐表核对结构是否完整。
def upgrade(engine):
    with engine.begin() as connection:
        for table in (AgentRun.__table__, AgentDraft.__table__, AgentExecution.__table__):
            table.create(connection, checkfirst=True)
            inspector = inspect(connection)
            missing = set(table.columns.keys()) - {c['name'] for c in inspector.get_columns(table.name)}
            if missing:
                raise RuntimeError(f'{table.name} 缺少字段 {sorted(missing)}，请执行迁移，禁止清库替代')
            actual = {(tuple(f['constrained_columns']), f['referred_table']) for f in inspector.get_foreign_keys(table.name)}
            for fk in table.foreign_key_constraints:
                if (tuple(c.name for c in fk.columns), fk.referred_table.name) not in actual:
                    raise RuntimeError(f'{table.name} 缺少必要外键，请执行对应迁移')
        # 唯一执行凭据是重复确认的最后防线，缺失时不能只靠程序判断。
        unique = {tuple(u['column_names']) for u in inspect(connection).get_unique_constraints(AgentExecution.__tablename__)}
        if ('draft_id', 'draft_revision') not in unique:
            raise RuntimeError('agent_executions 缺少 (draft_id, draft_revision) 唯一约束，请执行迁移')
