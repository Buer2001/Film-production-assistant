# 文件职责：V5 各步骤的实现；每步只做一件事，返回下一步和状态更新，不自行提交业务数据。
"""步骤函数不改状态机规则，只产出结果；步骤边界的状态保存在运行器中完成。"""
from datetime import date
from backend.ai import agent as ai_agent
from backend.agent.context import build_run_context
from backend.service import agent_work, planning, shooting

# 自检预算：修正最多两轮、模型调用总数上限，避免无进展时反复调用。
MAX_REVISE = 2
MAX_MODEL_CALLS = 6


# 判断安排是否落在范围日期内；没有范围日期时视为全部在范围内。
def _date_in_scope(value, scope):
    if not scope.get('start_date') or not scope.get('end_date'):
        return True
    day = date.fromisoformat(value[:10])
    return date.fromisoformat(scope['start_date']) <= day <= date.fromisoformat(scope['end_date'])


# 判断任务计划期是否与范围有交集；没有计划日期的任务不因此被排除。
def _task_in_scope(task, scope):
    if not scope.get('start_date') or not scope.get('end_date'):
        return False
    start = scope['start_date']
    end = scope['end_date']
    planned_start = task.get('planned_start') or end
    planned_end = task.get('planned_end') or start
    return planned_start <= end and planned_end >= start


# 累计模型调用次数，供预算判断使用。
def _spent(state):
    return (state.get('model_calls') or 0) + 1


# 预算用尽时不再调用模型，转人工决定，避免同一请求反复生成。
def _out_of_budget(state):
    return (state.get('model_calls') or 0) >= MAX_MODEL_CALLS


# 理解要求并检查硬门槛：开拍日期必须有，涉及场次时必须有已确认剧本。
async def step_understand(session, pid, run, payload):
    state = run.state_json or {}
    patch, columns = {}, {}
    if not state.get('scope') and state.get('message') and not _out_of_budget(state):
        # 读快照后先提交，等待模型期间不持有业务事务和项目锁。
        context = build_run_context(session, pid, state)
        session.commit()
        result = await ai_agent.understand({**context, 'mode_hint': run.mode},
                                           context={'project_id': pid})
        patch.update({'scope': result['scope'], 'constraints': result['constraints'],
                      'assumptions': result['assumptions'], 'questions': result['questions'],
                      'model_calls': _spent(state)})
        columns['mode'] = result['mode']
        state = {**state, **patch}

    plan = planning.read(session, pid)
    candidate = state.get('candidate') or {}
    operations = candidate.get('operations') or []
    questions = list(state.get('questions') or [])
    # 候选由后续 propose 步骤生成，这里只要求制片确实提出了要求。
    if not operations and not state.get('message'):
        questions.append('请说明这次要调整的任务或拍摄安排。')
    if not state.get('scope'):
        questions.append('请说明要编排的阶段和日期范围。')
    if not plan['settings'].get('shoot_start'):
        questions.append('请先在项目日程填写开拍日期，编排需要它判断安排先后。')
    needs_script = any(op['entity'] == 'shooting_item' or
                       isinstance((op.get('patch') or {}).get('details'), dict) and
                       (op.get('patch') or {})['details'].get('scene_refs')
                       for op in operations)
    if needs_script and not plan['source']:
        questions.append('当前没有已确认剧本，本次只能编排项目任务；拍摄安排请等剧本确认后再提交。')
    if questions:
        return {'next': 'clarify', 'patch': {**patch, 'questions': questions}, 'columns': columns}
    return {'next': 'load', 'patch': {**patch, 'questions': []}, 'columns': columns}


# 读取正式来源并记录两个基准版本；后续步骤和确认都以这两个版本为准。
async def step_load(session, pid, run, payload):
    plan = planning.read(session, pid)
    data = shooting.read(session, pid)
    source = plan['source']
    return {'next': 'impact' if run.mode == 'reschedule' else 'propose',
            'patch': {'source': source, 'settings': plan['settings'], 'questions': []},
            'columns': {'base_plan_revision': plan['revision'], 'base_project_revision': data['revision'],
                        'source_json': source or {}}}


# 分析变化影响：按场次、资源和计划日期找出受影响的任务与安排，关系全部来自程序查询。
async def step_impact(session, pid, run, payload):
    scope = (run.state_json or {}).get('scope') or {}
    data = shooting.read(session, pid)
    items = [row for row in data['items']
             if row['data']['status'] != 'cancelled' and _date_in_scope(row['data']['start_at'], scope)]
    scene_ids = {row['data']['scene_id'] for row in items if row['data'].get('scene_id')}
    resource_ids = {rid for row in items for rid in row['data'].get('resource_ids') or []}
    task_ids = []
    for task in data['tasks']:
        if task['status'] == 'cancelled':
            continue
        details = task.get('details') or {}
        if any(ref.get('scene_id') in scene_ids for ref in details.get('scene_refs') or []):
            task_ids.append(task['id'])
        elif any(ref.get('record_id') in resource_ids for ref in details.get('resource_refs') or []):
            task_ids.append(task['id'])
        elif _task_in_scope(task, scope):
            task_ids.append(task['id'])
    impact = {'item_ids': [row['id'] for row in items], 'task_ids': task_ids,
              'scene_ids': sorted(scene_ids)}
    return {'next': 'propose', 'patch': {'impact': impact}, 'columns': {}}


