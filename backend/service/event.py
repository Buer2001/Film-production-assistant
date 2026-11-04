# 文件职责：读取项目事件，在最终回答生成后保存对话事件。
from backend.service.project import get_project
from backend.dao import event as dao


# 用途：读取项目最近事件。
# 参数：s/pid 为会话及项目 ID。
# 返回及副作用：返回按时间倒序的至多 100 条事件；项目不存在抛 BusinessError，不提交。
def list_events(s, pid):
    get_project(s, pid)
    return [{'id': event.id, 'type': event.type, 'data': event.data, 'created_at': event.created_at}
            for event in sorted(dao.list_events(s, pid), key=lambda event: event.created_at, reverse=True)[:100]]


# 用途：记录最终对话结果。
# 参数：s/pid 为会话及项目，data 为对话数据。
# 返回及副作用：无返回值；写 chat 事件并提交当前会话。
def save_chat(s, pid, data):
    # 一次对话仅在最终回答生成后记录；工具草稿各自保留原有提交边界。
    dao.add_event(s, pid, 'chat', data)
    s.commit()
