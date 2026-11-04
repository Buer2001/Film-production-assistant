# 文件职责：管理拍摄计划和实际日志，汇集正式来源；版本、业务写入和事件处于同一事务。
from backend.common.errors import BusinessError
from backend.dao import shooting as dao, project as projects
from backend.dao.event import add_event
from backend.service.project import get_project
from backend.service.person import person_dict
from backend.tools.shooting import check_shooting, day_items, relevant_tasks, fingerprint


# 序列化 ORM 对象；unplanned 从实际引用推导，禁止客户端伪造临时加拍标识。
def item_dict(row):
    return {'id': row.id, 'data': row.data}


def log_dict(row):
    return {'id': row.id, 'data': row.data, 'unplanned': row.item_id is None}


# 收集本项目正式数据；发布和写事务使用 locked 当前读，普通 GET 不领取版本。
def facts(s, pid, *, locked=False):
    plan, tasks = dao.preparation(s, pid, locked=locked)
    people, resources = dao.support(s, pid, locked=locked)
    scenes = [{'id': scene.id, 'script_id': script.id, 'script_version': script.version_number,
               'script_revision': script.revision, 'scene_number': scene.scene_number,
               'location': scene.location, 'summary': scene.summary, 'atmosphere': scene.atmosphere,
               'interior_exterior': scene.interior_exterior, 'notes': scene.notes, 'details': scene.details}
              for scene, script in dao.scenes(s, pid, locked=locked)]
    return {'items': [item_dict(r) for r in dao.items(s, pid, locked=locked)],
            'logs': [log_dict(r) for r in dao.logs(s, pid, locked=locked)], 'scenes': scenes,
            'people': [person_dict(p) for p in people],
            'resources': [{'id': r.id, 'data': r.data} for r in resources],
            'tasks': [{'id': t.id, 'title': t.title, 'description': t.description, 'status': t.status, 'phase': t.phase,
                       'planned_start': t.planned_start.isoformat() if t.planned_start else None,
                       'planned_end': t.planned_end.isoformat() if t.planned_end else None,
                       'completion_criteria': t.completion_criteria, 'details': t.details} for t in tasks]}


# 返回完整拍摄工作区和纯规则提醒；查询不自动创建计划、任务或日志。
def read(s, pid):
    project = get_project(s, pid)
    data = facts(s, pid)
    return {'revision': project.revision, **data,
            'issues': check_shooting(data['items'], data['people'], data['resources'], data['tasks'])}


# 先领取项目版本，再读取关联来源；失败由请求级 Session 回滚，不残留版本或事件。
def claim(s, pid, revision):
    get_project(s, pid)
    if projects.claim_revision(s, pid, revision, increment=True) != 1:
        raise BusinessError(409, '数据已更新，请刷新后重试；未保存输入仍保留')


# 正式场次身份不依赖可变化的场号，历史已确认版本仍可保留引用以便追溯。
def require_scene(data, scene_id):
    if scene_id not in {r['id'] for r in data['scenes']}:
        raise BusinessError(422, '场次不存在、未正式确认或不属于本项目')


# 新建或完整替换安排；人工保存无需模型草稿，取消保留记录及历史引用。
def save_item(s, pid, request, iid=None):
    claim(s, pid, request.revision)
    current = dao.get_item(s, pid, iid) if iid else None
    if iid and current is None:
        raise BusinessError(404, '拍摄安排不存在')
    data = request.item.model_dump(mode='json')
    source = facts(s, pid, locked=True)
    if data['scene_id']:
        require_scene(source, data['scene_id'])
    for field, options in [('person_ids', source['people']), ('resource_ids', source['resources'])]:
        if set(data[field]) - {r['id'] for r in options}:
            raise BusinessError(422, '人员或资源不存在或不属于本项目')
    if data['reshoot_log_id']:
        log = dao.get_log(s, pid, data['reshoot_log_id'])
        if not log or data['kind'] != 'shoot' or log.scene_id != data['scene_id']:
            raise BusinessError(422, '补拍必须关联本项目同一场次的日志')
    # 已有实际结果不能改成另一场或非拍摄项，否则日志将失去正确的计划依据。
    if current and any(r['data']['item_id'] == iid for r in source['logs']):
        if data['scene_id'] != current.scene_id or data['kind'] != 'shoot':
            raise BusinessError(422, '已有日志的安排不能更换场次或改为非拍摄项')
        if data['reshoot_log_id'] != current.data.get('reshoot_log_id'):
            raise BusinessError(422, '已有日志的安排不能更换补拍来源，请新建补拍安排')
    before = current.data if current else None
    row = dao.write_item(s, pid, data, current)
    add_event(s, pid, 'shooting_item', {'id': row.id, 'before': before, 'after': data, 'revision': request.revision + 1})
    s.commit()
    s.expire_all()
    return read(s, pid)


