# 文件职责：对正式拍摄事实执行纯规则检查、选择当天来源并计算稳定指纹，不查询数据库。
import hashlib
import json
from datetime import datetime, time, timedelta, date
from itertools import combinations
from backend.tools.preparation import availability_problem, check_preparation


# 完整本地时间区间采用左闭右开，相邻安排不冲突，跨午夜无需拆成两条记录。
def overlaps(a, b):
    return a['start_at'] < b['end_at'] and b['start_at'] < a['end_at']


# 将安排时间映射到 V3 公用的时段结构，复用可用区间合并和未知提示规则。
def usage(data):
    start, end = datetime.fromisoformat(data['start_at']), datetime.fromisoformat(data['end_at'])
    return {'start_date': start.date().isoformat(), 'end_date': end.date().isoformat(),
            'start_time': start.time().isoformat(), 'end_time': end.time().isoformat()}


# task.details.scene_refs 使用稳定 scene_id；同时检查明确绑定同一资源的任务，不猜标题。
def relevant_tasks(tasks, scene_ids, resource_ids):
    return [t for t in tasks if t['status'] != 'cancelled' and t.get('phase') != 'closing' and (
        any(r.get('scene_id') in scene_ids for r in t['details'].get('scene_refs', [])) or
        any(r.get('record_id') in resource_ids for r in t['details'].get('resource_refs', [])))]


# 参数为序列化安排、人员、资源及任务；返回带 item_id 的提醒，不自动阻止制片保存。
def check_shooting(items, people, resources, tasks):
    active = [r for r in items if r['data']['status'] != 'cancelled']
    issues = []
    for left, right in combinations(active, 2):
        if not overlaps(left['data'], right['data']):
            continue
        for field, code, label in [('person_ids', 'person_overlap', '人员'), ('resource_ids', 'resource_overlap', '资源')]:
            if set(left['data'][field]) & set(right['data'][field]):
                issues.append({'code': code, 'item_id': left['id'], 'other_item_id': right['id'],
                               'message': f'「{left["data"]["title"]}」和「{right["data"]["title"]}」占用相同{label}，时间重叠'})
    people_by_id = {p['id']: p for p in people}
    resources_by_id = {r['id']: r['data'] for r in resources}
    for item in active:
        data = item['data']
        if data['kind'] == 'shoot':
            for field, label in [('person_ids', '参与人员'), ('resource_ids', '占用资源')]:
                if not data[field]:
                    issues.append({'code': field + '_unknown', 'item_id': item['id'],
                                   'message': f'「{data["title"]}」尚未指定{label}，暂不能完整检查占用'})
        for field, index, resource in [('person_ids', people_by_id, False), ('resource_ids', resources_by_id, True)]:
            for oid in data[field]:
                obj = index.get(oid)
                if obj is None:
                    issues.append({'code': 'reference_missing', 'item_id': item['id'], 'message': f'「{data["title"]}」存在失效引用，请重新选择'})
                    continue
                preparation = (obj.get('preparation') or {}) if resource else obj
                label = obj.get('title') if resource else obj['name']
                if resource and preparation.get('status') != 'confirmed':
                    issues.append({'code': 'resource_pending', 'item_id': item['id'], 'message': f'「{data["title"]}」：{label}尚未落实确认'})
                problem = availability_problem(usage(data), preparation.get('availability', []))
                if problem:
                    issues.append({'code': problem[0], 'item_id': item['id'], 'message': f'「{data["title"]}」：{label}，{problem[1]}'})
        related = relevant_tasks(tasks, {data['scene_id']}, set(data['resource_ids']))
        for task in related:
            if task['status'] != 'completed':
                issues.append({'code': 'preparation_unfinished', 'item_id': item['id'], 'task_id': task['id'],
                               'message': f'「{data["title"]}」关联任务「{task["title"]}」尚未完成'})
            # 准备任务的已落实对象不自动视为已安排到场；缺少占用引用时提示人工选择。
            required_resources = {r['record_id'] for r in task['details'].get('resource_refs', []) if r.get('record_id')}
            if required_resources - set(data['resource_ids']):
                issues.append({'code': 'resource_not_assigned', 'item_id': item['id'], 'task_id': task['id'],
                               'message': f'「{task["title"]}」关联的资源尚未全部加入「{data["title"]}」占用，请核实实际使用资源'})
        for issue in check_preparation(related, resources, people):
            issues.append({**issue, 'item_id': item['id']})
    return issues


# 当天通告包含与该日有交集的安排；取消项不进入执行快照，零点结束不算次日占用。
def day_items(items, day):
    start = datetime.combine(date.fromisoformat(day), time.min)
    end = start + timedelta(days=1)
    return [r for r in items if r['data']['status'] != 'cancelled' and
            datetime.fromisoformat(r['data']['start_at']) < end and datetime.fromisoformat(r['data']['end_at']) > start]


# 仅散列快照实际使用的来源，不包含全局 revision，避免无关日期变更使通告过期。
def fingerprint(source):
    return hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


# 导出只读取冻结快照，不能以当前名称或安排重建历史；文本不包含其他日期的个人资料。
def export_notice_text(notice):
    snap = notice.snapshot
    source = snap['source']
    lines = [f'{source["project"]} | {notice.date} 通告 V{notice.version}', f'发布时间：{notice.created_at}', '']
    for key, label in [('assembly', '集合'), ('makeup', '交妆'), ('transport', '交通'), ('meals', '用餐'), ('notes', '注意事项')]:
        lines.extend([f'【{label}】', snap['details'][key] or '待补充', ''])
    people = {p['id']: p['name'] for p in source['people']}
    resources = {r['id']: r['data']['title'] for r in source['resources']}
    scenes = {r['id']: r for r in source['scenes']}
    for row in source['items']:
        data = row['data']
        scene = scenes.get(data['scene_id'])
        lines.append(f'{data["start_at"].replace("T", " ")} — {data["end_at"].replace("T", " ")} | {data["title"]}')
        if scene:
            lines.append(f'场次：{scene["scene_number"]}（剧本 V{scene["script_version"]}） {scene["atmosphere"]} {scene["interior_exterior"]} | {scene["summary"]}')
        lines.extend([f'地点：{data["location"] or (scene["location"] if scene else "待定")}',
                      f'人员：{"、".join(people.get(p, "资料缺失") for p in data["person_ids"])}',
                      f'资源：{"、".join(resources.get(r, "资料缺失") for r in data["resource_ids"])}', data['notes'], ''])
    return '\n'.join(lines)
