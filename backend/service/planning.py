"""任务安排业务入口：生成只写草稿，正式修改统一校验并在事务内执行。"""
from copy import deepcopy
from datetime import date
from pydantic import ValidationError
from backend.common.database.base import uid, now
from backend.common.errors import BusinessError
from backend.common.logging.config import logger
from backend.common.logging.validation import validation_diagnostics, diagnostic_summary
from backend.dao import planning as dao, project as projects
from backend.dao.script import version as versions, scene as scenes
from backend.dao.event import add_event
from backend.schemas.planning import Settings, TaskData, PlanResult
from backend.tools.planning import check_tasks, check_coverage, today
from backend.ai import planning as ai
from backend.dao import resource as resources

MAX_TASKS = 500  # ponytail: 单制片小项目整计划校验，规模扩大后改分页和任务级并发。


def validate(schema, data):
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        diagnostics = validation_diagnostics(exc, schema)
        logger.warning('planning.validation_failed', extra={'operation': 'planning.validate', 'error_type': 'schema_invalid', **diagnostics})
        raise BusinessError(422, '任务或日程字段不合法：' + diagnostic_summary(diagnostics)) from exc


def require_project(session, pid):
    if projects.get_project(session, pid) is None:
        raise BusinessError(404, '项目不存在')


def settings_data(row):
    return Settings(**{key: getattr(row, key) for key in Settings.model_fields}).model_dump(mode='json') if row else Settings().model_dump(mode='json')


def task_data(row):
    value = TaskData(**{key: getattr(row, key) for key in TaskData.model_fields}).model_dump(mode='json')
    return {'id': row.id, **value, 'completed_at': row.completed_at, 'created_at': row.created_at, 'updated_at': row.updated_at}


def source_data(session, pid, *, current=False):
    rows = versions.list_versions(session, pid, current=current)
    row = next((r for r in rows if r.status == 'confirmed'), None)
    return {'script_id': row.id, 'revision': row.revision, 'version_number': row.version_number} if row else None


def read(session, pid):
    require_project(session, pid)
    row = dao.get(session, pid)
    tasks = [task_data(t) for t in dao.tasks(session, row.id)] if row else []
    index = {t['id']: t for t in tasks}
    for t in tasks:
        active = t['status'] not in ('completed', 'cancelled')
        days = (date.fromisoformat(t['planned_end']) - today()).days if active and t['planned_end'] else None
        t['due_state'] = ('overdue' if days < 0 else 'today' if days == 0 else 'soon' if days <= 3 else None) if days is not None else None
        t['overdue'] = t['due_state'] == 'overdue'
        t['blocked'] = bool(active and any(index.get(d['task_id'], {}).get('status') != 'completed' for d in t['details']['dependencies']))
    settings = settings_data(row)
    current_source = source_data(session, pid)
    warnings = check_tasks(tasks, settings)
    if row and row.source_script_id and (not current_source or (row.source_script_id, row.source_script_revision) != (current_source['script_id'], current_source['revision'])):
        warnings.append({'task_id': None, 'message': '正式剧本版本已变化，请复核任务关联；日程未自动改绑'})
    options = []
    if current_source:
        for scene in scenes.list_for_script(session, current_source['script_id']):
            options.append({'script_id': current_source['script_id'], 'scene_id': scene.id,
                            'scene_number': scene.scene_number, 'location': scene.location})
    draft = row.draft if row else None
    return {'id': row.id if row else None, 'revision': row.revision if row else 0, 'settings': settings,
            'tasks': tasks, 'draft': draft, 'warnings': warnings, 'source': current_source,
            'scene_options': options, 'resource_revision': projects.get_project(session, pid).revision,
            'resource_options': [{'id': r.id, 'data': r.data} for r in resources.list_resources(session, pid)], 'checklist': ai.checklist(),
            'draft_stale': bool(draft and draft['status'] == 'pending' and (draft['base_revision'] != row.revision or draft['source'] != current_source))}


