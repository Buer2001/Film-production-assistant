# 文件职责：以传入快照检查任务依赖、时间约束及检查项覆盖，不访问数据库或模型。
"""无数据库/模型依赖的安排检查；返回可解释的提醒。"""
from datetime import datetime, timedelta, timezone
from backend.common.errors import BusinessError


# 用途：取得东八区当前日期。
# 参数：无参数。
# 返回及副作用：返回 date，避免受服务器本地时区影响。
def today():
    return datetime.now(timezone(timedelta(hours=8))).date()


# 用途：校验任务依赖图并汇总日期和约束提醒。
# 参数：tasks 为带 ID 的任务字典列表，settings 为计划节点日期设置。
# 返回及副作用：返回提醒列表；重复依赖、自引用、缺失依赖、仍被依赖的取消项或循环依赖抛 BusinessError，不改输入。
def check_tasks(tasks, settings):
    index = {t['id']: t for t in tasks}
    graph = {}
    warnings = []
    for task in tasks:
        key, detail = task['id'], task['details']
        deps = [d['task_id'] for d in detail['dependencies']]
        if len(deps) != len(set(deps)):
            raise BusinessError(422, '任务前置依赖重复')
        graph[key] = deps
        for dep in deps:
            if dep not in index or dep == key:
                raise BusinessError(422, '前置任务不存在、跨计划或引用自身')
            before = index[dep]
            if task['status'] not in ('cancelled', 'completed') and before['status'] == 'cancelled':
                raise BusinessError(422, '仍被依赖的任务不能取消，请先调整依赖')
            if task.get('planned_start') and before.get('planned_end') and task['planned_start'] < before['planned_end']:
                warnings.append({'code': 'dependency_start_before', 'task_id': key, 'message': '开始日期早于前置任务的计划完成日期'})
            if task.get('planned_end') and before.get('planned_end') and task['planned_end'] < before['planned_end']:
                warnings.append({'code': 'dependency_end_before', 'task_id': key, 'message': '完成日期早于前置任务的计划完成日期'})
        start, end = task.get('planned_start'), task.get('planned_end')
        if task['status'] not in ('completed', 'cancelled'):
            if end and end < today().isoformat():
                warnings.append({'code': 'overdue_or_past', 'task_id': key, 'message': '已逾期或建议日期已经过去，请核对是否来得及'})
            if not end:
                warnings.append({'code': 'due_unknown', 'task_id': key, 'message': '完成日期待定'})
        for c in detail['constraints']:
            target = c.get('date')
            if c['kind'] == 'relative_to_milestone':
                anchor = settings.get(c['milestone'])
                if not anchor:
                    warnings.append({'code': 'milestone_missing', 'task_id': key, 'message': '时间约束对应的项目节点日期未确定'})
                if anchor:
                    target = (datetime.fromisoformat(anchor).date() + timedelta(days=c['offset_days'])).isoformat()
            actual = start if c['kind'] == 'start_on_or_after' else end
            violated = actual and target and (actual < target if c['kind'] == 'start_on_or_after' else actual > target)
            if violated:
                warnings.append({'code': 'constraint_violated', 'task_id': key, 'message': '安排违反时间约束' + ('（已确认硬期限）' if c['confirmation'] == 'confirmed' and c['strength'] == 'hard' else '（需核对）')})
            if c['confirmation'] == 'pending':
                warnings.append({'code': 'constraint_pending', 'task_id': key, 'message': '时间约束尚未确认：' + (c['source'] or '请补充来源')})
    # visiting 只记录当前递归路径以识别环；done 避免共享前置任务被重复遍历。
    visiting, done = set(), set()
    # 用途：以深度优先遍历检测依赖环。
    # 参数：key 为任务 ID，闭包 graph/visiting/done 为依赖图及遍历状态。
    # 返回及副作用：无返回值；维护递归路径和完成集合，遇到当前路径中的节点抛 BusinessError。
    def visit(key):
        if key in visiting:
            raise BusinessError(422, '任务依赖形成循环')
        if key in done:
            return
        visiting.add(key)
        for dep in graph[key]:
            visit(dep)
        visiting.remove(key); done.add(key)
    for key in graph:
        visit(key)
    return warnings


# 用途：检查模型是否完整覆盖检查框架并关联有效任务。
# 参数：result 为建议结果，checklist 为检查项列表，task_ids 为有效任务 ID 集合。
# 返回及副作用：无返回值；检查项缺失、重复、未知或关联不合法抛 BusinessError，不修改输入。
def check_coverage(result, checklist, task_ids):
    required = {x['id'] for x in checklist}
    actual = [x['check_id'] for x in result['coverage']]
    if len(actual) != len(set(actual)) or set(actual) != required:
        raise BusinessError(422, '模型检查框架覆盖不完整、重复或包含未知检查项')
    for item in result['coverage']:
        if not set(item['task_refs']) <= task_ids or (item['status'] == 'addressed' and not item['task_refs']):
            raise BusinessError(422, '检查项缺少有效任务关联')
