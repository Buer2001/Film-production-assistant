"""停服后执行：python -m scripts.migrate_planning。只补建 V2 两表。"""
import os
from pathlib import Path
from dotenv import load_dotenv
from backend.common.database.store import database, configured_url
from backend.common.database.migrations.script_v1 import upgrade as upgrade_scripts
from backend.common.database.migrations.planning_v2 import upgrade


# 用途：读取项目配置，按顺序检查并补建剧本和 V2 计划相关表。
# 参数：无；返回：无。会连接配置的数据库，迁移失败时向上抛出异常。
# 必须停服执行；不生成业务任务，结束时释放数据库连接池。
def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / '.env')
    os.chdir(root)
    engine, _ = database(configured_url())
    try:
        upgrade_scripts(engine)
        upgrade(engine)
        print('V2 计划及任务表结构检查通过；原有数据保留。')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
