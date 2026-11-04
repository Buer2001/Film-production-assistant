# 文件职责：冻结指定日期的项目快照，维护通告独立版本并导出文本。
from backend.common.errors import BusinessError
from backend.models.notice import Notice
from backend.service.project import rows, state
from backend.dao import project as project_dao
from backend.dao import notice as dao


# 用途：发布当天拍摄安排快照。
# 参数：s/pid 为会话及项目，request 含基准版本、日期及备注。
# 返回及副作用：返回通告标识、日期及版本；领取项目锁、分配当天版本后提交，基准版本变化抛 BusinessError。
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


# 用途：将已发布快照导出文本。
# 参数：s/pid/nid 为会话、项目及通告 ID。
# 返回及副作用：返回文本和文件名；不存在或归属不符抛 BusinessError，不用当前安排覆盖历史快照。
def export_notice(s, pid, nid):
    notice = dao.get_notice(s, nid)
    if not notice or notice.project_id != pid or notice.version <= 0:
        raise BusinessError(404, '通告不存在')
    snap = notice.snapshot
    if snap.get('format') == 'shooting_v4':
        from backend.tools.shooting import export_notice_text
        return export_notice_text(notice), f'notice-{notice.date}-v{notice.version}.txt'
    lines = [f"{snap['project']} | {notice.date} 通告 V{notice.version}",
             f'发布时间：{notice.created_at}', f'计划版本：{notice.revision}', '', snap['notes'], '']
    for record in snap['schedule']:
        data = record['data']
        lines.append(f"{data['start'] or '待定'} | {data['title']} | {data['minutes']}分钟 | {'、'.join(data['resources'])}\n{data['notes']}")
    return '\n'.join(lines), f'notice-{notice.date}-v{notice.version}.txt'


# 按日返回发布来源、草稿和通告历史；GET 只读，不自动新建空草稿。
def read_day(s, pid, day):
    from backend.service import shooting
    from backend.tools.shooting import fingerprint, check_shooting
    source = shooting.day_source(s, pid, day)
    draft = dao.get_draft(s, pid, day)
    project = shooting.get_project(s, pid)
    return {'revision': project.revision, 'source': source, 'fingerprint': fingerprint(source),
            'issues': check_shooting(source['items'], source['people'], source['resources'], source['tasks']),
            'draft': {'details': draft.snapshot['details'], 'revision': draft.revision} if draft else None,
            'notices': [published_dict(s, pid, n) for n in dao.list_published(s, pid, day)]}


# 草稿仅更新 version=0 的执行补充信息；与正式通告分离，刷新后可继续编辑。
def save_draft(s, pid, day, request):
    from backend.service import shooting
    from backend.dao.event import add_event
    shooting.claim(s, pid, request.revision)
    dao.write_draft(s, pid, day, request.revision + 1, request.details.model_dump(mode='json'))
    add_event(s, pid, 'notice_draft', {'date': day, 'revision': request.revision + 1})
    s.commit()
    s.expire_all()
    return read_day(s, pid, day)


# 来源指纹防止旧页面把变化后的安排误当已审阅；项目→计划→场次统一锁顺序保持来源一致。
def publish_shooting(s, pid, day, request):
    from backend.service import shooting
    from backend.dao.event import add_event
    from backend.tools.shooting import fingerprint
    shooting.claim(s, pid, request.revision)
    source = shooting.day_source(s, pid, day, locked=True)
    current = fingerprint(source)
    if current != request.fingerprint:
        raise BusinessError(409, '当天拍摄来源已变化，请刷新并复核后发布')
    if not source['items']:
        raise BusinessError(422, '当天没有正式安排，不能发布通告')
    details = request.details.model_dump(mode='json')
    version = max((n.version for n in dao.list_published(s, pid, day)), default=0) + 1
    snapshot = {'format': 'shooting_v4', 'fingerprint': current, 'source': source, 'details': details}
    notice = dao.add_notice(s, project_id=pid, date=day, version=version,
                            revision=request.revision + 1, snapshot=snapshot)
    # 发布时保留当前补充信息草稿，不删除用户内容；再次发布仍生成新冻结版本。
    dao.write_draft(s, pid, day, request.revision + 1, details)
    s.flush()
    add_event(s, pid, 'shooting_notice', {'id': notice.id, 'date': day, 'version': version})
    result = {'id': notice.id, 'date': day, 'version': version, 'snapshot': snapshot, 'created_at': notice.created_at,
              'project_revision': request.revision + 1}
    s.commit()
    return result


# 按格式分别复核历史和 V4 通告，草稿从调用方列表中排除。
def published_dict(s, pid, notice, records=None):
    from backend.service import shooting
    from backend.tools.notice import notice_status
    status = (shooting.notice_status(s, pid, notice) if notice.snapshot.get('format') == 'shooting_v4'
              else notice_status(notice, records if records is not None else state(s, pid)['records']))
    return {k: getattr(notice, k) for k in ('id', 'date', 'version', 'revision', 'snapshot', 'created_at')} | status
