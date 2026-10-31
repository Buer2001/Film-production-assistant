from backend.common.errors import BusinessError
from backend.models.notice import Notice
from backend.service.project import rows, state
from backend.dao import project as project_dao
from backend.dao import notice as dao


def publish(s, pid, request):
    # 通告版本号分配与项目变更共用同一项目锁，防止并发重复版本。
    result = project_dao.claim_revision(s, pid, request.base_revision)
    if result != 1:
        s.rollback()
        raise BusinessError(409, '计划版本已变化，请刷新')
    snapshot = state(s, pid)
    day = request.date.isoformat()
    versions = [n.version for n in rows(s, Notice, pid) if n.date == day]
    slots = [r for r in snapshot['records'] if r['kind'] == 'schedule' and r['data']['date'] == day]
    slots.sort(key=lambda r: r['data']['start'] or '')
    notice = dao.add_notice(s, project_id=pid, date=day, version=max(versions, default=0) + 1,
        revision=request.base_revision, snapshot={'project': snapshot['name'], 'schedule': slots,
            'records': snapshot['records'], 'checks': snapshot['checks'], 'notes': request.notes})
    s.commit()
    return {'id': notice.id, 'date': day, 'version': notice.version, 'snapshot': notice.snapshot}


def export_notice(s, pid, nid):
    notice = dao.get_notice(s, nid)
    if not notice or notice.project_id != pid:
        raise BusinessError(404, '通告不存在')
    snap = notice.snapshot
    lines = [f"{snap['project']} | {notice.date} 通告 V{notice.version}",
             f'发布时间：{notice.created_at}', f'计划版本：{notice.revision}', '', snap['notes'], '']
    for record in snap['schedule']:
        data = record['data']
        lines.append(f"{data['start'] or '待定'} | {data['title']} | {data['minutes']}分钟 | {'、'.join(data['resources'])}\n{data['notes']}")
    return '\n'.join(lines), f'notice-{notice.date}-v{notice.version}.txt'