def lock(session, pid, revision):
    if not projects.lock_project(session, pid):
        raise BusinessError(404, '项目不存在')
    row = dao.get(session, pid, current=True)
    if row is None:
        if revision != 0:
            raise BusinessError(409, '日程版本已变化，请刷新；本地输入保留')
        row = dao.create(session, pid)
    if row.revision != revision or not dao.claim(session, row, revision):
        raise BusinessError(409, '日程版本已变化，请刷新后重新核对；本地输入保留')
    session.refresh(row)
    return row


def validate_refs(session, pid, task):
    for ref in task['details']['scene_refs']:
        scene = dao.scene_reference(session, pid, ref['script_id'], ref['scene_id'])
        if scene is None:
            raise BusinessError(422, '关联场次不存在、不属于本项目或尚未确认')
        ref['scene_number'], ref['location'] = scene.scene_number, scene.location
    for ref in task['details']['resource_refs']:
        if ref['record_id'] and not dao.resource_exists(session, pid, ref['record_id']):
            raise BusinessError(422, '关联资源不存在或不属于本项目')


def clean_task(data):
    return {k: data[k] for k in TaskData.model_fields if k in data}


def merged_task(base, changes):
    # PATCH 顶层和 details 只更新给定字段，状态更新不会擦除来源与人工补充。
    data = deepcopy(clean_task(base))
    changes = deepcopy(changes)
    if isinstance(changes.get('details'), dict):
        changes['details'] = {**data.get('details', {}), **changes['details']}
    data.update(changes)
    return validate(TaskData, data).model_dump(mode='json')


def save_settings(session, pid, request):
    row = lock(session, pid, request.revision)
    before = settings_data(row)
    for key, value in request.settings.model_dump().items():
        setattr(row, key, value)
    add_event(session, pid, 'planning_settings', {'before': before, 'after': request.settings.model_dump(mode='json'), 'revision': row.revision})
    session.commit()
    return read(session, pid)


def save_task(session, pid, request, task_id=None):
    row = lock(session, pid, request.revision)
    current = {t.id: t for t in dao.tasks(session, row.id, current=True)}
    if task_id and task_id not in current:
        raise BusinessError(404, '任务不存在或不属于本项目')
    before = task_data(current[task_id]) if task_id else None
    data = merged_task(before, request.changes) if task_id else request.task.model_dump(mode='json')
    validate_refs(session, pid, data)
    key = task_id or uid()
    candidate = [task_data(t) for k, t in current.items() if k != key] + [{'id': key, **data}]
    if len(candidate) > MAX_TASKS:
        raise BusinessError(422, '单项目最多500项任务，请先收敛清单')
    check_tasks(candidate, settings_data(row))
    dao.write_task(session, row.id, key, validate(TaskData, data).model_dump(), current.get(key))
    add_event(session, pid, 'planning_task', {'task_id': key, 'before': before, 'after': data, 'revision': row.revision})
    session.commit()
    return read(session, pid)


def apply_result(session, pid, current, result, settings, *, model=False, generation_id=None):
    final = {key: deepcopy(value) for key, value in current.items()}
    refs = [op['ref'] for op in result['operations']]
    if len(refs) != len(set(refs)):
        raise BusinessError(422, '同一草稿不能重复操作同一任务编号')
    for op in result['operations']:
        key = op['ref']
        if op['action'] == 'add':
            if key in current:
                raise BusinessError(422, '新增编号与已有任务冲突')
            data = validate(TaskData, op['task']).model_dump(mode='json')
            if data['status'] != 'todo':
                raise BusinessError(422, '新增建议必须是待办任务')
            data['details']['origin'] = {'type': 'model', 'generation_id': generation_id}
        else:
            if key not in current:
                raise BusinessError(422, '修改任务不存在或不属于本计划')
            if model and current[key]['status'] in ('completed', 'cancelled'):
                raise BusinessError(422, '模型不得修改已完成或已取消任务，请人工处理')
            data = merged_task(current[key], op['changes'] if op['action'] == 'update' else {'status': 'cancelled'})
            if model and data['status'] not in ('todo', 'in_progress', 'cancelled'):
                raise BusinessError(422, '模型不得代替制片标记完成')
        if model:
            # 部门可由模型建议，实施人员只由制片填写；不编造或改派姓名。
            previous_details = current.get(key, {}).get('details', {})
            data['details']['assignees'] = list(previous_details.get('assignees', []))
            if previous_details.get('department'):
                data['details']['department'] = previous_details['department']
            if previous_details.get('collaborating_departments'):
                data['details']['collaborating_departments'] = list(previous_details['collaborating_departments'])
            old_constraints = current.get(key, {}).get('details', {}).get('constraints', [])
            confirmed = [c for c in old_constraints if c['confirmation'] == 'confirmed']
            if any(c not in data['details']['constraints'] for c in confirmed):
                raise BusinessError(422, '模型不得删除或改写已确认约束')
            for c in data['details']['constraints']:
                if c not in confirmed:
                    c['confirmation'] = 'pending'
        validate_refs(session, pid, data)
        if op['action'] == 'add':
            op['task'] = data
        elif op['action'] == 'update':
            # 回写经过净化的字段；保留局部修改，避免重新解释模型输出。
            op['changes'] = {k: data[k] for k in op['changes']}
        final[key] = {'id': key, **data}
    if len(final) > MAX_TASKS:
        raise BusinessError(422, '单项目最多500项任务')
    check_coverage(result, ai.checklist(), set(final))
    for task in final.values():
        if not set(task['details']['checklist_refs']) <= {c['id'] for c in ai.checklist()}:
            raise BusinessError(422, '任务关联了未知检查项')
    warnings = check_tasks(list(final.values()), settings)
    return final, warnings


