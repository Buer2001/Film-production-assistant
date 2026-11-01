from copy import deepcopy
from uuid import UUID
from backend.common.errors import BusinessError
from backend.common.database.base import now, uid
from backend.dao.script import version as scripts, scene as scenes
from backend.service.script import version as script_service
from backend.service.script.comparison import compare, FIELDS
from backend.tools.script.evidence import missing, duplicate_warnings, is_empty_placeholder
from backend.tools.script.draft_store import DraftStore
from backend.schemas.script import SceneData
from backend.service.script.jobs import advance
from backend.tools.script.text import refresh_scene_metadata
from backend.service.script import fields as custom_fields


def header(row):
    return {key: getattr(row, key) for key in ('id', 'project_id', 'title', 'version_number', 'version_label',
            'previous_script_id', 'status', 'revision', 'source_name', 'created_at', 'confirmed_at', 'parse_error')}


def detail(session, pid, sid, store=None, manager=None):
    store = store or DraftStore()
    row = script_service.require(session, pid, sid)
    draft = store.load(pid, sid)
    if draft and row.status == 'confirmed' and row.revision > draft.get('base_revision', row.revision):
        def repair_receipt(current):
            # Another reader may already have repaired the receipt and a user may
            # have edited it since our initial load. Recheck the durable draft
            # while holding the file lock before applying the SQL receipt.
            if current and row.revision > current.get('base_revision', row.revision):
                current.update(status='confirmed', revision=row.revision, base_revision=row.revision, confirmed_at=row.confirmed_at)
                current['progress'].update(state='confirmed', stage='已确认')
                return advance(current, 'complete')
            return current
        draft = store.update(pid, sid, repair_receipt)
    if draft and draft.get('progress', {}).get('state') == 'running' and manager and not manager.active(pid, sid):
        manager.interrupt(pid, sid)
        draft = store.load(pid, sid)
    current = draft['scenes'] if draft else []
    if not draft:
        for record in scenes.list_for_script(session, sid):
            entry = scenes.as_dict(record)
            empty = is_empty_placeholder(entry)
            entry.update(parse_status='pending' if empty else 'succeeded', parse_error='',
                         resolution='pending' if empty or entry.get('extracted_data') else 'manual')
            current.append(entry)
    previous = ([scenes.as_dict(r) for r in scenes.list_for_script(session, row.previous_script_id)] if row.previous_script_id else [])
    for entry in current + previous:
        refresh_scene_metadata(entry)
    doc = {**header(row), 'content': row.content, 'scenes': current, 'previous_scenes': previous,
           'review_issues': list(dict.fromkeys((draft.get('review_issues', []) if draft else row.review_issues) + duplicate_warnings([r for r in current if r.get('resolution') != 'excluded']))),
           'deleted_reviewed': draft['deleted_reviewed'] if draft else row.deleted_reviewed,
           'base_revision': draft.get('base_revision', row.revision) if draft else row.revision,
           'read_only': script_service.versions(session, pid)[0].id != sid,
           'comparison': compare([r for r in current if r.get('resolution') != 'excluded'], previous, bool(row.previous_script_id)),
           'progress': draft['progress'] if draft else {'state': 'confirmed' if row.status == 'confirmed' else 'review', 'stage': '待解析', 'total': len(current), 'completed': sum(r['parse_status'] == 'succeeded' and r['resolution'] != 'manual' for r in current), 'failed': 0, 'sequence': 0, 'started_at': None}}
    doc['can_start_parse'] = (not draft and not doc['read_only'] and row.status != 'confirmed'
                              and all(is_empty_placeholder(entry) for entry in current))
    if draft:
        doc.update(status=draft['status'], revision=draft['revision'], confirmed_at=draft.get('confirmed_at'))
    doc['custom_fields'] = custom_fields.get(session, pid)['fields']
    return doc


def claim(session, row, revision):
    scripts.lock_project(session, row.project_id)
    script_service.require_editable(session, row)
    if not scripts.claim(session, row.id, revision):
        session.rollback()
        raise BusinessError(409, '版本已变化，请刷新；本地修改尚未覆盖服务器')
    session.refresh(row)


