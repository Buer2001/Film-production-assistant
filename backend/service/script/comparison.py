# 文件职责：对照前版生成场次差异，仅在原文完全一致时复用前版字段。
from copy import deepcopy
from backend.tools.script.matching import suggest
from backend.schemas.script import SceneData

FIELDS = tuple(SceneData.model_fields) + ('custom_values',)


# 用途：匹配唯一原文相同的前版场次。
# 参数：entries 为当前可变场次列表，previous 为前版列表。
# 返回及副作用：原地写入复用字段、人工标记及匹配状态后返回 entries；非唯一匹配保持 pending。
def apply_previous(entries, previous):
    used = set()
    for entry in entries:
        exact = [p for p in previous if p['evidence'].get('text') == entry['evidence']['text']
                 and p['id'] not in used]
        if len(exact) == 1:
            old = exact[0]
            # 仅原文完全一致才沿用人工修改；原始提取和证据保持可追溯。
            for key in FIELDS:
                entry[key] = deepcopy(old.get(key, {} if key == 'custom_values' else None))
            entry['evidence']['manual_fields'] = old['evidence'].get('manual_fields', [])
            entry.update(previous_scene_id=old['id'], match_status='matched', change_reviewed=False)
            used.add(old['id'])
        else:
            entry.update(previous_scene_id=None, match_status='pending', change_reviewed=False)
    return entries


# 用途：比较场次字段、原文及顺序。
# 参数：current/previous 为前后版场次，revised 表示有前版，deletions_reviewed 表示已核对删除。
# 返回及副作用：返回修改、新增、待匹配、未变及删除分类；尚未确认删除的旧场次放入 unlinked，不修改输入。
def compare(current, previous, revised, deletions_reviewed=False):
    old_map = {row['id']: row for row in previous}
    linked, changed, added, pending, unchanged = set(), [], [], [], []
    for index, row in enumerate(current):
        old = old_map.get(row['previous_scene_id'])
        if old:
            linked.add(old['id'])
            fields = [key for key in FIELDS if row.get(key) != old.get(key)]
            if row['evidence'].get('text') != old['evidence'].get('text'):
                fields.append('原文')
            if index != previous.index(old):
                fields.append('顺序')
            item = {'id': row['id'], 'scene_number': row['scene_number'], 'fields': fields,
                    'before': old, 'after': row, 'before_order': previous.index(old) + 1, 'after_order': index + 1}
            (changed if fields else unchanged).append(item)
        elif revised and row['match_status'] == 'pending':
            pending.append({'id': row['id'], 'candidates': suggest(row, previous)})
        else:
            added.append(row)
    unlinked = [row for row in previous if row['id'] not in linked]
    confirmed_deletions = revised and deletions_reviewed and not pending
    return {'changed': changed, 'added': added, 'pending': pending, 'unchanged': unchanged,
            'deleted': unlinked if confirmed_deletions else [],
            'unlinked': [] if confirmed_deletions else unlinked}
