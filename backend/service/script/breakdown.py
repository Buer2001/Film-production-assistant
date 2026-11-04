# 文件职责：管理拆解工作台：编辑只写文件草稿，明确确认后才替换数据库正式场次。
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


# 用途：提取剧本详情头部元数据。
# 参数：row 为剧本版本模型。
# 返回及副作用：返回版本、状态、修订号、来源及时间字典。
def header(row):
    return {key: getattr(row, key) for key in ('id', 'project_id', 'title', 'version_number', 'version_label',
            'previous_script_id', 'status', 'revision', 'source_name', 'created_at', 'confirmed_at', 'parse_error')}


# 用途：组合文件草稿、正式版本和前版生成工作台详情。
# 参数：session/pid/sid 为会话及标识，store 为可选文件存储，manager 为可选任务管理器。
# 返回及副作用：返回详情；优先使用草稿，必要时修复确认回执或任务中断状态；版本不存在抛 BusinessError。
def detail(session, pid, sid, store=None, manager=None):
    store = store or DraftStore()
    row = script_service.require(session, pid, sid)
    draft = store.load(pid, sid)
    if draft and row.status == 'confirmed' and row.revision > draft.get('base_revision', row.revision):
        # 用途：在文件锁内补写数据库已确认回执。
        # 参数：current 为重新读取的草稿，闭包 row 为正式版本。
        # 返回及副作用：仅正式修订号领先时同步确认状态并推进进度；返回草稿，避免覆盖已修复后的人工编辑。
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
           'comparison': compare([r for r in current if r.get('resolution') != 'excluded'], previous, bool(row.previous_script_id),
                                 draft['deleted_reviewed'] if draft else row.deleted_reviewed),
           'progress': draft['progress'] if draft else {'state': 'confirmed' if row.status == 'confirmed' else 'review', 'stage': '待解析', 'total': len(current), 'completed': sum(r['parse_status'] == 'succeeded' and r['resolution'] != 'manual' for r in current), 'failed': 0, 'sequence': 0, 'started_at': None}}
    doc['can_start_parse'] = (not draft and not doc['read_only'] and row.status != 'confirmed'
                              and all(is_empty_placeholder(entry) for entry in current))
    if draft:
        doc.update(status=draft['status'], revision=draft['revision'], confirmed_at=draft.get('confirmed_at'))
    doc['custom_fields'] = custom_fields.get(session, pid)['fields']
    return doc


# 用途：领取数据库修订号以协调开始解析。
# 参数：session 为会话，row 为版本，revision 为预期数据库修订号。
# 返回及副作用：锁定项目并检查最新版本后刷新 row；领取失败回滚并抛 BusinessError，成功不提交。
def claim(session, row, revision):
    scripts.lock_project(session, row.project_id)
    script_service.require_editable(session, row)
    if not scripts.claim(session, row.id, revision):
        session.rollback()
        raise BusinessError(409, '版本已变化，请刷新；本地修改尚未覆盖服务器')
    session.refresh(row)


# 用途：首次分场并启动后台解析。
# 参数：session/pid/sid 为会话及标识，revision 为数据库修订号，manager 为任务管理器。
# 返回及副作用：返回公开草稿；已有草稿或拆解时拒绝；提交解析状态、初始化文件后启动后台任务，不写正式场次。
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
    # 用途：在同一文件锁内检查并初始化草稿。
    # 参数：current 为现有文件内容，闭包 doc 为新草稿。
    # 返回及副作用：无旧草稿时提交数据库状态并返回 doc；已有内容抛 BusinessError，防止覆盖人工编辑。
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


# 用途：将人工编辑保存到文件草稿。
# 参数：request 含文件 revision、场次和 edited_fields；store 为可选文件存储。
# 返回及副作用：返回详情；校验 ID、字段及版本后递增文件 revision，最终回滚数据库只读事务，不写正式场次。
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
    # 用途：合并人工修改并维护逐字段保护标记。
    # 参数：doc 为锁内草稿，闭包 request 提供值及字段掩码。
    # 返回及副作用：返回更新草稿；解析中或有掩码时保留未提交场次；版本、ID、前版匹配不合法抛 BusinessError。
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
            # 后台结果可能已更新其他字段；显式编辑掩码只覆盖本次实际修改，避免旧页面快照反向擦除模型结果。
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
            # 记录人工真实改动过的业务字段，后台成功回写时按此名单跳过覆盖。
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