async def parse(session, pid, sid, revision, manager):
    from backend.tools.script.splitter import split_scenes
    store = manager.store
    row = script_service.require(session, pid, sid)
    existing = [scenes.as_dict(record) for record in scenes.list_for_script(session, sid)]
    if store.load(pid, sid) or row.status == 'confirmed' or any(not is_empty_placeholder(entry) for entry in existing):
        raise BusinessError(409, '已有拆解草稿，请逐场重试或直接编辑')
    claim(session, row, revision)
    sources = split_scenes(row.content)
    entries = []
    for source in sources['scenes']:
        entries.append({**SceneData().model_dump(mode='json'), 'id': uid(), 'scene_number': source['scene_number'],
            'evidence': source['evidence'], 'extracted_data': {}, 'review_issues': [],
            'previous_scene_id': None, 'match_status': 'pending' if row.previous_script_id else 'first',
            'change_reviewed': False, 'parse_status': 'pending', 'parse_error': '', 'resolution': 'pending'})
    row.status, row.parse_error = 'parsing', ''
    doc = detail(session, pid, sid, store)
    doc.update(base_revision=row.revision, scenes=entries, status='parsing', can_start_parse=False, review_issues=sources['warnings'], progress={
        'state': 'running', 'stage': '逐场解析', 'total': len(entries), 'completed': 0,
        'failed': 0, 'sequence': 0, 'started_at': now()})
    advance(doc)
    def initialize(current):
        # 检查和创建必须持有同一文件锁，避免检查后出现的人工草稿被覆盖。
        if current is not None:
            raise BusinessError(409, '已有人工草稿，请刷新后继续编辑，未覆盖原内容')
        session.commit()
        return doc
    try:
        store.update(pid, sid, initialize)
    except Exception:
        session.rollback()
        raise
    manager.start(pid, sid)
    return {k: v for k, v in doc.items() if not k.startswith('_')}


def save(session, pid, sid, request, store=None):
    store = store or DraftStore()
    row = script_service.require(session, pid, sid)
    initial = detail(session, pid, sid, store)
    scripts.lock_project(session, pid)
    script_service.require_editable(session, row)
    field_ids = {field['id'] for field in custom_fields.get(session, pid)['fields']}
    if any(set(item.custom_values) - field_ids for item in request.scenes):
        raise BusinessError(422, '自定义字段不属于当前项目')
    previous = {r.id for r in scenes.list_for_script(session, row.previous_script_id)} if row.previous_script_id else set()
    def update(doc):
        doc = doc or initial
        if doc['revision'] != request.revision:
            raise BusinessError(409, '版本已变化，请刷新；本地修改尚未覆盖服务器')
        current = {r['id']: r for r in doc['scenes']}
        ids = [item.id for item in request.scenes if item.id]
        if len(ids) != len(set(ids)):
            raise BusinessError(422, '场次不存在或重复')
        new_ids = set(ids) - current.keys()
        try:
            for rid in new_ids:
                UUID(rid)
        except (ValueError, TypeError):
            raise BusinessError(422, '新增场次必须使用有效标识')
        if scenes.existing_ids(session, new_ids):
            raise BusinessError(422, '场次不属于当前草稿')
        running = doc['progress']['state'] == 'running'
        edits = getattr(request, 'edited_fields', {})
        masked = 'edited_fields' in request.model_fields_set
        entries = []
        for item in request.scenes:
            incoming = item.model_dump(mode='json')
            old = current.get(item.id)
            data = deepcopy(old) if old else {**incoming, 'id': item.id or uid(), 'evidence': {'text': '', 'manual_fields': list(FIELDS)}, 'extracted_data': {}}
            allowed = set(edits.get(item.id, [])) if masked or running else set(FIELDS) | {'previous_scene_id', 'match_status', 'change_reviewed', 'resolution'}
            if old is None:
                data.update(parse_status='pending', parse_error='', resolution=incoming.get('resolution', 'manual'))
            allowed &= set(FIELDS) | {'previous_scene_id', 'match_status', 'change_reviewed', 'resolution'}
            for key in allowed:
                data[key] = incoming[key]
            if data['previous_scene_id'] and data['previous_scene_id'] not in previous:
                raise BusinessError(422, '对应场次不属于上一版剧本')
            if not row.previous_script_id:
                data.update(previous_scene_id=None, match_status='first')
            elif data['match_status'] == 'matched' and not data['previous_scene_id']:
                raise BusinessError(422, '已匹配场次必须选择上一版对应场次')
            elif data['match_status'] in ('first', 'pending'):
                data.update(match_status='pending', previous_scene_id=None)
            elif data['match_status'] == 'new':
                data['previous_scene_id'] = None
            manual = set(data['evidence'].get('manual_fields', []))
            manual.update(k for k in FIELDS if k in allowed and (old is None or incoming[k] != old.get(k)))
            data['evidence']['manual_fields'] = sorted(manual)
            if allowed & {'previous_scene_id', 'match_status', 'change_reviewed'}:
                data['evidence']['match_manual'] = True
            data['review_issues'] = missing(data)
            refresh_scene_metadata(data)
            entries.append(data)
        if running or masked:
            entries.extend(deepcopy(value) for key, value in current.items() if key not in ids)
        if not entries:
            raise BusinessError(422, '至少保留一场戏')
        doc.update(scenes=entries, revision=doc['revision'] + 1, deleted_reviewed=request.deleted_reviewed, confirmed_at=None)
        if not running:
            doc['status'] = 'review'
            doc['progress']['state'] = 'review'
        return advance(doc, 'snapshot')
    try:
        if store.load(pid, sid) is None:
            store.write(pid, sid, initial)
        store.update(pid, sid, update)
    finally:
        session.rollback()
    return detail(session, pid, sid, store)


