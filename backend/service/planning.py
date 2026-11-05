# 文件职责：编排正式任务和待审日程草稿，模型调用后重新核对版本再保存建议。
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
from backend.dao import person as people

MAX_TASKS = 500  # ponytail: 单制片小项目整计划校验，规模扩大后改分页和任务级并发。


# 用途：验证输入模型并转换为业务错误。
# 参数：schema 为 Pydantic 模型类，data 为待验证数据。
# 返回及副作用：返回验证模型；失败记录诊断日志并抛 BusinessError(422)。
def validate(schema, data):
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        diagnostics = validation_diagnostics(exc, schema)
        logger.warning('planning.validation_failed', extra={'operation': 'planning.validate', 'error_type': 'schema_invalid', **diagnostics})
        raise BusinessError(422, '任务或日程字段不合法：' + diagnostic_summary(diagnostics)) from exc


# 用途：检查项目存在。
# 参数：session/pid 为会话及项目 ID。
# 返回及副作用：无返回值；不存在抛 BusinessError(404)，不提交。
def require_project(session, pid):
    if projects.get_project(session, pid) is None:
        raise BusinessError(404, '项目不存在')


# 用途：序列化计划设置。
# 参数：row 为计划模型或 None。
# 返回及副作用：返回 JSON 兼容设置字典；无计划时使用 Settings 默认值。
def settings_data(row):
    return Settings(**{key: getattr(row, key) for key in Settings.model_fields}).model_dump(mode='json') if row else Settings().model_dump(mode='json')


# 用途：序列化任务及时间元数据。
# 参数：row 为任务模型。
# 返回及副作用：返回 JSON 兼容任务字段及完成、创建、修改时间字典。
def task_data(row):
    value = TaskData(**{key: getattr(row, key) for key in TaskData.model_fields}).model_dump(mode='json')
    return {'id': row.id, **value, 'completed_at': row.completed_at, 'created_at': row.created_at, 'updated_at': row.updated_at}


# 用途：选择最新的已确认剧本依据。
# 参数：session/pid 为会话及项目，current 控制 DAO 当前读。
# 返回及副作用：返回剧本 ID、修订号和版本号字典，无已确认版本时返回 None。
def source_data(session, pid, *, current=False):
    rows = versions.list_versions(session, pid, current=current)
    row = next((r for r in rows if r.status == 'confirmed'), None)
    return {'script_id': row.id, 'revision': row.revision, 'version_number': row.version_number} if row else None


# 用途：聚合日程设置、正式任务、待审草稿及可选关联资料。
# 参数：session/pid 为会话及项目 ID。
# 返回及副作用：返回日程详情、日期提醒、阻塞标记及草稿过期状态；项目不存在抛 BusinessError，不提交。
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


# 用途：领取计划修订号并刷新计划对象。
# 参数：session/pid 为会话及项目，revision 为预期计划修订号。
# 返回及副作用：返回计划模型；项目锁内可初始化计划，版本冲突抛 BusinessError；不提交，交由外层事务完成。
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


# 用途：验证任务的人员、正式场次和资源引用。
# 参数：session/pid 为会话及项目，task 为可变任务字典。
# 返回及副作用：无返回值；同步场号和场景快照，归属或引用不合法抛 BusinessError，不提交。
def validate_refs(session, pid, task):
    for person_id in task['details'].get('person_ids', []):
        if people.get_person(session, pid, person_id) is None:
            raise BusinessError(422, '关联人员不存在或不属于本项目')
    for ref in task['details']['scene_refs']:
        scene = dao.scene_reference(session, pid, ref['script_id'], ref['scene_id'])
        if scene is None:
            raise BusinessError(422, '关联场次不存在、不属于本项目或尚未确认')
        ref['scene_number'], ref['location'] = scene.scene_number, scene.location
    for ref in task['details']['resource_refs']:
        if ref['record_id'] and not dao.resource_exists(session, pid, ref['record_id']):
            raise BusinessError(422, '关联资源不存在或不属于本项目')


# 用途：仅保留可写任务字段。
# 参数：data 为可能含展示元数据的任务字典。
# 返回及副作用：返回 TaskData 已定义字段的新字典，嵌套值沿用输入引用。
def clean_task(data):
    return {k: data[k] for k in TaskData.model_fields if k in data}


# 用途：转换任务为数据库存储结构。
# 参数：data 为任务数据。
# 返回及副作用：返回顶层 date 对象及 JSON 兼容 details 字典；字段非法由 validate 转成 BusinessError。
def storage_data(data):
    """SQL 日期列保留 date 对象，JSON details 中的时段则必须转成 ISO 文本。"""
    task = validate(TaskData, data)
    value = task.model_dump()
    value['details'] = task.details.model_dump(mode='json')
    return value


