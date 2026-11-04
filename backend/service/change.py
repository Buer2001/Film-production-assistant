# 文件职责：校验通用变更草稿，并在明确确认后应用正式记录及事件。
from backend.dao.record import apply_operation
from backend.common.errors import BusinessError
from backend.models.record import Record
from backend.service.project import get_project, rows, record_dict, change_dict
from backend.dao import project as project_dao
from backend.dao import change as dao
from backend.dao.event import add_event
from backend.dao import resource as resources


# 用途：校验整批操作和应用后的场次引用。
# 参数：s/pid 为会话及项目，operations 为可变操作列表。
# 返回及副作用：返回逐项原始快照；补全未提供的资源落实资料，非法引用或字段抛 BusinessError，不提交。
def validate_operations(s, pid, operations):
    current = {r.id: r for r in rows(s, Record, pid)}
    before, seen = [], set()
    for op in operations:
        # 旧任务只保留读取；同时拦住通用接口、Agent及升级前遗留草稿的确认。
        if op['kind'] == 'task':
            raise BusinessError(422, '筹备任务已统一到项目日程，请在项目日程维护；旧草稿可取消')
        if op['kind'] == 'resource' and op.get('delete') and resources.referenced(s, pid, op.get('id')):
            raise BusinessError(422, '资源仍被正式日程或待确认草稿引用，请先解除关联')
        if op['kind'] == 'expense' and not op.get('delete') and (op.get('data') or {}).get('category') not in ('预算', '报价', '已确定', '实际支出'):
            raise BusinessError(422, '费用分类必须为预算、报价、已确定或实际支出')
        rid = op.get('id')
        if rid:
            if rid in seen or rid not in current or current[rid].kind != op['kind']:
                raise BusinessError(422, '修改对象不存在、类型不符或重复')
            seen.add(rid)
        if (op.get('delete') and not rid) or (not op.get('delete') and not op.get('data')):
            raise BusinessError(422, '修改或删除缺少必要信息')
        if op['kind'] == 'resource' and not op.get('delete'):
            data = op['data']
            if rid and 'preparation' not in data and 'preparation' in current[rid].data:
                data['preparation'] = current[rid].data['preparation']
            contact_id = (data.get('preparation') or {}).get('contact_person_id')
            if contact_id:
                from backend.dao.person import get_person
                if get_person(s, pid, contact_id) is None:
                    raise BusinessError(422, '资源联系人不存在或不属于本项目')
        before.append(record_dict(current[rid]) if rid else None)
    # 先构造整批操作后的最终集合再查引用，使同批解除关联和删除可以一起验证。
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


# 用途：创建待确认变更草稿。
# 参数：request 含基准版本、原因及操作，commit 控制立即提交。
# 返回及副作用：项目锁内校验版本和操作后返回草稿字典；commit=False 留给调用者提交，冲突抛 BusinessError。
def propose(s, pid, request, *, commit=True):
    p = get_project(s, pid)

    # 与日程写入采用相同的项目→计划锁顺序，避免资源删除和任务关联竞态。
    project_dao.lock_project(s, pid)
    s.refresh(p)
    if p.revision != request.base_revision:
        raise BusinessError(409, '数据已更新，请刷新后重新生成修改')

    operations = [o.model_dump(mode='json') for o in request.operations]
    # 旧调用方未提供落实资料时保留原值；显式 null 仍可由人工清空。
    for source, op in zip(request.operations, operations):
        if op['kind'] == 'resource' and source.data is not None and 'preparation' not in source.data.model_fields_set:
            op['data'].pop('preparation', None)
    before = validate_operations(s, pid, operations)
    c = dao.add_change(s, project_id=pid, base_revision=p.revision, reason=request.reason,
               operations=operations, before=before)
    if commit:
        s.commit()
    return change_dict(c)


# 用途：幂等确认草稿并修改正式记录。
# 参数：s/pid/cid 为会话、项目及草稿 ID。
# 返回及副作用：返回草稿字典；领取项目版本及草稿状态、应用操作、写事件并提交；不存在或冲突抛 BusinessError。
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
    # 项目版本和草稿状态都采用条件领取，任一失败均不能留下半批正式修改。
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


# 用途：原子拒绝待处理草稿。
# 参数：s/pid/cid 为会话、项目及草稿 ID。
# 返回及副作用：返回 rejected 状态并提交；不存在或已处理抛 BusinessError，领取失败回滚。
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