async def generate(sessions, pid, request, model=None):
    with sessions() as session:
        snap = read(session, pid)
        if snap['revision'] != request.revision:
            raise BusinessError(409, '日程版本已变化，请刷新后生成')
        if not snap['settings']['shoot_start']:
            raise BusinessError(422, '请先保存开拍日期')
        source = snap['source']
        breakdown = []
        if source:
            for scene in scenes.list_for_script(session, source['script_id']):
                data = scenes.data(scene)
                breakdown.append({'id': scene.id, 'scene_number': scene.scene_number, 'location': scene.location,
                                  **{k: data.get(k) for k in ('summary', 'cast', 'makeup_costume', 'action_props', 'other_props')}})
        snapshot = {'today': today().isoformat(), 'settings': snap['settings'], 'source': source,
                    'tasks': snap['tasks'], 'breakdown': breakdown,
                    'resources': snap['resource_options']}
        # 显式结束事务和连接作用域，模型等待期间不持锁。
    result = await ai.generate(snapshot, request.instruction, model, context={
        'project_id': pid, 'revision': request.revision, 'script_id': source['script_id'] if source else None})
    with sessions() as session:
        try:
            row = lock(session, pid, request.revision)
            if source_data(session, pid, current=True) != source:
                raise BusinessError(409, '生成期间正式剧本已变化，请重新生成')
            generation_id = uid()
            current = {t.id: task_data(t) for t in dao.tasks(session, row.id, current=True)}
            _, warnings = apply_result(session, pid, current, result, settings_data(row), model=True, generation_id=generation_id)
            row.draft = {'id': generation_id, 'status': 'pending', 'base_revision': row.revision,
                         'source': source, 'result': result, 'warnings': warnings, 'created_at': now()}
            add_event(session, pid, 'planning_generate', {'draft_id': generation_id, 'source': source,
                       'operations': len(result['operations']), 'revision': row.revision})
            session.commit()
            return read(session, pid)
        except Exception:
            session.rollback()
            raise


def require_draft(row, draft_id=None):
    draft = row.draft
    if not draft or draft['status'] != 'pending' or (draft_id and draft['id'] != draft_id):
        raise BusinessError(409, '待确认草稿不存在或已处理')
    return deepcopy(draft)


def edit_draft(session, pid, request):
    row = lock(session, pid, request.revision)
    draft = require_draft(row, request.draft_id)
    if draft['base_revision'] != request.revision or draft['source'] != source_data(session, pid, current=True):
        raise BusinessError(409, '草稿依据已变化，请重新生成后核对')
    result = request.result.model_dump(mode='json')
    current = {t.id: task_data(t) for t in dao.tasks(session, row.id, current=True)}
    _, warnings = apply_result(session, pid, current, result, settings_data(row), generation_id=draft['id'])
    draft.update(result=result, warnings=warnings, base_revision=row.revision)
    row.draft = draft
    session.commit()
    return read(session, pid)


