# 文件职责：根据明确录入的人员、资源及使用时段检查缺口，不用任务完成状态替代事实。
"""筹备缺口纯规则：只检查传入事实，不查库、不调模型、不修改原数据。"""
from datetime import date, datetime, time, timedelta


# 用途：将日期或带时刻的使用区间转换为可比较边界。
# 参数：period 含开始、结束日期和可选时刻。
# 返回及副作用：返回 datetime 起止二元组；全日范围包含末日，时刻范围左闭右开，非法 ISO 日期或时刻会传播解析异常。
def period_bounds(period):
    """日期范围含末日；有时刻的区间按左闭右开处理，相邻预约不算重叠。"""
    start_day = date.fromisoformat(period['start_date'])
    end_day = date.fromisoformat(period['end_date'])
    if period.get('start_time'):
        return (datetime.combine(start_day, time.fromisoformat(period['start_time'])),
                datetime.combine(end_day, time.fromisoformat(period['end_time'])))
    # 全日区间以次日零点为结束；兼容 Python 日期支持的最大末日。
    end = datetime.combine(end_day + timedelta(days=1), time.min) if end_day < date.max else datetime.max
    return datetime.combine(start_day, time.min), end


# 用途：检查使用时段是否获得明确可用覆盖。
# 参数：usage 为使用区间，availability 为带 available/unavailable 状态的区间列表。
# 返回及副作用：返回问题代码和说明二元组，无问题返回 None；不可用交叠优先，可拼接相邻可用段，不修改输入。
def availability_problem(usage, availability):
    """明确不可用优先；多个相邻可用段可以共同覆盖使用时段，空白不推断为可用。"""
    start, end = period_bounds(usage)
    available = []
    for item in availability:
        left, right = period_bounds(item)
        if item['state'] == 'unavailable' and left < end and right > start:
            return 'time_unavailable', '使用时段与明确不可用的时间重叠'
        if item['state'] == 'available':
            available.append((left, right))
    if not available:
        return 'availability_unknown', '尚无覆盖使用时段的可用确认，请核实'
    # 将可用区间按起点排序后连续推进覆盖边界；出现空隙即停止，不能把未知时间当作可用。
    cursor = start
    for left, right in sorted(available):
        if left > cursor:
            break
        cursor = max(cursor, right)
        if cursor >= end:
            return None
    return 'time_outside_available', '使用时段超出已录入的可用范围，请核实'


# 用途：汇总任务所需人员及资源的落实和时段问题。
# 参数：tasks/resources/people 为正式任务、资源和人员字典列表。
# 返回及副作用：返回问题列表；仅跳过取消项，完成但仍缺对象的任务额外提示结果缺口，不修改输入。
def check_preparation(tasks, resources, people):
    """状态完成不消除事实缺口；只跳过取消项，不凭标题猜测任务需求。"""
    resource_index = {r['id']: r['data'] for r in resources}
    person_index = {p['id']: p for p in people}
    issues = []
    for task in tasks:
        if task['status'] == 'cancelled':
            continue
        detail = task.get('details') or {}
        usage = detail.get('usage_period')
        unresolved = False

        # 用途：追加带关联标识的缺口。
        # 参数：code/message 为问题编码及说明，rid/person_id 为可选资源或人员 ID。
        # 返回及副作用：无返回值；将当前 task 的问题追加到闭包 issues 列表。
        def issue(code, message, *, rid=None, person_id=None):
            issues.append({'code': code, 'message': message, 'task_id': task['id'],
                           'resource_id': rid, 'person_id': person_id})

        # 用途：检查一项关联对象的预计使用时段。
        # 参数：availability 为可用记录，label 为对象名称，rid/person_id 为可选关联 ID。
        # 返回及副作用：无返回值；使用时段缺失或覆盖不完整时通过 issue 追加提醒，不用任务期限补造使用时段。
        def check_time(availability, label, *, rid=None, person_id=None):
            if not usage:
                issue('usage_unknown', f'{label}尚未填写预计使用时段，不能用任务期限代替', rid=rid, person_id=person_id)
            else:
                problem = availability_problem(usage, availability)
                if problem:
                    issue(problem[0], f'{label}：{problem[1]}', rid=rid, person_id=person_id)

        person_ids = detail.get('person_ids', [])
        if detail.get('requires_people') and not person_ids:
            if detail.get('assignees'):
                issue('people_unlinked', '实施人员仅有手填姓名，尚未关联人员资料')
            else:
                unresolved = True
                issue('people_unresolved', '该任务要求落实人员，尚未选择人员')
        for person_id in dict.fromkeys(person_ids):
            person = person_index.get(person_id)
            if person is None:
                unresolved = True
                issue('person_missing', '关联人员资料缺失，请重新核对', person_id=person_id)
            else:
                check_time(person.get('availability', []), person['name'], person_id=person_id)

        seen = set()
        for ref in detail.get('resource_refs', []):
            rid = ref.get('record_id')
            key = rid or ref['name']
            if key in seen:
                continue
            seen.add(key)
            if not rid:
                unresolved = True
                issue('resource_unresolved', f'“{ref["name"]}”尚未关联具体资源')
                continue
            resource = resource_index.get(rid)
            if resource is None:
                unresolved = True
                issue('resource_missing', '关联资源资料缺失，请重新核对', rid=rid)
                continue
            preparation = resource.get('preparation') or {}
            status = preparation.get('status', 'pending')
            if status == 'unavailable':
                unresolved = True
                issue('resource_unavailable', f'“{resource["title"]}”已标记不可用，需另行落实', rid=rid)
            elif status != 'confirmed':
                issue('resource_pending', f'“{resource["title"]}”尚未确认落实', rid=rid)
            check_time(preparation.get('availability', []), resource['title'], rid=rid)
        if task['status'] == 'completed' and unresolved:
            issue('result_missing', '任务已完成，但明确要求落实的人员或资源仍有缺口，请复核结果')
    return issues
