# 文件职责：V5 运行记录、联合草稿与统一执行；业务规则、版本和事务都在这一层落地。
"""联合草稿的生命周期：检查、保存、人工修改、幂等确认和整体回滚。"""
from backend.common.errors import BusinessError
from backend.dao import agent as dao, project as projects
from backend.dao.event import add_event
from backend.dao.script import scene as scenes
from backend.service.project import get_project
from backend.service import planning, shooting
from backend.tools import agent_checks
from backend.tools import shooting as shooting_rules

# 需要制片亲自填写的落实字段；模型来源的候选不得提交这些字段。
PERSONNEL_FIELDS = ('person_ids', 'usage_period', 'result_notes', 'requires_people')


# 发起一次工作：保存范围与候选后交给运行器逐步推进，提交只用于取得运行 ID。
def create_run(session, pid, *, mode, message, state):
    get_project(session, pid)
    run = dao.add_run(session, pid, mode=mode, request_text=message, state=state)
    session.commit()
    return run


# 收起一次工作：放弃时不改动任何正式数据，只更新运行和草稿状态。
def discard_run(session, pid, run):
    dao.set_run(session, run.id, fields={'status': 'abandoned', 'current_step': 'feedback'})
    session.commit()
    return run


# 人工修改草稿：递增 revision 使旧检查和旧确认失效，重新运行程序检查。
def edit_draft(session, pid, run, request):
    if run.status != 'waiting_review':
        raise BusinessError(409, '当前工作不在待审阅阶段')
    draft = dao.pending_draft(session, run.id)
    if draft is None:
        raise BusinessError(409, '没有待确认草稿')
    if draft.revision != request.revision:
        raise BusinessError(409, '草稿版本已变化，请刷新后重新修改')
    candidate = request.candidate.model_dump(mode='json')
    run.state_json = {**(run.state_json or {}), 'candidate': candidate}
    validation = inspect_candidate(session, pid, run)
    candidate['operations'] = validation.pop('operations')
    run.state_json = {**run.state_json, 'candidate': candidate}
    # 保留建议稿原文，人工修改后仍能对比建议稿与最终稿；revision 由条件更新递增。
    existing = draft.rationale_json or {}
    changed = dao.revise_draft(session, draft.id, request.revision, fields={
        'operations_json': {'schema_version': 1, 'operations': candidate.get('operations') or []},
        'validation_json': validation,
        'rationale_json': {'summary': candidate.get('summary', ''),
                           'assumptions': candidate.get('assumptions') or [],
                           'questions': candidate.get('questions') or [],
                           'proposal': existing.get('proposal') or []}})
    if changed != 1:
        raise BusinessError(409, '草稿已被其他操作修改，请刷新')
    session.commit()
    draft = dao.get_draft(session, pid, draft.id)
    return draft


# 放弃草稿：条件领取状态，成功后工作结束，不留待确认建议。
def discard_draft(session, pid, draft_id, request):
    draft = dao.get_draft(session, pid, draft_id)
    if draft is None:
        raise BusinessError(404, '草稿不存在或不属于本项目')
    if draft.revision != request.revision:
        raise BusinessError(409, '草稿版本已变化，请刷新')
    if dao.claim_draft(session, draft_id, request.revision, status='abandoned') != 1:
        raise BusinessError(409, '草稿已处理，请刷新')
    run = dao.get_run(session, pid, draft.run_id)
    if run is not None:
        dao.set_run(session, run.id, fields={'status': 'abandoned', 'current_step': 'feedback'})
    session.commit()
    return {'draft_id': draft_id, 'status': 'abandoned'}


# 判断候选是否提交了只能由制片填写的落实字段。
def _has_personnel(patch):
    if set(patch) & set(PERSONNEL_FIELDS):
        return True
    details = patch.get('details') or {}
    return bool(set(details) & set(PERSONNEL_FIELDS))


