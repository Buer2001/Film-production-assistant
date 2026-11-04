# 测试职责：用临时数据库验证 V4 的版本、项目隔离、并行安排、日志及通告快照。
from copy import deepcopy
from test_planning import client


# 建立正式场次及人员，避免模型参与业务契约回归；返回项目和拍摄接口前缀。
def setup(c):
    from backend.models.script import Script, SceneBreakdown
    pid = c.post('/api/projects', json={'name': '拍摄测试'}).json()['id']
    with c.app.state.sessions() as s:
        script = Script(project_id=pid, version_number=1, title='剧本', content='正文', status='confirmed', confirmed_at='2026-11-04')
        s.add(script)
        s.flush()
        scene = SceneBreakdown(script_id=script.id, sort_order=1, scene_number='1', location='教室')
        s.add(scene)
        s.commit()
    return pid, f'/api/projects/{pid}/shooting'


# 保存安排并检查请求成功；默认时段跨午夜，用于验证完整日期时间而非同日时刻比较。
def item(c, root, revision=0, **changes):
    value = {'title': '布光', 'kind': 'lighting', 'start_at': '2026-11-05T23:00',
             'end_at': '2026-11-06T01:00', **changes}
    response = c.post(root + '/items', json={'revision': revision, 'item': value})
    assert response.status_code == 200, response.text
    return response.json()


# 版本冲突不写入、跨项目引用拒绝，拍摄项必须引用正式场次。
def test_items_version_isolation_and_validation(client):
    pid, root = setup(client)
    other_pid, other = setup(client)
    scene = client.get(root).json()['scenes'][0]['id']
    saved = item(client, root, kind='shoot', scene_id=scene)
    assert saved['revision'] == 1 and len(saved['items']) == 1
    assert client.post(root + '/items', json={'revision': 0, 'item': saved['items'][0]['data']}).status_code == 409
    assert client.post(other + '/items', json={'revision': 0, 'item': saved['items'][0]['data']}).status_code == 422
    bad = {**saved['items'][0]['data'], 'end_at': '2026-11-04T01:00'}
    assert client.post(root + '/items', json={'revision': 1, 'item': bad}).status_code == 422
    assert client.get(root).json()['revision'] == 1


# 时间重叠只针对实际共享人员/资源，同一时刻不同组可以并行；无 V2 计划也保护引用。
def test_parallel_items_and_person_reference_protection(client):
    pid, root = setup(client)
    person = client.post(f'/api/projects/{pid}/people', json={'revision': 0, 'person': {'name': '灯光师'}}).json()['people'][0]['id']
    saved = item(client, root, 1, person_ids=[person])
    saved = item(client, root, 2)
    assert not any(i['code'] == 'person_overlap' for i in saved['issues'])
    saved = item(client, root, 3, person_ids=[person])
    assert any(i['code'] == 'person_overlap' for i in saved['issues'])
    assert client.delete(f'/api/projects/{pid}/people/{person}?revision=4').status_code == 422


# 临时加拍可直接记正式场次；重复保存有版本保护；补拍不覆盖日志或把场次自动判为完成。
def test_logs_unplanned_and_reshoot_reference(client):
    pid, root = setup(client)
    scene = client.get(root).json()['scenes'][0]['id']
    log = {'scene_id': scene, 'date': '2026-11-05', 'status': 'partial', 'remaining': '门口特写', 'reshoot_reason': '下雨'}
    response = client.post(root + '/logs', json={'revision': 0, 'log': log})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['logs'][0]['unplanned'] is True
    lid = saved['logs'][0]['id']
    saved = item(client, root, 1, kind='shoot', scene_id=scene, reshoot_log_id=lid)
    iid = saved['items'][0]['id']
    log['item_id'] = iid
    saved = client.post(root + '/logs', json={'revision': 2, 'log': log}).json()
    updated = client.put(root + '/items/' + iid, json={'revision': 3, 'item': {**saved['items'][0]['data'], 'scene_id': None, 'kind': 'lighting'}})
    assert updated.status_code == 422


# 草稿刷新可恢复但不出现在已发布列表；发布冻结资料，无关日期变化不触发复核。
def test_notice_draft_snapshot_export_and_relevance(client):
    pid, root = setup(client)
    saved = item(client, root)
    day = root + '/days/2026-11-05'
    details = {'assembly': '南门 07:00', 'makeup': '06:30交妆', 'transport': '大巴', 'meals': '12:00午饭', 'notes': '带雨具'}
    response = client.put(day + '/draft', json={'revision': 1, 'details': details})
    assert response.status_code == 200, response.text
    view = client.get(day).json()
    assert view['draft']['details'] == details
    assert client.get(f'/api/projects/{pid}').json()['notices'] == []
    response = client.post(day + '/publish', json={'revision': view['revision'], 'fingerprint': view['fingerprint'], 'details': details})
    assert response.status_code == 200, response.text
    notice = response.json()
    frozen = deepcopy(notice['snapshot'])
    assert '南门' in client.get(f'/api/projects/{pid}/notices/{notice["id"]}/export').text
    saved = item(client, root, notice['project_revision'], start_at='2026-11-07T09:00', end_at='2026-11-07T10:00')
    current = client.get(f'/api/projects/{pid}').json()['notices'][0]
    assert current['stale'] is False and current['snapshot'] == frozen
    iid = saved['items'][0]['id']
    client.put(root + '/items/' + iid, json={'revision': saved['revision'], 'item': {**saved['items'][0]['data'], 'title': '改布光'}})
    current = client.get(f'/api/projects/{pid}').json()['notices'][0]
    assert current['stale'] is True and current['snapshot'] == frozen