# 保存实际日志；临时加拍可不关联安排，但有引用时必须对应本项目相同正式场次。
def save_log(s, pid, request, lid=None):
    claim(s, pid, request.revision)
    current = dao.get_log(s, pid, lid) if lid else None
    if lid and not current:
        raise BusinessError(404, '拍摄日志不存在')
    data = request.log.model_dump(mode='json')
    source = facts(s, pid, locked=True)
    require_scene(source, data['scene_id'])
    if data['item_id']:
        item = dao.get_item(s, pid, data['item_id'])
        if not item or item.scene_id != data['scene_id'] or item.data['kind'] != 'shoot':
            raise BusinessError(422, '日志安排不存在或与当前场次不符')
    if current and any(r['data'].get('reshoot_log_id') == lid for r in source['items']):
        # 原日志被后续补拍引用后，不能再挂到自己的补拍安排，避免追溯链形成因果环。
        if current.scene_id != data['scene_id'] or current.item_id != data['item_id']:
            raise BusinessError(422, '已有补拍引用的日志不能更换场次或对应安排')
    before = current.data if current else None
    row = dao.write_log(s, pid, data, current)
    add_event(s, pid, 'shooting_log', {'id': row.id, 'before': before, 'after': data, 'revision': request.revision + 1})
    s.commit()
    s.expire_all()
    return read(s, pid)


# 挑选当天实际引用的来源，供发布校验和通告复核复用，不把所有项目数据塞入快照。
def day_source(s, pid, day, *, locked=False):
    project = get_project(s, pid)
    data = facts(s, pid, locked=locked)
    slots = day_items(data['items'], day)
    scene_ids = {r['data']['scene_id'] for r in slots}
    person_ids = {oid for r in slots for oid in r['data']['person_ids']}
    resource_ids = {oid for r in slots for oid in r['data']['resource_ids']}
    tasks = relevant_tasks(data['tasks'], scene_ids, resource_ids)
    # 准备任务实施人员不等于拍摄参与人员；检查仍需这些真实资料，不能因快照裁剪误报缺失。
    person_ids.update(oid for t in tasks for oid in t['details'].get('person_ids', []))
    resource_ids.update(r['record_id'] for t in tasks for r in t['details'].get('resource_refs', []) if r.get('record_id'))
    return {'project': project.name, 'date': day, 'items': slots,
            # 已复制场次内容及版本身份；不使用整版 revision 判断，避免其他场次编辑误报复核。
            'scenes': [{k: v for k, v in r.items() if k != 'script_revision'} for r in data['scenes'] if r['id'] in scene_ids],
            'people': [r for r in data['people'] if r['id'] in person_ids],
            'resources': [r for r in data['resources'] if r['id'] in resource_ids],
            'tasks': tasks}


# V4 快照只与其当天来源比较；不会因日志新增或其他天的安排变化而标记过期。
def notice_status(s, pid, notice):
    changed = fingerprint(day_source(s, pid, notice.date)) != notice.snapshot['fingerprint']
    return {'stale': changed, 'reasons': ['当天安排、关联场次、人员资源或准备资料已变化，请复核'] if changed else []}