# 用途：合并任务局部更新。
# 参数：base 为原任务，changes 为局部修改字典。
# 返回及副作用：深复制后合并顶层及 details 并返回规范化 JSON 字典；非法字段抛 BusinessError，不改输入。
def merged_task(base, changes):
    # PATCH 顶层和 details 只更新给定字段，状态更新不会擦除来源与人工补充。
    data = deepcopy(clean_task(base))
    changes = deepcopy(changes)
    if isinstance(changes.get('details'), dict):
        changes['details'] = {**data.get('details', {}), **changes['details']}
    data.update(changes)
    return validate(TaskData, data).model_dump(mode='json')


# 用途：保存项目日程设置。
# 参数：session/pid 为会话及项目，request 含计划 revision 和设置。
# 返回及副作用：领取计划版本、更新设置、写事件后提交，返回最新日程；版本冲突抛 BusinessError。
def save_settings(session, pid, request):
    row = lock(session, pid, request.revision)
    before = settings_data(row)
    for key, value in request.settings.model_dump().items():
        setattr(row, key, value)
    add_event(session, pid, 'planning_settings', {'before': before, 'after': request.settings.model_dump(mode='json'), 'revision': row.revision})
    session.commit()
    return read(session, pid)


# 用途：新增或局部修改正式任务。
# 参数：request 含计划 revision 及任务或修改字段，task_id 为可选现有任务 ID。
# 返回及副作用：校验引用、总量和整计划依赖后写任务及事件并提交，返回日程；非法输入或冲突抛 BusinessError。
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
    dao.write_task(session, row.id, key, storage_data(data), current.get(key))
    add_event(session, pid, 'planning_task', {'task_id': key, 'before': before, 'after': data, 'revision': row.revision})
    session.commit()
    return read(session, pid)


# 用途：模拟应用草稿操作并校验最终任务集合。
# 参数：current 为现有任务映射，result 为可变草稿，settings 为设置；model 开启模型保护，generation_id 标记来源。
# 返回及副作用：返回最终任务映射及提醒；会净化并回写 result，校验引用但不写正式任务；不合法抛 BusinessError。
def apply_result(session, pid, current, result, settings, *, model=False, generation_id=None, require_coverage=True, origin_type='model'):
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
            data['details']['origin'] = {'type': origin_type, 'generation_id': generation_id}
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
            # 模型只建议安排，不能把猜测写成落实事实，或覆盖制片已经填写的结果。
            # 回写净化后的草稿，保证以后人工确认仍使用这些受保护值。
            for field, default in (('person_ids', []), ('usage_period', None),
                                   ('result_notes', ''), ('requires_people', False)):
                data['details'][field] = deepcopy(previous_details.get(field, default))
            if any(ref.get('record_id') for ref in previous_details.get('resource_refs', [])):
                data['details']['resource_refs'] = deepcopy(previous_details['resource_refs'])
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
    # V5 联合草稿只调整指定范围，不强制覆盖全部检查清单；日程生成仍保持完整覆盖要求。
    if require_coverage:
        check_coverage(result, ai.checklist(), set(final))
    for task in final.values():
        if not set(task['details']['checklist_refs']) <= {c['id'] for c in ai.checklist()}:
            raise BusinessError(422, '任务关联了未知检查项')
    warnings = check_tasks(list(final.values()), settings)
    return final, warnings


# 用途：把联合草稿的任务操作转换成日程建议结构。
# 参数：operations 为 V5 草稿操作列表，含 add/update/cancel 三种动作。
# 返回及副作用：返回只含 operations 的建议结构；不修改入参，不写库。
def task_operations(operations):
    """V5 任务操作转成日程建议结构，使模型保护和净化逻辑只有一份。"""
    converted = []
    for op in operations:
        if op['action'] == 'add':
            converted.append({'action': 'add', 'ref': op['temp_id'], 'task': op['patch'], 'changes': {}})
        elif op['action'] == 'update':
            converted.append({'action': 'update', 'ref': op['target_id'], 'task': None, 'changes': op['patch']})
        else:
            converted.append({'action': 'cancel', 'ref': op['target_id'], 'task': None, 'changes': {}})
    return {'operations': converted, 'questions': [], 'coverage': []}


# 用途：只计算候选任务合并后的整体视图，用于提交前的程序检查。
# 参数：operations 为联合草稿中的任务操作，generation_id 为本次工作编号。
# 返回及副作用：返回最终任务映射和提醒；读正式任务但不写库，不合法抛 BusinessError。
def plan_task_ops(session, pid, operations, *, generation_id=None, model=False):
    row = dao.get(session, pid)
    current = {t.id: task_data(t) for t in dao.tasks(session, row.id)} if row else {}
    return apply_result(session, pid, current, task_operations(operations), settings_data(row),
                        model=model, generation_id=generation_id, require_coverage=False,
                        origin_type='model' if model else 'manual')