def confirm(session, pid, request):
    # 项目锁内先查询确认事件，使旧确认请求在后续编辑或新草稿后仍可幂等返回。
    if not projects.lock_project(session, pid):
        raise BusinessError(404, '项目不存在')
    if dao.confirmed(session, pid, request.draft_id):
        session.rollback()
        return read(session, pid)
    row = lock(session, pid, request.revision)
    draft = require_draft(row, request.draft_id)
    if draft['base_revision'] != request.revision or draft['source'] != source_data(session, pid, current=True):
        raise BusinessError(409, '草稿依据已变化，请重新生成后核对')
    rows = {t.id: t for t in dao.tasks(session, row.id, current=True)}
    current = {key: task_data(t) for key, t in rows.items()}
    result = deepcopy(draft['result'])
    final, _ = apply_result(session, pid, current, result, settings_data(row), generation_id=draft['id'])
    mapping = {op['ref']: uid() for op in result['operations'] if op['action'] == 'add'}
    # 新增依赖可能引用尚未写入的任务，先映射整批 ID，再统一写入。
    changes = []
    for op in result['operations']:
        ref = op['ref']; key = mapping.get(ref, ref)
        data = clean_task(final[ref])
        for dep in data['details']['dependencies']:
            dep['task_id'] = mapping.get(dep['task_id'], dep['task_id'])
        dao.write_task(session, row.id, key, validate(TaskData, data).model_dump(), rows.get(key))
        changes.append({'task_id': key, 'before': current.get(ref), 'after': data})
    row.source_script_id = draft['source']['script_id'] if draft['source'] else None
    row.source_script_revision = draft['source']['revision'] if draft['source'] else None
    draft['status'] = 'confirmed'; draft['confirmed_at'] = now()
    row.draft = draft
    add_event(session, pid, 'planning_confirm', {'draft_id': draft['id'], 'changes': changes, 'revision': row.revision})
    session.commit()
    return read(session, pid)


def discard(session, pid, request):
    row = lock(session, pid, request.revision)
    draft = require_draft(row, request.draft_id)
    draft['status'] = 'discarded'
    row.draft = draft
    add_event(session, pid, 'planning_discard', {'draft_id': draft['id'], 'revision': row.revision})
    session.commit()
    return read(session, pid)


def task_evidence(session, pid, task_id, script_id, scene_id):
    """只读关联版本的正式拆解；禁止借用 V1 detail（该入口会优先读取文件草稿）。"""
    require_project(session, pid)
    task = dao.task_for_project(session, pid, task_id)
    if task is None:
        raise BusinessError(404, '任务不存在或不属于本项目')
    refs = (task.details or {}).get('scene_refs', [])
    if not any(r['script_id'] == script_id and r['scene_id'] == scene_id for r in refs):
        raise BusinessError(404, '该任务没有关联这个场次，请核对任务关联')
    scene = dao.scene_reference(session, pid, script_id, scene_id)
    if scene is None:
        raise BusinessError(404, '关联场次已不存在或没有已确认拆解，请编辑任务重新核对关联')
    script = versions.get(session, pid, script_id)
    return {'task_id': task.id, 'task_title': task.title,
            'script': {'id': script.id, 'title': script.title, 'version_number': script.version_number,
                       'version_label': script.version_label},
            'scene': scenes.as_dict(scene), 'content': script.content}


def department_targets(snapshot):
    """有待审草稿时只补该草稿；已分配、完成和取消的任务不再交给模型。"""
    current = {t['id']: t for t in snapshot['tasks']}
    draft = snapshot['draft']
    if draft and draft['status'] == 'pending':
        if snapshot['draft_stale']:
            raise BusinessError(409, '待确认草稿依据已变化，请先重新核对；没有替换原草稿')
        candidates = {}
        for op in draft['result']['operations']:
            key = op['ref']
            if op['action'] == 'cancel':
                continue
            if op['action'] == 'add':
                value = validate(TaskData, op['task']).model_dump(mode='json')
            else:
                if key not in current:
                    raise BusinessError(409, '草稿关联任务已变化，请重新核对')
                if current[key]['details'].get('department'):
                    continue
                value = merged_task(current[key], op['changes'])
            candidates[key] = value
    else:
        candidates = current
    return {key: value for key, value in candidates.items()
            if not value['details'].get('department', '').strip() and value['status'] in ('todo', 'in_progress')}


