"""停服后执行：python -m scripts.migrate_planning。只补建 V2 两表。"""
import os
from pathlib import Path
from dotenv import load_dotenv
from backend.common.database.store import database, configured_url
from backend.common.database.migrations.script_v1 import upgrade as upgrade_scripts
from backend.common.database.migrations.planning_v2 import upgrade


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