# 结构检查：模型来源不得填写人员落实字段，空草稿按缺口记录。
def _structural(operations, origin):
    issues = []
    if origin == 'model':
        for op in operations:
            if op['entity'] == 'project_task' and _has_personnel(op.get('patch') or {}):
                issues.append(agent_checks.issue(
                    'personnel_forbidden', '模型不能填写人员关联和落实结果，请由制片在草稿中补充',
                    task_id=op.get('target_id')))
    return issues


# 已排或候选已排的场次 ID；取消项不算已安排。
def _planned_scene_ids(view):
    return {row['data'].get('scene_id') for row in view
            if row['data'].get('scene_id') and row['data'].get('status') != 'cancelled'}


# 计算未排场次：只在首次编排时检查，重排模式只处理受影响对象。
def _uncovered(session, pid, run, view):
    state = run.state_json or {}
    scope = state.get('scope') or {}
    if run.mode != 'compose' or not scope.get('include_shooting', True):
        return []
    source = planning.source_data(session, pid)
    if not source:
        return []
    confirmed = [{'id': row.id, 'scene_number': row.scene_number, 'location': row.location}
                 for row in scenes.list_for_script(session, source['script_id'])]
    return agent_checks.uncovered_scenes(confirmed, _planned_scene_ids(view))


# 为修改和取消操作补上当前值，供审阅界面展示差异；执行时仍重新读库，不依赖这里的快照。
def _with_before(session, pid, operations):
    tasks = {row['id']: row for row in planning.read(session, pid)['tasks']}
    items = {row['id']: row['data'] for row in shooting.read(session, pid)['items']}
    enriched = []
    for op in operations:
        if op['action'] == 'add' or op.get('before'):
            enriched.append(op)
            continue
        source = tasks.get(op['target_id']) if op['entity'] == 'project_task' else items.get(op['target_id'])
        enriched.append({**op, 'before': source} if source else op)
    return enriched


# 程序检查：任务与拍摄安排合并在候选后的整体视图上检查，并补范围漏排。
def inspect_candidate(session, pid, run):
    state = run.state_json or {}
    candidate = state.get('candidate') or {}
    origin = candidate.get('origin', 'manual')
    operations = _with_before(session, pid, candidate.get('operations') or [])
    issues = _structural(operations, origin)
    task_ops = [op for op in operations if op['entity'] == 'project_task']
    item_ops = [op for op in operations if op['entity'] == 'shooting_item']

    if task_ops:
        try:
            _, warnings = planning.plan_task_ops(session, pid, task_ops, generation_id=run.id,
                                                 model=origin == 'model')
            issues += [agent_checks.from_warning(warning) for warning in warnings]
        except BusinessError as exc:
            issues.append(agent_checks.issue('task_invalid', getattr(exc, 'detail', str(exc))))

    try:
        view = shooting.plan_item_ops(session, pid, item_ops)
    except BusinessError as exc:
        # 安排合并失败时仍用现有安排计算缺口，避免漏排检查被连带跳过。
        issues.append(agent_checks.issue('item_invalid', getattr(exc, 'detail', str(exc))))
        view = shooting.plan_item_ops(session, pid, [])

    data = shooting.read(session, pid)
    for raw in shooting_rules.check_shooting(view, data['people'], data['resources'], data['tasks']):
        issues.append(agent_checks.issue(raw['code'], raw['message'], item_id=raw.get('item_id')))

    # 重排模式只应改动影响范围内的对象，范围外改动按缺口提示并说明原因。
    if run.mode == 'reschedule':
        impact = state.get('impact') or {}
        allowed = set(impact.get('task_ids') or []) | set(impact.get('item_ids') or [])
        for op in operations:
            if op.get('target_id') and op['target_id'] not in allowed:
                issues.append(agent_checks.issue('out_of_scope_change', '该对象不在本次变化的影响范围内',
                                                 task_id=op['target_id'] if op['entity'] == 'project_task' else None,
                                                 item_id=op['target_id'] if op['entity'] == 'shooting_item' else None))

    uncovered = _uncovered(session, pid, run, view)
    for scene in uncovered:
        issues.append(agent_checks.issue('scope_uncovered', f'场次 {scene["scene_number"]} 尚未安排拍摄',
                                         scene_id=scene['scene_id']))
    if not operations:
        issues.append(agent_checks.issue('no_change', '本次草稿没有任何调整'))

    issues = agent_checks.normalize(issues)
    blocked = agent_checks.blocked(issues)
    questions = list(candidate.get('questions') or [])
    if blocked:
        # 阻断原因逐条转成待确认问题，界面不依赖检查列表之外的信息。
        questions.extend(item['message'] for item in issues if item['level'] == agent_checks.BLOCK)
        questions.append('请修正阻断问题后重新提交，当前草稿不能确认执行。')
    return {'issues': issues, 'uncovered': uncovered, 'blocked': blocked, 'origin': origin,
            'questions': questions, 'operations': operations,
            'counts': {'task': len(task_ops), 'shooting': len(item_ops)}}