# 形成候选方案：制片已提交候选时直接使用，否则由模型生成。
async def step_propose(session, pid, run, payload):
    state = run.state_json or {}
    candidate = state.get('candidate') or {}
    if candidate.get('operations'):
        return {'next': 'validate', 'patch': {}, 'columns': {}}
    if _out_of_budget(state):
        return {'next': 'clarify', 'patch': {'questions': ['模型调用次数已达上限，请缩小范围后重试。']},
                'columns': {}}
    context = build_run_context(session, pid, state)
    session.commit()
    result = await ai_agent.propose(context, context={'project_id': pid})
    # 来源固定标记为模型，人员落实字段由业务规则继续拦截。
    result['origin'] = 'model'
    return {'next': 'validate', 'patch': {'candidate': result, 'model_calls': _spent(state)},
            'columns': {}}


# 程序检查：在候选合并后的整体视图上检查，并计算范围漏排。
# 检查时补齐的当前值回写到候选，审阅界面据此展示改动前后。
async def step_validate(session, pid, run, payload):
    validation = agent_work.inspect_candidate(session, pid, run)
    candidate = {**((run.state_json or {}).get('candidate') or {}),
                 'operations': validation.pop('operations')}
    patch = {'validation': validation, 'candidate': candidate, 'questions': validation['questions']}
    return {'next': 'clarify' if validation['blocked'] else 'reflect',
            'patch': patch, 'columns': {}}


# 模型复核：对照要求检查遗漏、越界、虚构和解释；制片自己提交的候选不做模型复核。
async def step_reflect(session, pid, run, payload):
    state = run.state_json or {}
    candidate = state.get('candidate') or {}
    if candidate.get('origin') != 'model':
        return {'next': 'save_draft', 'patch': {'reflect_status': 'skipped_manual'}, 'columns': {}}
    if _out_of_budget(state):
        return {'next': 'clarify', 'patch': {'questions': ['模型调用次数已达上限，请缩小范围后重试。']},
                'columns': {}}
    context = build_run_context(session, pid, state)
    session.commit()
    result = await ai_agent.reflect({**context, 'candidate': candidate,
                                     'validation': state.get('validation')},
                                    context={'project_id': pid})
    attempts = dict(state.get('attempts') or {'revise': 0, 'reflect': 0})
    attempts['reflect'] = (attempts.get('reflect') or 0) + 1
    findings = result['findings']
    patch = {'review_findings': findings, 'reflect_status': result['verdict'],
             'attempts': attempts, 'model_calls': _spent(state)}
    if result['verdict'] == 'ok' or not findings:
        return {'next': 'save_draft', 'patch': patch, 'columns': {}}
    if result['verdict'] == 'need_user' or any(item['needs_user'] for item in findings):
        questions = [item['message'] for item in findings if item['needs_user']] or \
                    [result['summary'] or '模型复核需要制片决定。']
        return {'next': 'clarify', 'patch': {**patch, 'questions': questions}, 'columns': {}}
    if (attempts.get('revise') or 0) >= MAX_REVISE:
        return {'next': 'clarify',
                'patch': {**patch, 'questions': [item['message'] for item in findings]}, 'columns': {}}
    return {'next': 'revise', 'patch': patch, 'columns': {}}


# 只针对复核发现的问题修正候选；修正后重新运行程序检查和模型复核。
async def step_revise(session, pid, run, payload):
    state = run.state_json or {}
    if _out_of_budget(state):
        return {'next': 'clarify', 'patch': {'questions': ['模型调用次数已达上限，请缩小范围后重试。']},
                'columns': {}}
    context = build_run_context(session, pid, state)
    session.commit()
    result = await ai_agent.revise({**context, 'candidate': state.get('candidate'),
                                    'findings': state.get('review_findings') or []},
                                   context={'project_id': pid})
    result['origin'] = 'model'
    attempts = dict(state.get('attempts') or {'revise': 0, 'reflect': 0})
    attempts['revise'] = (attempts.get('revise') or 0) + 1
    return {'next': 'validate',
            'patch': {'candidate': result, 'attempts': attempts, 'review_findings': [],
                      'model_calls': _spent(state)},
            'columns': {}}


# 保存联合草稿并进入待审阅；草稿不是正式数据，确认后才执行。
async def step_save_draft(session, pid, run, payload):
    draft = agent_work.save_draft(session, pid, run)
    return {'next': 'review', 'patch': {'draft_id': draft.id, 'questions': []},
            'columns': {'draft_id': draft.id}}
