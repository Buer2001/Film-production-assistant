# 文件职责：检查通用拍摄安排的条件缺失、旧筹备记录状态及资源时间冲突。
# 用途：检查安排就绪程度、跨日和资源占用重叠。
# 参数：records 为含 kind、id、data 的通用记录列表。
# 返回及副作用：返回 unknown、readiness、conflict 提醒；仅对同一天且有开始时刻的安排比较占用，不修改输入。
def check_schedule(records):
    warnings = []
    slots = [r for r in records if r['kind'] == 'schedule']
    by_id = {r['id']: r for r in records}
    for r in slots:
        d = r['data']
        if not d.get('date') or not d.get('start') or d['status'] == '待确认':
            warnings.append({'type': 'unknown', 'ids': [r['id']], 'message': f"{d['title']}：日期、时间或拍摄条件待确认"})
        for scene in d['scene_ids']:
            for task in records:
                if task['kind'] == 'task' and scene in task['data']['scene_ids'] and task['data']['status'] not in ('已确认', '已完成'):
                    warnings.append({'type': 'readiness', 'ids': [r['id'], task['id']], 'message': f"{d['title']}：{task['data']['title']}尚未落实"})
    for i, a in enumerate(slots):
        x = a['data']
        if not x.get('date') or not x.get('start'):
            continue
        start = lambda d: int(d['start'][:2]) * 60 + int(d['start'][3:5])
        if start(x) + x['minutes'] > 1440:
            warnings.append({'type': 'conflict', 'ids': [a['id']], 'message': f"{x['title']}跨越午夜，请拆分安排"})
        for b in slots[i + 1:]:
            y = b['data']
            if x['date'] != y.get('date') or not y.get('start'):
                continue
            shared = set(x['resources']) & set(y['resources'])
            if shared and start(x) < start(y) + y['minutes'] and start(y) < start(x) + x['minutes']:
                warnings.append({'type': 'conflict', 'ids': [a['id'], b['id']], 'message': f"{x['title']} / {y['title']}占用重叠：{'、'.join(sorted(shared))}"})
    return warnings
