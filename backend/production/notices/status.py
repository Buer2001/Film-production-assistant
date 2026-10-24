def notice_status(notice, records):
    """按当天快照比较当前数据，不依赖项目版本或事件历史。"""
    snapshot = notice.snapshot['records']
    slots = [r for r in snapshot
             if r['kind'] == 'schedule' and r['data'].get('date') == notice.date]
    scenes = {scene for r in slots for scene in r['data'].get('scene_ids', [])}

    def relevant(record):
        if record['kind'] == 'schedule':
            return record['data'].get('date') == notice.date
        return record['kind'] in ('task', 'requirement') and bool(
            scenes.intersection(record['data'].get('scene_ids', [])))

    before = {r['id']: r for r in snapshot if relevant(r)}
    current = {r['id']: r for r in records}
    reasons = []
    for rid, old in before.items():
        new = current.get(rid)
        label = '当天拍摄安排' if old['kind'] == 'schedule' else '当天筹备事项'
        title = old['data']['title']
        if new is None:
            reasons.append(f'{label}「{title}」已删除')
        elif new != old:
            if old['kind'] in ('task', 'requirement') and old['data'].get('status') != new['data'].get('status'):
                reasons.append(f'「{title}」状态由 {old["data"].get("status")} 变为 {new["data"].get("status")}')
            else:
                reasons.append(f'{label}「{title}」已改动')
    for record in records:
        if record['id'] not in before and relevant(record):
            label = '拍摄安排' if record['kind'] == 'schedule' else '筹备事项'
            reasons.append(f'当天新增{label}「{record["data"]["title"]}」')
    return {'stale': bool(reasons), 'reasons': reasons}
