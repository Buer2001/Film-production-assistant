# 维护版本内有序场次，提供展示转换、字数计算和保留 ID 的整体替换。
from sqlalchemy import select
from backend.models.script import SceneBreakdown
from backend.tools.script.text import scene_word_count

SCALARS = ('scene_number', 'interior_exterior', 'atmosphere', 'location', 'summary', 'notes')
MULTIPLE = ('cast', 'makeup_costume', 'action_props', 'other_props', 'custom_values')


# 用 session 返回 sid 版本的场次列表，按 sort_order 排序。
def list_for_script(session, sid):
    return session.scalars(select(SceneBreakdown).where(SceneBreakdown.script_id == sid)
                           .order_by(SceneBreakdown.sort_order)).all()


# 从 row 提取业务展示字段并按原文计算 word_count；返回字典，忽略历史 page_count。
def data(row):
    raw = row.evidence.get('text', '')
    return {**{key: getattr(row, key) for key in SCALARS},
            **{key: value for key, value in row.details.items() if key != 'page_count'},
            'word_count': scene_word_count(raw) if raw else None,
            'custom_values': row.details.get('custom_values') or {}}


# 将 row 转为含 ID、版本匹配信息、证据和审阅问题的场次字典。
def as_dict(row):
    return {'id': row.id, **data(row), 'previous_scene_id': row.previous_scene_id,
            'match_status': row.match_status, 'change_reviewed': row.change_reviewed,
            'evidence': row.evidence, 'extracted_data': row.extracted_data, 'review_issues': row.review_issues}


# 用 entries 整体替换 sid 的场次并保留已有 ID；先暂移排序再 flush，最后删除未保留项，不提交 session。
def replace(session, sid, entries):
    """保留仍存在的场次 ID；先腾出排序位置，避免唯一约束中途冲突。"""
    current = {r.id: r for r in list_for_script(session, sid)}
    # 先将现有排序移至负数区间并 flush，避免新旧正数位置交换时触发唯一约束。
    for i, row in enumerate(current.values()):
        row.sort_order = -(i + 1)
    session.flush()
    keep = set()
    for order, entry in enumerate(entries):
        rid = entry.get('id')
        row = current[rid] if rid in current else SceneBreakdown(script_id=sid, **({"id": rid} if rid else {}))
        for key in SCALARS:
            setattr(row, key, entry.get(key, ''))
        row.details = {key: (entry.get(key) or {}) if key == 'custom_values' else entry.get(key) for key in MULTIPLE}
        raw = entry.get('evidence', {}).get('text', '')
        row.details['word_count'] = scene_word_count(raw) if raw else None
        for key in ('previous_scene_id', 'match_status', 'change_reviewed', 'evidence', 'extracted_data', 'review_issues'):
            if key in entry:
                setattr(row, key, entry[key])
        row.sort_order = order
        session.add(row)
        if rid:
            keep.add(rid)
    # 整体替换的删除范围仅限当前版本；其他剧本版本的场次保持独立。
    for rid, row in current.items():
        if rid not in keep:
            session.delete(row)
    session.flush()


# 用 session 查询 ids 中实际存在的场次 ID，返回集合；空输入直接返回空集合。
def existing_ids(session, ids):
    return set(session.scalars(select(SceneBreakdown.id).where(SceneBreakdown.id.in_(ids))).all()) if ids else set()