def confirm(session, pid, sid, request, store=None):
    store = store or DraftStore()
    row = script_service.require(session, pid, sid)
    scripts.lock_project(session, pid)
    script_service.require_editable(session, row)
    doc = detail(session, pid, sid, store)
    if doc['status'] == 'confirmed' and request.revision in (doc['revision'], doc['revision'] - 1):
        session.rollback()
        return doc
    def commit(value):
        if value['revision'] != request.revision:
            raise BusinessError(409, '版本已变化，请刷新')
        if value['progress']['state'] == 'running':
            raise BusinessError(409, '请等待解析完成或先中止')
        kept = [r for r in value['scenes'] if r.get('resolution') != 'excluded']
        if not kept:
            raise BusinessError(422, '至少保留一场戏')
        if any(r.get('parse_status') in ('failed', 'pending', 'running') and r.get('resolution') != 'manual' for r in kept):
            raise BusinessError(422, '请人工补齐或明确排除未完成的场次')
        if row.previous_script_id:
            if any(r['match_status'] == 'pending' or not r['change_reviewed'] for r in kept):
                raise BusinessError(422, '请处理场次匹配并逐场确认变更')
            comparison = compare(kept, value['previous_scenes'], True)
            if comparison['deleted'] and not value['deleted_reviewed']:
                raise BusinessError(422, '请核对已删除的场次')
        if (value['review_issues'] or any(missing(r) for r in kept)) and not request.accept_missing:
            raise BusinessError(422, '仍有待补信息，请补齐或明确接受这些提示')
        if not scripts.claim(session, sid, value.get('base_revision', row.revision)):
            raise BusinessError(409, '正式版本已变化，请刷新')
        scenes.replace(session, sid, kept)
        row.revision = value['revision'] + 1
        row.status, row.confirmed_at, row.deleted_reviewed = 'confirmed', now(), value['deleted_reviewed']
        scripts.log(session, pid, 'confirm', {'script_id': sid, 'revision': row.revision, 'accepted_missing': request.accept_missing})
        session.commit()
        value.update(revision=row.revision, base_revision=row.revision, status='confirmed', confirmed_at=row.confirmed_at)
        value['progress'].update(state='confirmed', stage='已确认')
        return advance(value, 'complete')
    try:
        if store.load(pid, sid) is None:
            store.write(pid, sid, doc)
        store.update(pid, sid, commit)
    except Exception:
        session.rollback()
        raise
    return detail(session, pid, sid, store)


async def retry(session, pid, sid, scene_id, revision, manager):
    row = script_service.require(session, pid, sid)
    doc = detail(session, pid, sid, manager.store, manager)
    if manager.store.load(pid, sid) is None:
        raise BusinessError(409, '尚无解析草稿，请先从原文开始逐场拆解')
    if manager.active(pid, sid):
        raise BusinessError(409, '请等待当前解析完成')
    entry = next((r for r in doc['scenes'] if r['id'] == scene_id), None)
    if not entry:
        raise BusinessError(404, '场次不存在')
    if entry['parse_status'] == 'succeeded':
        raise BusinessError(409, '该场已解析成功，可直接编辑')
    scripts.lock_project(session, pid)
    script_service.require_editable(session, row)
    def update(value):
        if value['revision'] != revision:
            raise BusinessError(409, '版本已变化，请刷新')
        value.update(revision=revision + 1, status='parsing', confirmed_at=None)
        value['progress'].update(state='running', stage='单场重试')
        next(r for r in value['scenes'] if r['id'] == scene_id)['parse_status'] = 'pending'
        return advance(value)
    try:
        manager.store.update(pid, sid, update)
    finally:
        session.rollback()
    manager.start(pid, sid, scene_id)
    return detail(session, pid, sid, manager.store)


async def recover(session, pid, sid, revision, manager):
    row = script_service.require(session, pid, sid)
    doc = detail(session, pid, sid, manager.store)
    if doc['progress']['state'] != 'running':
        raise BusinessError(409, '状态或版本已变化')
    scripts.lock_project(session, pid)
    script_service.require_editable(session, row)
    def update(value):
        if value['revision'] != revision:
            raise BusinessError(409, '版本已变化，请刷新')
        value['revision'] += 1
        return value
    try:
        manager.store.update(pid, sid, update)
    finally:
        session.rollback()
    await manager.cancel(pid, sid)
    return detail(session, pid, sid, manager.store)


def export(session, pid, sid, store=None):
    from backend.tools.script.exporter import export_workbook
    doc = detail(session, pid, sid, store)
    # 排除行只在工作台保留用于追溯，不能混进交付表格伪装成正式场次。
    doc['scenes'] = [scene for scene in doc['scenes'] if scene.get('resolution') != 'excluded']
    return f"breakdown-v{doc['version_number']}-r{doc['revision']}.xlsx", export_workbook(doc)