# 保存联合草稿：新草稿生效时把同运行其它待处理草稿标为失效，避免并存两份建议。
# rationale 同时保存建议稿原文，人工修改后仍能对比建议稿与最终稿的差异。
def save_draft(session, pid, run):
    state = run.state_json or {}
    candidate = state.get('candidate') or {}
    operations = candidate.get('operations') or []
    draft = dao.add_draft(session, pid, run.id,
                          operations={'schema_version': 1, 'operations': operations},
                          validation=state.get('validation') or {},
                          source=run.source_json or {},
                          rationale={'summary': candidate.get('summary', ''),
                                     'assumptions': candidate.get('assumptions') or [],
                                     'questions': candidate.get('questions') or [],
                                     'proposal': operations})
    dao.invalidate_pending(session, run.id, draft.id)
    return draft


# 记录影响日期的范围：改期时新旧两天都要复核，取消时看原安排。
def _affected_dates(item_ops, item_before):
    days = set()
    for op in item_ops:
        if op['action'] == 'cancel':
            source = item_before.get(op.get('target_id')) or {}
        else:
            source = op.get('patch') or {}
            old = item_before.get(op.get('target_id')) or {}
            for value in (old.get('start_at'), old.get('end_at')):
                if value:
                    days.add(value[:10])
        for value in (source.get('start_at'), source.get('end_at')):
            if value:
                days.add(value[:10])
    return days


# 只保留用于对比的字段，避免把完整任务详情写进执行记录。
TASK_FIELDS = ('title', 'phase', 'status', 'planned_start', 'planned_end')
ITEM_FIELDS = ('title', 'kind', 'status', 'start_at', 'end_at', 'scene_id')


# 取一条正式记录的展示快照；不存在时返回 None。
def _snapshot(entity, row):
    if not row:
        return None
    fields = TASK_FIELDS if entity == 'project_task' else ITEM_FIELDS
    return {key: row.get(key) for key in fields}


# 逐项记录执行前后的值，供结果页展示实际改动。
def _applied_changes(session, pid, task_ops, item_ops, task_mapping, item_mapping,
                     task_before, item_before):
    tasks = {row['id']: row for row in planning.read(session, pid)['tasks']}
    items = {row['id']: row['data'] for row in shooting.read(session, pid)['items']}
    rows = []
    for op in task_ops:
        key = task_mapping[op['temp_id']] if op['action'] == 'add' else op['target_id']
        rows.append({'op_id': op['op_id'], 'entity': 'project_task', 'action': op['action'],
                     'target_id': key, 'before': _snapshot('project_task', task_before.get(key)),
                     'after': _snapshot('project_task', tasks.get(key))})
    for op in item_ops:
        key = item_mapping[op['temp_id']] if op['action'] == 'add' else op['target_id']
        rows.append({'op_id': op['op_id'], 'entity': 'shooting_item', 'action': op['action'],
                     'target_id': key, 'before': _snapshot('shooting_item', item_before.get(key)),
                     'after': _snapshot('shooting_item', items.get(key))})
    return rows


