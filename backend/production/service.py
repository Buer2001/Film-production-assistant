from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, update
from backend.common.database.store import Project, Record, Change, Notice, Event
from backend.production.scheduling.checks import check_schedule


def rows(s, model, pid):
    return s.scalars(select(model).where(model.project_id == pid)).all()


def get_project(s, pid):
    p = s.get(Project, pid)
    if not p:
        raise HTTPException(404, '项目不存在')
    return p


def record_dict(r):
    return {'id': r.id, 'kind': r.kind, 'data': r.data}


def change_dict(c):
    return {k: getattr(c, k) for k in ('id', 'base_revision', 'reason', 'operations', 'before', 'status', 'created_at')}


def state(s, pid):
    p = get_project(s, pid)
    records = [record_dict(r) for r in rows(s, Record, pid)]
    notices = [{'id': n.id, 'date': n.date, 'version': n.version, 'revision': n.revision,
                'snapshot': n.snapshot, 'created_at': n.created_at, 'stale': n.revision != p.revision}
               for n in rows(s, Notice, pid)]
    return {'id': p.id, 'name': p.name, 'revision': p.revision, 'records': records,
            'changes': [change_dict(c) for c in rows(s, Change, pid)], 'notices': notices,
            'checks': check_schedule(records),
            'totals': {category: str(sum((Decimal(r['data']['amount']) for r in records
                if r['kind'] == 'expense' and r['data']['category'] == category), Decimal(0)))
                for category in ('预算', '报价', '已确定', '实际支出')}}


def validate_operations(s, pid, operations):
    current = {r.id: r for r in rows(s, Record, pid)}
    before, seen = [], set()
    for op in operations:
        if op['kind'] == 'expense' and not op.get('delete') and (op.get('data') or {}).get('category') not in ('预算', '报价', '已确定', '实际支出'):
            raise HTTPException(422, '费用分类必须为预算、报价、已确定或实际支出')
        rid = op.get('id')
        if rid:
            if rid in seen or rid not in current or current[rid].kind != op['kind']:
                raise HTTPException(422, '修改对象不存在、类型不符或重复')
            seen.add(rid)
        if (op.get('delete') and not rid) or (not op.get('delete') and not op.get('data')):
            raise HTTPException(422, '修改或删除缺少必要信息')
        before.append(record_dict(current[rid]) if rid else None)
    deleted = {o['id'] for o in operations if o.get('delete')}
    final = {rid: record_dict(r) for rid, r in current.items() if rid not in deleted}
    for i, op in enumerate(operations):
        if not op.get('delete'):
            final[op.get('id') or f'new-{i}'] = {'kind': op['kind'], 'data': op['data']}
    for r in final.values():
        for scene in r['data'].get('scene_ids', []):
            if scene not in final or final[scene]['kind'] != 'scene':
                raise HTTPException(422, '关联场次不存在，或删除后仍被引用')
    return before


def propose(s, pid, request, *, commit=True):
    p = get_project(s, pid)
    if p.revision != request.base_revision:
        raise HTTPException(409, '数据已更新，请刷新后重新生成修改')
    operations = [o.model_dump(mode='json') for o in request.operations]
    before = validate_operations(s, pid, operations)
    c = Change(project_id=pid, base_revision=p.revision, reason=request.reason,
               operations=operations, before=before)
    s.add(c)
    s.flush()
    if commit:
        s.commit()
    return change_dict(c)


def confirm(s, pid, cid):
    c = s.get(Change, cid)
    if not c or c.project_id != pid:
        raise HTTPException(404, '修改草稿不存在')
    if c.status == 'confirmed':
        return change_dict(c)
    if c.status != 'pending':
        raise HTTPException(409, '草稿已取消')
    # Project-wide compare-and-swap keeps one producer's edits atomic across devices.
    updated = s.execute(update(Project).where(Project.id == pid, Project.revision == c.base_revision)
                        .values(revision=Project.revision + 1))
    if updated.rowcount != 1:
        s.rollback()
        s.refresh(c)
        if c.status == 'confirmed':
            return change_dict(c)
        raise HTTPException(409, '版本已变化，请重新检查修改')
    claimed = s.execute(update(Change).where(Change.id == cid, Change.status == 'pending')
                        .values(status='confirmed'))
    if claimed.rowcount != 1:
        s.rollback()
        raise HTTPException(409, '草稿已被其他操作处理，请刷新')
    validate_operations(s, pid, c.operations)
    for op in c.operations:
        r = s.get(Record, op['id']) if op.get('id') else None
        if op.get('delete'):
            s.delete(r)
        elif r:
            r.data = op['data']
        else:
            s.add(Record(project_id=pid, kind=op['kind'], data=op['data']))
    s.add(Event(project_id=pid, type='change', data={'change_id': c.id, 'reason': c.reason,
        'before': c.before, 'operations': c.operations, 'revision': c.base_revision + 1}))
    s.commit()
    return change_dict(c)


def publish(s, pid, request):
    # Lock/CAS the project row so notice versions serialize with project changes.
    result = s.execute(update(Project).where(Project.id == pid, Project.revision == request.base_revision)
                       .values(revision=Project.revision))
    if result.rowcount != 1:
        s.rollback()
        raise HTTPException(409, '计划版本已变化，请刷新')
    snapshot = state(s, pid)
    day = request.date.isoformat()
    versions = [n.version for n in rows(s, Notice, pid) if n.date == day]
    slots = [r for r in snapshot['records'] if r['kind'] == 'schedule' and r['data']['date'] == day]
    slots.sort(key=lambda r: r['data']['start'] or '')
    notice = Notice(project_id=pid, date=day, version=max(versions, default=0) + 1,
        revision=request.base_revision, snapshot={'project': snapshot['name'], 'schedule': slots,
            'records': snapshot['records'], 'checks': snapshot['checks'], 'notes': request.notes})
    s.add(notice)
    s.commit()
    return {'id': notice.id, 'date': day, 'version': notice.version, 'snapshot': notice.snapshot}
