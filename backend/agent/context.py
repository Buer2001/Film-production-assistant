# 文件职责：为旧对话组装有界项目索引，为 V5 组装范围相关的正式资料快照。
import json
from backend.models.event import Event
from backend.service.project import rows, state


# 用会话 s、项目 pid 和 session_id 构建上下文；返回项目 JSON 文本及最近三轮消息，不修改项目。
def build_context(s, pid, session_id):
    project = state(s, pid)
    # Keep project context bounded. Full records are retrieved through tools.
    # 只注入前 150 条记录索引，避免把完整项目作为每轮模型上下文；截断标志交给模型判断是否继续查询。

    index = [{'id': r['id'], 'kind': r['kind'], 'title': r['data']['title'],
              'status': r['data']['status']} for r in project['records'][:150]]
    context = {'project': project['name'], 'revision': project['revision'],
               'index': index, 'index_truncated': len(project['records']) > 150,
               'totals': project['totals'], 'planning_summary': project['planning_summary'],
               'task_boundary': '任务统一在项目日程维护；旧records中的task仅为历史，不代表当前日程，禁止新增或修改。'}
    sessions = sorted((e for e in rows(s, Event, pid) if e.type == 'chat'
                       and e.data.get('session_id') == session_id), key=lambda e: e.created_at)
    messages = []

    # 只恢复当前 session_id 的最近三轮对话，其他会话不进入本轮历史。
    for event in sessions[-3:]:
        messages.extend([{'role': 'user', 'content': event.data['message']},
                         {'role': 'assistant', 'content': event.data['answer']}])
    return json.dumps(context, ensure_ascii=False), messages


# 组装 V5 步骤所需的正式资料快照；只保留范围相关的有界字段，不灌入整套项目事实。
def build_run_context(session, pid, run_state):
    # 延迟导入，避免上下文模块与服务层在导入阶段互相依赖。
    from backend.service import planning, shooting
    plan = planning.read(session, pid)
    data = shooting.read(session, pid)
    tasks = [{'id': row['id'], 'title': row['title'], 'phase': row['phase'], 'status': row['status'],
              'planned_start': row['planned_start'], 'planned_end': row['planned_end'],
              'dependencies': row['details'].get('dependencies', []),
              'scene_refs': row['details'].get('scene_refs', []),
              'estimate_days': row['details'].get('estimate_days')}
             for row in data['tasks'][:200]]
    items = [{'id': row['id'], **{key: row['data'].get(key) for key in
              ('title', 'kind', 'status', 'start_at', 'end_at', 'scene_id', 'location')}}
             for row in data['items'][:200]]
    scenes = [{'id': row['id'], 'scene_number': row['scene_number'], 'location': row['location']}
              for row in data['scenes'][:200]]
    people = [{'id': row['id'], 'name': row['name'], 'department': row.get('department', '')}
              for row in data['people']]
    resources = [{'id': row['id'], 'title': row['data'].get('title'),
                  'preparation': (row['data'].get('preparation') or {}).get('status', 'pending')}
                 for row in data['resources']]
    return {'scope': run_state.get('scope'), 'message': run_state.get('message', ''),
            'settings': plan['settings'], 'source': plan['source'],
            'constraints': run_state.get('constraints') or [],
            'assumptions': run_state.get('assumptions') or [],
            'impact': run_state.get('impact'),
            'tasks': tasks, 'items': items, 'scenes': scenes,
            'people': people, 'resources': resources}
