"""离线执行：先备份，按原文迁移details与文件草稿；不调用模型。"""
from copy import deepcopy
from pathlib import Path
import json

from sqlalchemy import select
from backend.models.script import SceneBreakdown
from backend.tools.script.text import scene_word_count, refresh_scene_metadata


# 用途：递归整理草稿中的场次元数据，并移除旧 page_count 字段配置。
# 参数：value 为草稿中的字典或列表；返回：无，直接修改传入对象。
# 场次字数依据原文 evidence 重新计算，不调用模型或覆盖人工自定义值。
def normalize_draft(value):
    if isinstance(value, dict):
        if isinstance(value.get('evidence'), dict):
            refresh_scene_metadata(value)
        for key, child in value.items():
            if key == 'fields' and isinstance(child, list):
                value[key] = [field for field in child if field != 'page_count']
            else:
                normalize_draft(child)
    elif isinstance(value, list):
        for child in value:
            normalize_draft(child)


# 用途：将正式拆解和文件草稿从页数迁移为按原文字数统计，先备份再写入。
# 参数：session 为数据库会话；store 为草稿存储；backup_dir 为新建备份目录。
# 返回：database_rows、draft_files 两类实际变更数量；无变更时不创建备份。
# 副作用：锁定并更新正式记录、写草稿和备份、提交事务；运行中的草稿拒绝迁移。
# 异常：写入失败时回滚数据库并尝试恢复已写文件；恢复不全时报告备份路径。
def migrate(session, store, backup_dir):
    rows, drafts = [], []
    for row in session.scalars(select(SceneBreakdown).order_by(SceneBreakdown.script_id, SceneBreakdown.sort_order).with_for_update()).all():
        raw = (row.evidence or {}).get('text', '')
        details = {key: value for key, value in (row.details or {}).items() if key != 'page_count'}
        details['word_count'] = scene_word_count(raw) if raw else None
        if details != row.details:
            rows.append((row, deepcopy(row.details), details))
    for path in store.directory.glob('*.json'):
        original = path.read_bytes()
        doc = json.loads(original)
        if not all(key in doc for key in ('id', 'project_id', 'scenes')):
            continue
        if store._path(doc['project_id'], doc['id']) != path:
            raise ValueError('草稿文件标识不符，未执行迁移')
        if doc.get('progress', {}).get('state') == 'running':
            raise ValueError('存在运行中的拆解任务，未执行迁移')
        updated = deepcopy(doc)
        normalize_draft(updated)
        if updated != doc:
            drafts.append((path, original, doc, updated))
    if not rows and not drafts:
        session.rollback()
        return {'database_rows': 0, 'draft_files': 0}
    # 全部待迁移内容检查完毕后才创建备份，避免半途发现不安全状态。
    backup = Path(backup_dir)
    backup.mkdir(parents=True, exist_ok=False)
    (backup / 'database.json').write_text(json.dumps(
        [{'id': row.id, 'script_id': row.script_id, 'details': original} for row, original, _ in rows],
        ensure_ascii=False, indent=2), encoding='utf-8')
    for path, original, _, _ in drafts:
        (backup / path.name).write_bytes(original)
    # 数据库和文件不在同一事务中，因此单独记录已成功写入的文件以便补偿。
    written = []
    try:
        for row, _, details in rows:
            row.details = details
        session.flush()
        for path, _, original, updated in drafts:
            store.write(original['project_id'], original['id'], updated)
            written.append(original)
        session.commit()
    except Exception as exc:
        # 即使某一项恢复失败，也继续恢复其他文件，最后集中报告失败项。
        failures = []
        try:
            session.rollback()
        except Exception:
            failures.append('数据库回滚')
        for original in written:
            try:
                store.write(original['project_id'], original['id'], original)
            except Exception:
                failures.append(store._path(original['project_id'], original['id']).name)
        if failures:
            raise RuntimeError(f'迁移失败，部分自动恢复失败：{", ".join(failures)}；原始备份：{backup.resolve()}') from exc
        raise
    return {'database_rows': len(rows), 'draft_files': len(drafts)}


if __name__ == '__main__':
    # 命令行入口：加载本地配置，使用时间戳区分每次备份，打印变更数量。
    from datetime import datetime, timezone
    from dotenv import load_dotenv
    from backend.common.database.store import database, configured_url
    from backend.tools.script.draft_store import DraftStore
    load_dotenv()
    backup = Path('.drafts/backups') / ('word-counts-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    engine, sessions = database(configured_url())
    try:
        with sessions() as session:
            result = migrate(session, DraftStore(), backup)
        print(json.dumps({**result, 'backup': str(backup.resolve()) if any(result.values()) else None}, ensure_ascii=False))
    finally:
        engine.dispose()
