# 为对话组装有界项目索引和最近三轮会话，完整事实通过工具按需读取。
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