# 用途：将人工确认的文件草稿写为正式拆解。
# 参数：request 含文件 revision 及接受缺失、未核对变化选项；store 为可选存储。
# 返回及副作用：返回详情；项目锁和文件锁内按 base_revision 领取正式版本，提交场次后再保存文件确认回执。
def confirm(session, pid, sid, request, store=None):
    store = store or DraftStore()
    row = script_service.require(session, pid, sid)
    scripts.lock_project(session, pid)
    script_service.require_editable(session, row)
    doc = detail(session, pid, sid, store)
    if doc['status'] == 'confirmed' and request.revision in (doc['revision'], doc['revision'] - 1):
        session.rollback()
        return doc
    # 用途：校验确认条件并提交正式场次替换。
    # 参数：value 为锁内草稿，闭包 request/row 提供选项及正式版本。
    # 返回及副作用：返回确认后的草稿；解析未完成、核对选项不足或版本冲突抛 BusinessError；数据库提交先于文件回执写入。
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
            comparison = compare(kept, value['previous_scenes'], True, value['deleted_reviewed'])
            unreviewed = (any(r['match_status'] == 'pending' or not r['change_reviewed'] for r in kept)
                          or bool(comparison['unlinked']))
            if unreviewed and not request.accept_unreviewed:
                raise BusinessError(422, '仍有未匹配或未核对的版本变化，可逐场处理，或明确选择直接确认本版')
        if (value['review_issues'] or any(missing(r) for r in kept)) and not request.accept_missing:
            raise BusinessError(422, '仍有待补信息，请补齐或明确接受这些提示')
        # 文件 revision 防止人工编辑互相覆盖；base_revision 则校验正式数据库版本，两者不能混用。
        if not scripts.claim(session, sid, value.get('base_revision', row.revision)):
            raise BusinessError(409, '正式版本已变化，请刷新')
        scenes.replace(session, sid, kept)
        row.revision = value['revision'] + 1
        row.status, row.confirmed_at, row.deleted_reviewed = 'confirmed', now(), value['deleted_reviewed']
        scripts.log(session, pid, 'confirm', {'script_id': sid, 'revision': row.revision,
            'accepted_missing': request.accept_missing, 'accepted_unreviewed': request.accept_unreviewed})
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


# 用途：对失败或未完成的单场启动重试。
# 参数：scene_id 为场次，revision 为文件修订号，manager 为后台管理器。
# 返回及副作用：递增文件 revision、释放数据库事务后启动任务并返回详情；运行状态、目标或版本不合法抛 BusinessError。
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
    # 用途：在文件锁内领取单场重试版本。
    # 参数：value 为草稿，闭包 revision/scene_id 为请求版本及目标场次。
    # 返回及副作用：返回标记运行并递增 revision 的草稿；版本不符抛 BusinessError。
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


# 用途：中止运行解析并保留待处理草稿。
# 参数：revision 为文件草稿修订号，manager 为任务管理器。
# 返回及副作用：领取文件 revision 后释放数据库事务、等待取消并返回详情；状态或版本冲突抛 BusinessError。
async def recover(session, pid, sid, revision, manager):
    row = script_service.require(session, pid, sid)
    doc = detail(session, pid, sid, manager.store)
    if doc['progress']['state'] != 'running':
        raise BusinessError(409, '状态或版本已变化')
    scripts.lock_project(session, pid)
    script_service.require_editable(session, row)
    # 用途：领取中止操作的文件修订号。
    # 参数：value 为锁内草稿，闭包 revision 为预期版本。
    # 返回及副作用：返回 revision 加一的草稿；冲突抛 BusinessError，实际取消由外层完成。
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


# 用途：导出当前工作台未排除场次。
# 参数：session/pid/sid 为会话及标识，store 为可选文件存储。
# 返回及副作用：返回带版本和修订号的文件名及 XLSX 字节；可导出未确认稿，排除行不进入交付表格。
def export(session, pid, sid, store=None):
    from backend.tools.script.exporter import export_workbook
    doc = detail(session, pid, sid, store)
    # 排除行只在工作台保留用于追溯，不能混进交付表格伪装成正式场次。
    doc['scenes'] = [scene for scene in doc['scenes'] if scene.get('resolution') != 'excluded']
    return f"breakdown-v{doc['version_number']}-r{doc['revision']}.xlsx", export_workbook(doc)