async def suggest_departments(sessions, pid, request, model=None):
    with sessions() as session:
        snapshot = read(session, pid)
        if snapshot['revision'] != request.revision:
            raise BusinessError(409, '日程版本已变化，请刷新后补全部门')
        targets = department_targets(snapshot)
        if not targets:
            raise BusinessError(422, '当前没有需要补全部门的未完成任务')
        remaining_count = max(0, len(targets) - 300)
        targets = dict(list(targets.items())[:300])
        payload = [{'ref': key, 'title': t['title'], 'description': t['description'], 'phase': t['phase'],
                    'category': t['category'], 'resource_refs': t['details']['resource_refs'],
                    'scene_refs': t['details']['scene_refs'],
                    'collaborating_departments': t['details'].get('collaborating_departments', [])}
                   for key, t in targets.items()]
        source = snapshot['source']
        pending = snapshot['draft'] if snapshot['draft'] and snapshot['draft']['status'] == 'pending' else None
    suggestions = await ai.departments(payload, model, context={'project_id': pid, 'revision': request.revision,
        'script_id': source['script_id'] if source else None})
    refs = [item['ref'] for item in suggestions['assignments']]
    if len(refs) != len(set(refs)) or set(refs) != set(targets):
        raise BusinessError(422, '部门建议的任务编号遗漏、重复或越界；原任务及草稿保留')
    with sessions() as session:
        try:
            row = lock(session, pid, request.revision)
            if source_data(session, pid, current=True) != source:
                raise BusinessError(409, '补全部门期间剧本依据已变化，请重新核对')
            draft = deepcopy(pending) if pending else {'id': uid(), 'status': 'pending', 'source': source,
                'created_at': now(), 'kind': 'departments', 'result': {'operations': [], 'questions': [],
                'coverage': [{'check_id': item['id'], 'status': 'unknown', 'reason': '本次仅补全部门，未重新检查日程', 'task_refs': []}
                             for item in ai.checklist()]}}
            result = draft['result']
            operation_index = {op['ref']: op for op in result['operations']}
            assigned = 0
            uncertain = []
            for item in suggestions['assignments']:
                key = item['ref']
                if not item['department']:
                    uncertain.append(item)
                    continue
                detail = {'department': item['department']}
                # 人工已填协作部门保持不变；模型只补空白字段。
                if not targets[key]['details'].get('collaborating_departments'):
                    detail['collaborating_departments'] = list(dict.fromkeys(d for d in item['collaborating_departments'] if d != item['department']))
                if key in operation_index:
                    op = operation_index[key]
                    if op['action'] == 'add':
                        op['task'].setdefault('details', {}).update(detail)
                    else:
                        op['changes'].setdefault('details', {}).update(detail)
                else:
                    result['operations'].append({'action': 'update', 'ref': key, 'task': None, 'changes': {'details': detail}})
                assigned += 1
            if uncertain:
                question = f'有{len(uncertain)}项任务的主责部门需要确认，请查看部门判断明细或人工补填。'
                if question not in result['questions'] and len(result['questions']) < 50:
                    result['questions'].append(question)
            # 复用完整安排校验，但不让规范化过程扩写原有局部变更字段。
            validate(PlanResult, result)
            current = {t.id: task_data(t) for t in dao.tasks(session, row.id, current=True)}
            _, warnings = apply_result(session, pid, current, deepcopy(result), settings_data(row), generation_id=draft['id'])
            draft.update(base_revision=row.revision, warnings=warnings, updated_at=now(),
                         department_assignment={'target_count': len(targets), 'assigned_count': assigned, 'remaining_count': remaining_count,
                                                'suggestions': suggestions['assignments']})
            row.draft = draft
            add_event(session, pid, 'planning_departments', {'draft_id': draft['id'], 'revision': row.revision,
                      'target_count': len(targets), 'assigned_count': assigned})
            session.commit()
            return read(session, pid)
        except Exception:
            session.rollback()
            raise
