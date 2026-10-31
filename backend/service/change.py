from backend.dao.record import apply_operation
from backend.common.errors import BusinessError
from backend.models.record import Record
from backend.service.project import get_project, rows, record_dict, change_dict
from backend.dao import project as project_dao
from backend.dao import change as dao
from backend.dao.event import add_event


def validate_operations(s, pid, operations):
    current = {r.id: r for r in rows(s, Record, pid)}
    before, seen = [], set()
    for op in operations:
        if op['kind'] == 'expense' and not op.get('delete') and (op.get('data') or {}).get('category') not in ('预算', '报价', '已确定', '实际支出'):
            raise BusinessError(422, '费用分类必须为预算、报价、已确定或实际支出')
        rid = op.get('id')
        if rid:
            if rid in seen or rid not in current or current[rid].kind != op['kind']:
                raise BusinessError(422, '修改对象不存在、类型不符或重复')
            seen.add(rid)
        if (op.get('delete') and not rid) or (not op.get('delete') and not op.get('data')):
            raise BusinessError(422, '修改或删除缺少必要信息')
        before.append(record_dict(current[rid]) if rid else None)
    deleted = {o['id'] for o in operations if o.get('delete')}
    final = {rid: record_dict(r) for rid, r in current.items() if rid not in deleted}
    for i, op in enumerate(operations):
        if not op.get('delete'):
            final[op.get('id') or f'new-{i}'] = {'kind': op['kind'], 'data': op['data']}
    for r in final.values():
        for scene in r['data'].get('scene_ids', []):
            if scene not in final or final[scene]['kind'] != 'scene':
                raise BusinessError(422, '关联场次不存在，或删除后仍被引用')
    return before


def propose(s, pid, request, *, commit=True):
    p = get_project(s, pid)
    if p.revision != request.base_revision:
        raise BusinessError(409, '数据已更新，请刷新后重新生成修改')
    operations = [o.model_dump(mode='json') for o in request.operations]
    before = validate_operations(s, pid, operations)
    c = dao.add_change(s, project_id=pid, base_revision=p.revision, reason=request.reason,
               operations=operations, before=before)
    if commit:
        s.commit()
    return change_dict(c)


def confirm(s, pid, cid):
    c = dao.get_change(s, cid)
    if not c or c.project_id != pid:
        raise BusinessError(404, '修改草稿不存在')
    if c.status == 'confirmed':
        return change_dict(c)
    if c.status != 'pending':
        raise BusinessError(409, '草稿已取消')
    # 草稿确认和正式记录修改在同一事务内，先原子领取项目版本。
    updated = project_dao.claim_revision(s, pid, c.base_revision, increment=True)
    if updated != 1:
        s.rollback()
        s.refresh(c)
        if c.status == 'confirmed':
            return change_dict(c)
        raise BusinessError(409, '版本已变化，请重新检查修改')
    claimed = dao.claim_status(s, cid, 'confirmed')
    if claimed != 1:
        s.rollback()
        raise BusinessError(409, '草稿已被其他操作处理，请刷新')
    validate_operations(s, pid, c.operations)
    for op in c.operations:
        apply_operation(s, pid, op)
    add_event(s, pid, 'change', {'change_id': c.id, 'reason': c.reason,
        'before': c.before, 'operations': c.operations, 'revision': c.base_revision + 1})
    s.commit()
    return change_dict(c)


def reject(s, pid, cid):
    change = dao.get_change(s, cid)
    if not change or change.project_id != pid:
        raise BusinessError(404, '草稿不存在')
    if change.status != 'pending':
        raise BusinessError(409, '草稿已处理')
    if dao.claim_status(s, cid, 'rejected', pid) != 1:
        s.rollback()
        raise BusinessError(409, '草稿已处理，请刷新')
    s.commit()
    return {'status': 'rejected'}
