# 文件职责：给 V5 检查结果分级并计算范围漏排；只处理传入数据，不查库、不调模型。
"""检查结果分级与漏排计算；未知信息按缺口处理，不能当作通过。"""
BLOCK = 'block'
CONFLICT = 'conflict'
GAP = 'gap'

# 阻断项表示数据无效或越权，修正前不能提交；冲突项需要先改方案；缺口允许知情保留。
BLOCK_CODES = frozenset({'task_invalid', 'item_invalid', 'personnel_forbidden', 'unknown_temp_ref',
                         'duplicate_operation', 'service_unavailable'})
CONFLICT_CODES = frozenset({'person_overlap', 'resource_overlap', 'time_unavailable',
                            'time_outside_available', 'constraint_violated',
                            'dependency_start_before', 'dependency_end_before'})
# 其余问题一律按缺口处理，包括未知可用时间、准备未完成和未安排的场次。
GAP_CODES = frozenset({'person_ids_unknown', 'resource_ids_unknown', 'availability_unknown',
                       'resource_pending', 'preparation_unfinished', 'resource_not_assigned',
                       'usage_unknown', 'people_unresolved', 'people_unlinked', 'person_missing',
                       'resource_unresolved', 'resource_missing', 'resource_unavailable',
                       'result_missing', 'due_unknown', 'overdue_or_past', 'milestone_missing',
                       'constraint_pending', 'scope_uncovered', 'out_of_scope_change',
                       'reference_missing', 'no_change'})


# 按问题代码取级别；未知代码按缺口处理，避免把没识别的问题当成通过。
def level_of(code):
    if code in BLOCK_CODES:
        return BLOCK
    if code in CONFLICT_CODES:
        return CONFLICT
    return GAP


# 组装一条检查问题；对象标识用于界面定位，evidence 保存来源或规则依据。
def issue(code, message, *, level=None, task_id=None, item_id=None, scene_id=None, evidence=None):
    return {'code': code, 'level': level or level_of(code), 'message': message,
            'task_id': task_id, 'item_id': item_id, 'scene_id': scene_id,
            'evidence': evidence or ''}


# 转换既有纯规则提醒为统一问题；提醒可能没有代码，此时按缺口记录。
def from_warning(warning):
    return issue(warning.get('code') or 'preparation_gap', warning.get('message', ''),
                 task_id=warning.get('task_id'), item_id=warning.get('item_id'))


# 汇总问题：去重后按阻断、冲突、缺口排序，便于界面先显示必须处理的部分。
def normalize(issues):
    order = {BLOCK: 0, CONFLICT: 1, GAP: 2}
    seen, unique = set(), []
    for item in issues:
        key = (item['code'], item.get('task_id'), item.get('item_id'), item.get('scene_id'), item['message'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return sorted(unique, key=lambda item: order[item['level']])


# 判断是否存在阻断项；模型不得自行降低级别，因此只看程序结果。
def blocked(issues):
    return any(item['level'] == BLOCK for item in issues)


# 计算范围内未安排的场次；planned 为已排或候选已排的场次 ID 集合。
def uncovered_scenes(confirmed_scenes, planned):
    return [{'scene_id': scene['id'], 'scene_number': scene['scene_number'],
             'location': scene.get('location', '')}
            for scene in confirmed_scenes if scene['id'] not in planned]
