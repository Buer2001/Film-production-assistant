from sqlalchemy import select
from backend.models.script import SceneBreakdown

SCALARS = ('scene_number', 'interior_exterior', 'atmosphere', 'location', 'summary', 'notes')
MULTIPLE = ('page_count', 'cast', 'makeup_costume', 'action_props', 'other_props')


def list_for_script(session, sid):
    return session.scalars(select(SceneBreakdown).where(SceneBreakdown.script_id == sid)
                           .order_by(SceneBreakdown.sort_order)).all()


def data(row):
    return {**{key: getattr(row, key) for key in SCALARS}, **row.details}


def as_dict(row):
    return {'id': row.id, **data(row), 'previous_scene_id': row.previous_scene_id,
            'match_status': row.match_status, 'change_reviewed': row.change_reviewed,
            'evidence': row.evidence, 'extracted_data': row.extracted_data, 'review_issues': row.review_issues}


def replace(session, sid, entries):
    """保留仍存在的场次 ID；先腾出排序位置，避免唯一约束中途冲突。"""
    current = {r.id: r for r in list_for_script(session, sid)}
    for i, row in enumerate(current.values()):
        row.sort_order = -(i + 1)
    session.flush()
    keep = set()
    for order, entry in enumerate(entries):
        rid = entry.get('id')
        row = current[rid] if rid in current else SceneBreakdown(script_id=sid, **({"id": rid} if rid else {}))
        for key in SCALARS:
            setattr(row, key, entry.get(key, ''))
        row.details = {key: entry.get(key) for key in MULTIPLE}
        for key in ('previous_scene_id', 'match_status', 'change_reviewed', 'evidence', 'extracted_data', 'review_issues'):
            if key in entry:
                setattr(row, key, entry[key])
        row.sort_order = order
        session.add(row)
        if rid:
            keep.add(rid)
    for rid, row in current.items():
        if rid not in keep:
            session.delete(row)
    session.flush()


def existing_ids(session, ids):
    return set(session.scalars(select(SceneBreakdown.id).where(SceneBreakdown.id.in_(ids))).all()) if ids else set()