# 比较建议稿和最终稿的操作，只记录被改写、新增或删除的项。
def _operations_diff(proposal, final):
    before = {op.get('op_id'): op for op in proposal or []}
    after = {op.get('op_id'): op for op in final or []}
    changes = []
    for op_id in sorted(set(before) | set(after)):
        old, new = before.get(op_id), after.get(op_id)
        if old is None:
            status = 'added'
        elif new is None:
            status = 'removed'
        elif old == new:
            continue
        else:
            status = 'modified'
        changes.append({'op_id': op_id, 'entity': (new or old).get('entity'), 'status': status})
    return {'edited': bool(changes), 'changes': changes,
            'proposal_count': len(before), 'final_count': len(after)}


# 复核已发布通告：只比较当天实际来源，来源变化才提示复核，不静默改写历史版本。
def notice_review(session, pid, days):
    from backend.dao import notice as notice_dao
    from backend.service import shooting as shooting_service
    pending = []
    for day in sorted(days):
        for notice in notice_dao.list_published(session, pid, day):
            if notice.snapshot.get('format') != 'shooting_v4':
                continue
            status = shooting_service.notice_status(session, pid, notice)
            if status['stale']:
                pending.append({'date': day, 'notice_id': notice.id, 'version': notice.version,
                                'reasons': status['reasons']})
    return pending


