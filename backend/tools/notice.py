# 文件职责：对照已发布快照及当前记录判断通告是否过期，不依赖事件历史。
# 用途：比较通告当天安排及其场次关联筹备事项。
# 参数：notice 为通告模型，records 为当前项目记录字典列表。
# 返回及副作用：返回 stale 及具体原因；依据原快照当天场次筛选，识别删除、修改和新增，不写数据。
def notice_status(notice, records):
    """按当天快照比较当前数据，不依赖项目版本或事件历史。"""
    snapshot = notice.snapshot['records']
    slots = [r for r in snapshot
             if r['kind'] == 'schedule' and r['data'].get('date') == notice.date]
    scenes = {scene for r in slots for scene in r['data'].get('scene_ids', [])}

    # 用途：判断记录是否属于本次通告比较范围。
    # 参数：record 为记录字典，闭包 scenes 来自快照当天安排。
    # 返回及副作用：返回 bool；包含当天安排及关联这些场次的旧 task/requirement 记录。
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
