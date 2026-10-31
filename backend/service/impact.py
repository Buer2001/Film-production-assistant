from collections import deque
from backend.common.errors import BusinessError
from backend.models.notice import Notice
from backend.service.project import get_project, rows, state
from backend.dao.change import get_change
from backend.tools.normalization import normalized, unique
from backend.schemas.impact import ImpactInput


def analyze_impact(s, pid, request):
    project = get_project(s, pid)
    if request.base_revision is not None and project.revision != request.base_revision:
        raise BusinessError(409, '项目版本已变化，请重新分析')
    snapshot = state(s, pid)
    records = {r['id']: r for r in snapshot['records']}
    seeds, resource_names, warnings = set(request.record_ids), set(request.resources), []
    if not seeds.issubset(records):
        raise BusinessError(422, '分析对象不存在于当前项目')
    for rid in seeds:
        record = records[rid]
        if record['kind'] == 'resource':
            resource_names.update(unique([record['data']['title'], *record['data'].get('resources', [])]))
    if request.change_id:
        change = get_change(s, request.change_id)
        if not change or change.project_id != pid:
            raise BusinessError(404, '修改草稿不存在')
        if change.base_revision != project.revision or change.status != 'pending':
            raise BusinessError(409, '草稿已过期或已处理，请重新生成')
        for op in change.operations:
            if op.get('id'):
                seeds.add(op['id'])
            old = records.get(op.get('id'), {}).get('data', {})
            new = op.get('data') or {}
            seeds.update(new.get('scene_ids', []))
            resource_names.update(unique([*old.get('resources', []), *new.get('resources', [])]))
            if op['kind'] == 'resource':
                resource_names.update(unique([old.get('title', ''), new.get('title', '')]))
        if any(not op.get('id') for op in change.operations):
            warnings.append('新增记录尚无正式ID，按其关联场次或资源定位潜在影响')
    paths = {rid: [f'指定记录：{records[rid]["data"]["title"]}'] for rid in sorted(seeds) if rid in records}
    for name in sorted(resource_names):
        matches = [r for r in records.values() if name in unique(r['data'].get('resources', []))
                   or (r['kind'] == 'resource' and normalized(r['data']['title']) == name)]
        if not matches:
            warnings.append(f'未找到资源“{name}”的明确关联，请检查别名及未录入信息')
        for r in matches:
            paths.setdefault(r['id'], [f'资源：{name}', f'记录：{r["data"]["title"]}'])
    # ponytail: 当前按项目内存扫描关联；项目规模增大后再使用索引边表。
    edges = {rid: set() for rid in records}
    for rid, r in records.items():
        for scene in r['data'].get('scene_ids', []):
            if scene in records:
                edges[rid].add(scene)
                edges[scene].add(rid)
    queue = deque(paths)
    while queue:
        rid = queue.popleft()
        for neighbor in sorted(edges[rid]):
            if neighbor not in paths:
                paths[neighbor] = paths[rid] + [f'场次关联：{records[neighbor]["data"]["title"]}']
                queue.append(neighbor)
    affected = [{'id': rid, 'kind': records[rid]['kind'], 'title': records[rid]['data']['title'],
                 'path': path, 'status': records[rid]['data']['status']} for rid, path in paths.items()]
    notices = []
    for notice in rows(s, Notice, pid):
        matched = [r['id'] for r in notice.snapshot.get('schedule', [])
                   if r['id'] in paths or set(r['data'].get('scene_ids', [])) & paths.keys()
                   or set(unique(r['data'].get('resources', []))) & resource_names]
        if matched:
            notices.append({'id': notice.id, 'date': notice.date, 'version': notice.version,
                            'schedule_ids': matched, 'action': '复核该版本通告，确认后决定是否重新发布'})
    return {'base_revision': project.revision, 'records': affected, 'notices': notices,
            'warnings': warnings, 'suggestions': [
                {'record_id': r['id'], 'action': '核实该拍摄安排的资源和时段，必要时提交调整草稿'}
                for r in affected if r['kind'] == 'schedule'],
            'limitations': '基于已录入的场次关联及规范化资源名称；不推断未录入关系，不自动改排期或发布通告'}

