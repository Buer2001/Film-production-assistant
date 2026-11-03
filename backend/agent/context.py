import json
from backend.models.event import Event
from backend.service.project import rows, state


def build_context(s, pid, session_id):
    project = state(s, pid)
    # Keep project context bounded. Full records are retrieved through tools.
    index = [{'id': r['id'], 'kind': r['kind'], 'title': r['data']['title'],
              'status': r['data']['status']} for r in project['records'][:150]]
    context = {'project': project['name'], 'revision': project['revision'],
               'index': index, 'index_truncated': len(project['records']) > 150,
               'totals': project['totals'], 'planning_summary': project['planning_summary'],
               'task_boundary': '任务统一在项目日程维护；旧records中的task仅为历史，不代表当前日程，禁止新增或修改。'}
    sessions = sorted((e for e in rows(s, Event, pid) if e.type == 'chat'
                       and e.data.get('session_id') == session_id), key=lambda e: e.created_at)
    messages = []
    for event in sessions[-3:]:
        messages.extend([{'role': 'user', 'content': event.data['message']},
                         {'role': 'assistant', 'content': event.data['answer']}])
    return json.dumps(context, ensure_ascii=False), messages