# 用途：在已领取计划版本的同一事务内写入正式任务。
# 参数：row 为已领取版本的计划行，operations 为任务操作，model 表示来源为模型。
# 返回及副作用：返回临时编号到正式任务 ID 的映射；不提交，任一步失败由外层整体回滚。
def apply_task_ops(session, pid, row, operations, *, generation_id=None, model=False):
    current = {t.id: task_data(t) for t in dao.tasks(session, row.id, current=True)}
    final, _ = apply_result(session, pid, current, task_operations(operations), settings_data(row),
                            model=model, generation_id=generation_id, require_coverage=False,
                            origin_type='model' if model else 'manual')
    mapping = {op['temp_id']: uid() for op in operations if op['action'] == 'add'}
    for op in operations:
        # final 以草稿编号为键：新增用临时编号，修改和取消用正式 ID。
        if op['action'] == 'add':
            key, data = mapping[op['temp_id']], clean_task(final[op['temp_id']])
        else:
            key, data = op['target_id'], clean_task(final[op['target_id']])
        # 同批新增任务之间的前置依赖先用临时编号表达，写入前统一换成正式 ID。
        for dep in data['details']['dependencies']:
            dep['task_id'] = mapping.get(dep['task_id'], dep['task_id'])
        dao.write_task(session, row.id, key, storage_data(data), current.get(key))
    return mapping


# 用途：调用模型生成待确认日程建议。
# 参数：sessions 为会话工厂，pid 为项目，request 含计划 revision 和指令，model 可替换模型。
# 返回及副作用：返回最新日程；模型等待期间关闭读取会话，返回后重验计划及剧本并写草稿、事件；失败回滚，不改正式任务。
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


# 用途：读取仍待确认的指定日程草稿。
# 参数：row 为计划模型，draft_id 为可选预期草稿 ID。
# 返回及副作用：返回深复制草稿；不存在、状态已变或 ID 不符抛 BusinessError。
def require_draft(row, draft_id=None):
    draft = row.draft
    if not draft or draft['status'] != 'pending' or (draft_id and draft['id'] != draft_id):
        raise BusinessError(409, '待确认草稿不存在或已处理')
    return deepcopy(draft)


# 用途：保存人工调整后的待审日程草稿。
# 参数：session/pid 为会话及项目，request 含 revision、draft_id 和完整建议结果。
# 返回及副作用：重验计划及剧本依据、模拟检查后提交草稿并返回日程；过期或不合法抛 BusinessError，不改正式任务。
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


# 用途：幂等确认日程草稿并应用正式任务。
# 参数：session/pid 为会话及项目，request 含 revision 和 draft_id。
# 返回及副作用：项目锁内检查确认事件，映射新增任务 ID、更新依赖并写事件后提交；返回日程，过期或非法抛 BusinessError。
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
        dao.write_task(session, row.id, key, storage_data(data), rows.get(key))
        changes.append({'task_id': key, 'before': current.get(ref), 'after': data})
    row.source_script_id = draft['source']['script_id'] if draft['source'] else None
    row.source_script_revision = draft['source']['revision'] if draft['source'] else None
    draft['status'] = 'confirmed'; draft['confirmed_at'] = now()
    row.draft = draft
    add_event(session, pid, 'planning_confirm', {'draft_id': draft['id'], 'changes': changes, 'revision': row.revision})
    session.commit()
    return read(session, pid)


# 用途：丢弃待审日程草稿。
# 参数：session/pid 为会话及项目，request 含 revision 和 draft_id。
# 返回及副作用：领取版本、标记草稿 discarded、写事件后提交并返回日程；冲突或草稿不存在抛 BusinessError。
def discard(session, pid, request):
    row = lock(session, pid, request.revision)
    draft = require_draft(row, request.draft_id)
    draft['status'] = 'discarded'
    row.draft = draft
    add_event(session, pid, 'planning_discard', {'draft_id': draft['id'], 'revision': row.revision})
    session.commit()
    return read(session, pid)


# 用途：读取任务明确关联版本的正式场次证据。
# 参数：session/pid 为会话及项目，task_id/script_id/scene_id 指定关联关系。
# 返回及副作用：返回任务、剧本、场次和原文；引用不存在或不属于任务抛 BusinessError；不读取文件草稿。
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


# 用途：筛选需要补全部门的任务。
# 参数：snapshot 为日程读取结果，可能包含待审草稿。
# 返回及副作用：返回 ref 到任务的映射；有草稿时仅处理该草稿，跳过已有部门、完成及取消项；草稿过期抛 BusinessError。
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


# 用途：调用模型为缺少主责部门的任务补建议。
# 参数：sessions 为会话工厂，request 含计划 revision，model 为可选模型。
# 返回及副作用：最多处理 300 项，模型后重验依据并仅写待审草稿和事件；返回日程，建议遗漏、重复或版本变化抛 BusinessError。
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