# 发布时来源指纹变化会拒绝旧页面，不因准备计划使用独立版本而漏检。
def test_publish_rejects_changed_sources(client):
    pid, root = setup(client)
    scene = client.get(root).json()['scenes'][0]['id']
    item(client, root, kind='shoot', scene_id=scene)
    day = root + '/days/2026-11-05'
    view = client.get(day).json()
    from backend.models.script import SceneBreakdown
    with client.app.state.sessions() as s:
        s.get(SceneBreakdown, scene).summary = '剧本内容已变化'
        s.commit()
    assert client.post(day + '/publish', json={'revision': view['revision'], 'fingerprint': view['fingerprint'], 'details': {}}).status_code == 409


# 没有 V2 计划时，资源引用仍受保护；取消安排不会静默删除历史使用依据。
def test_resource_protection_and_shared_resource_conflict(client):
    pid, root = setup(client)
    resource_root = f'/api/projects/{pid}/resources'
    response = client.post(resource_root, json={'revision': 0, 'resource': {'title': '摄影机'}})
    assert response.status_code == 200, response.text
    rid = response.json()['resources'][0]['id']
    saved = item(client, root, 1, resource_ids=[rid])
    saved = item(client, root, 2, resource_ids=[rid])
    assert any(i['code'] == 'resource_overlap' for i in saved['issues'])
    assert client.delete(resource_root + '/' + rid + '?revision=3').status_code == 422
    assert client.get(root).json()['revision'] == 3


# 日志及补拍来源拒绝跨项目、更换场次；失败事务不能推进正式版本。
def test_log_and_reshoot_cross_project_and_scene_protection(client):
    pid, root = setup(client)
    _, other = setup(client)
    scene = client.get(root).json()['scenes'][0]['id']
    other_scene = client.get(other).json()['scenes'][0]['id']
    response = client.post(root + '/logs', json={'revision': 0, 'log': {'scene_id': scene, 'date': '2026-11-05'}})
    lid = response.json()['logs'][0]['id']
    invalid = {'title': '错误补拍', 'kind': 'shoot', 'scene_id': other_scene, 'reshoot_log_id': lid,
               'start_at': '2026-11-05T09:00', 'end_at': '2026-11-05T10:00'}
    assert client.post(other + '/items', json={'revision': 0, 'item': invalid}).status_code == 422
    assert client.post(other + '/logs', json={'revision': 0, 'log': {'scene_id': scene, 'date': '2026-11-05'}}).status_code == 422
    assert client.get(other).json()['revision'] == 0
    saved = item(client, root, 1, kind='shoot', scene_id=scene, reshoot_log_id=lid)
    assert client.put(root + '/logs/' + lid, json={'revision': 2, 'log': {'scene_id': other_scene, 'date': '2026-11-05'}}).status_code == 422
    assert client.get(root).json()['revision'] == saved['revision']


# 通告草稿重复保存只维护一个草稿；发布重复请求被版本检查拒绝，不产生重复版本。
def test_draft_updates_and_publish_retry(client):
    pid, root = setup(client)
    item(client, root)
    day = root + '/days/2026-11-05'
    client.put(day + '/draft', json={'revision': 1, 'details': {'notes': '第一版'}})
    second = client.put(day + '/draft', json={'revision': 2, 'details': {'notes': '第二版'}}).json()
    assert second['draft']['details']['notes'] == '第二版'
    assert client.put(day + '/draft', json={'revision': 2, 'details': {'notes': '旧页面'}}).status_code == 409
    assert client.get(day).json()['draft'] == second['draft']
    body = {'revision': 3, 'fingerprint': second['fingerprint'], 'details': second['draft']['details']}
    assert client.post(day + '/publish', json=body).status_code == 200
    assert client.post(day + '/publish', json=body).status_code == 409
    view = client.get(day).json()
    assert len(view['notices']) == 1 and view['notices'][0]['version'] == 1
    assert view['draft']['details']['notes'] == '第二版'
    from backend.models.notice import Notice
    from sqlalchemy import select
    with client.app.state.sessions() as s:
        drafts = s.scalars(select(Notice).where(Notice.project_id == pid, Notice.version == 0)).all()
        assert len(drafts) == 1
        draft_id = drafts[0].id
    assert client.get(f'/api/projects/{pid}/notices/{draft_id}/export').status_code == 404