# 确认并执行草稿：业务修改、执行凭据、草稿状态和运行状态一次提交。
def confirm(session, pid, draft_id, request):
    draft = dao.get_draft(session, pid, draft_id)
    if draft is None:
        raise BusinessError(404, '草稿不存在或不属于本项目')
    execution = dao.get_execution(session, draft_id, request.revision)
    if execution is not None:
        # 已执行过：直接返回原结果，只修正可能滞后的运行状态，不重复写业务数据。
        run = dao.get_run(session, pid, draft.run_id)
        if run is not None and run.status != 'completed':
            dao.set_run(session, run.id, fields={'status': 'completed', 'current_step': 'feedback'})
        session.commit()
        return {'repeated': True, **execution.result_json}
    if draft.status != 'pending':
        raise BusinessError(409, '草稿已处理，请刷新')
    if draft.revision != request.revision:
        raise BusinessError(409, '草稿版本已变化，请刷新后重新审阅')
    run = dao.get_run(session, pid, draft.run_id)
    if run is None:
        raise BusinessError(404, '运行记录不存在')

    validation = draft.validation_json or {}
    uncovered = validation.get('uncovered') or []
    if uncovered and not request.accept_uncovered:
        numbers = '、'.join(item['scene_number'] for item in uncovered)
        raise BusinessError(422, f'仍有未安排的场次（{numbers}），请确认知情保留后再提交')

    # 事务外先复核来源版本，明确区分「数据变了」和「规则不允许」。
    plan = planning.read(session, pid)
    data = shooting.read(session, pid)
    if plan['revision'] != run.base_plan_revision or data['revision'] != run.base_project_revision:
        raise BusinessError(409, '正式数据已变化，请重新加载后再确认')
    if (plan['source'] or {}) != (run.source_json or {}):
        raise BusinessError(409, '剧本来源已变化，请重新生成建议')

    # 条件领取草稿状态：两个请求同时确认时只有一个能继续。
    if dao.claim_draft(session, draft_id, request.revision, status='confirmed') != 1:
        # 并发确认时另一个请求可能已经执行完；回滚后重查执行凭据，避免同一版草稿重复执行。
        session.rollback()
        execution = dao.get_execution(session, draft_id, request.revision)
        if execution is not None:
            run = dao.get_run(session, pid, draft.run_id)
            if run is not None and run.status != 'completed':
                dao.set_run(session, run.id, fields={'status': 'completed', 'current_step': 'feedback'})
            session.commit()
            return {'repeated': True, **execution.result_json}
        raise BusinessError(409, '草稿已被其他操作处理，请刷新')

    operations = (draft.operations_json or {}).get('operations') or []
    task_ops = [op for op in operations if op['entity'] == 'project_task']
    item_ops = [op for op in operations if op['entity'] == 'shooting_item']
    # 执行前记录旧值，执行后据此生成差异；界面展示不依赖候选里的 before 快照。
    task_before = {row['id']: row for row in plan['tasks']}
    item_before = {row['id']: row['data'] for row in data['items']}
    days = _affected_dates(item_ops, item_before)
    # 统一事务：按固定顺序领取计划版本和项目版本，再写任务、拍摄安排、事件和凭据。
    row = planning.lock(session, pid, run.base_plan_revision)
    if projects.claim_revision(session, pid, run.base_project_revision, increment=True) != 1:
        raise BusinessError(409, '项目版本已变化，请刷新后重新确认')
    task_mapping = planning.apply_task_ops(session, pid, row, task_ops, generation_id=run.id,
                                           model=validation.get('origin') == 'model')
    item_mapping = shooting.apply_item_ops(session, pid, item_ops)

    applied = _applied_changes(session, pid, task_ops, item_ops, task_mapping, item_mapping,
                               task_before, item_before)
    notices = notice_review(session, pid, days)
    result = {'draft_id': draft_id, 'draft_revision': request.revision,
              'task_ids': task_mapping, 'item_ids': item_mapping, 'uncovered': uncovered,
              'plan_revision': run.base_plan_revision + 1,
              'project_revision': run.base_project_revision + 1,
              'applied': applied,
              'diff': _operations_diff((draft.rationale_json or {}).get('proposal') or [],
                                       operations),
              'notices': notices}
    add_event(session, pid, 'agent_apply', {
        'draft_id': draft_id, 'revision': request.revision,
        'task_ids': list(task_mapping.values()), 'item_ids': list(item_mapping.values()),
        'uncovered': [item['scene_number'] for item in uncovered],
        'notices': [{'date': item['date'], 'notice_id': item['notice_id']} for item in notices]})
    dao.add_execution(session, pid, draft_id, request.revision, result)
    dao.set_run(session, run.id, fields={'status': 'completed', 'current_step': 'feedback',
                                         'draft_id': draft_id})
    session.commit()
    return result


# 序列化运行记录；等待中的工作据此展示当前步骤、问题和待审草稿。
# 已确认的草稿和执行结果也要返回，审阅页面才能展示实际做了什么、哪些通告需要复核。
def run_dict(session, run):
    state = run.state_json or {}
    draft = dao.get_draft(session, run.project_id, run.draft_id) if run.draft_id else dao.pending_draft(session, run.id)
    execution = dao.get_execution(session, draft.id, draft.revision) if draft is not None else None
    return {'id': run.id, 'project_id': run.project_id, 'mode': run.mode, 'status': run.status,
            'current_step': run.current_step, 'version': run.version, 'message': run.request_text,
            'scope': state.get('scope'), 'questions': state.get('questions') or [],
            'validation': state.get('validation'), 'impact': state.get('impact'),
            'reflect_status': state.get('reflect_status'),
            'draft': draft_dict(draft) if draft is not None else None,
            'execution': execution.result_json if execution is not None else None}


# 序列化草稿；检查结果和依据一起返回，供审阅界面展示。
def draft_dict(draft):
    return {'id': draft.id, 'run_id': draft.run_id, 'revision': draft.revision, 'status': draft.status,
            'operations': (draft.operations_json or {}).get('operations') or [],
            'validation': draft.validation_json or {}, 'source': draft.source_json or {},
            'rationale': draft.rationale_json or {}, 'created_at': draft.created_at}