# 准备日程使用自己的版本：修改明确关联任务后，旧预览指纹必须失效，即使项目 revision 未变。
def test_related_preparation_change_rejects_old_preview(client):
    pid, root = setup(client)
    scene = client.get(root).json()['scenes'][0]
    planning = f'/api/projects/{pid}/planning'
    response = client.post(planning + '/tasks', json={'revision': 0, 'task': {'title': '落实教室',
        'details': {'scene_refs': [{'script_id': scene['script_id'], 'scene_id': scene['id']}]}}})
    assert response.status_code == 200, response.text
    task = response.json()['tasks'][0]
    current_revision = client.get(root).json()['revision']
    item(client, root, current_revision, kind='shoot', scene_id=scene['id'])
    day = root + '/days/2026-11-05'
    view = client.get(day).json()
    assert any(i['code'] == 'preparation_unfinished' for i in view['issues'])
    changed = client.patch(planning + '/tasks/' + task['id'], json={'revision': response.json()['revision'], 'changes': {'status': 'completed'}})
    assert changed.status_code == 200, changed.text
    assert client.get(root).json()['revision'] == view['revision']
    assert client.post(day + '/publish', json={'revision': view['revision'], 'fingerprint': view['fingerprint'], 'details': {}}).status_code == 409


# 新旧通告同日共享递增版本；日志更新和未关联场次修改不应误报通告变化。
def test_legacy_coexistence_and_unrelated_script_edit(client):
    pid, root = setup(client)
    legacy = client.post(f'/api/projects/{pid}/notices', json={'base_revision': 0, 'date': '2026-11-05', 'notes': '旧通告'})
    assert legacy.status_code == 200
    scene = client.get(root).json()['scenes'][0]
    item(client, root, kind='shoot', scene_id=scene['id'])
    day = root + '/days/2026-11-05'
    view = client.get(day).json()
    response = client.post(day + '/publish', json={'revision': view['revision'], 'fingerprint': view['fingerprint'], 'details': {}})
    assert response.status_code == 200 and response.json()['version'] == 2
    from backend.models.script import Script, SceneBreakdown
    with client.app.state.sessions() as s:
        s.add(SceneBreakdown(script_id=scene['script_id'], sort_order=2, scene_number='2', summary='其他场次'))
        s.get(Script, scene['script_id']).revision += 1
        s.commit()
    logs = client.post(root + '/logs', json={'revision': response.json()['project_revision'], 'log': {'scene_id': scene['id'], 'date': '2026-11-05'}})
    assert logs.status_code == 200
    notices = client.get(f'/api/projects/{pid}').json()['notices']
    assert len(notices) == 2 and not any(n['stale'] for n in notices)
    assert '旧通告' in client.get(f'/api/projects/{pid}/notices/{legacy.json()["id"]}/export').text


# 准备任务实施人员不必参加拍摄：通告检查不能因裁剪参与名单而误报人员/资源不存在。
def test_notice_checks_keep_preparation_support_facts(client):
    pid, root = setup(client)
    scene = client.get(root).json()['scenes'][0]
    person = client.post(f'/api/projects/{pid}/people', json={'revision': 0, 'person': {'name': '执行制片'}}).json()['people'][0]['id']
    resource = client.post(f'/api/projects/{pid}/resources', json={'revision': 1, 'resource': {'title': '准备物品'}}).json()['resources'][0]['id']
    response = client.post(f'/api/projects/{pid}/planning/tasks', json={'revision': 0, 'task': {'title': '落实物品', 'status': 'completed',
        'details': {'scene_refs': [{'script_id': scene['script_id'], 'scene_id': scene['id']}], 'person_ids': [person],
                    'resource_refs': [{'name': '准备物品', 'record_id': resource}]}}})
    assert response.status_code == 200, response.text
    item(client, root, 2, kind='shoot', scene_id=scene['id'])
    issues = client.get(root + '/days/2026-11-05').json()['issues']
    assert not {'person_missing', 'resource_missing', 'result_missing'} & {i['code'] for i in issues}
    assert any(i['code'] == 'resource_not_assigned' for i in issues)


# 原日志不能改成自己的补拍结果；有实际日志的安排也不能事后改造成补拍来源环。
def test_reshoot_preserves_original_log_causality(client):
    pid, root = setup(client)
    scene = client.get(root).json()['scenes'][0]['id']
    item(client, root, kind='shoot', scene_id=scene)
    iid = client.get(root).json()['items'][0]['id']
    value = {'scene_id': scene, 'item_id': iid, 'date': '2026-11-05', 'status': 'partial'}
    saved = client.post(root + '/logs', json={'revision': 1, 'log': value}).json()
    lid = saved['logs'][0]['id']
    saved = item(client, root, 2, kind='shoot', scene_id=scene, reshoot_log_id=lid)
    reshoot_id = next(i['id'] for i in saved['items'] if i['data'].get('reshoot_log_id'))
    assert client.put(root + '/logs/' + lid, json={'revision': 3, 'log': {**value, 'item_id': reshoot_id}}).status_code == 422
    original = next(i for i in saved['items'] if i['id'] == iid)
    assert client.put(root + '/items/' + iid, json={'revision': 3, 'item': {**original['data'], 'reshoot_log_id': lid}}).status_code == 422
