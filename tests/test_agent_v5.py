# 测试职责：用临时数据库验证 V5 的联合草稿、检查分级、统一事务、幂等确认和重启恢复。
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.main import create_app
from test_planning import client  # noqa: F401  复用临时数据库客户端夹具

SCOPE = {'phase': 'shooting', 'start_date': '2026-11-10', 'end_date': '2026-11-20'}


# 建一条拍摄安排，返回安排对象；用于验证通告复核和改期差异。
def create_item(c, pid, scene_id):
    data = {'title': '拍第1场', 'kind': 'shoot', 'scene_id': scene_id,
            'start_at': '2026-11-10T09:00', 'end_at': '2026-11-10T12:00'}
    response = c.post(f'/api/projects/{pid}/shooting/items', json={'revision': 0, 'item': data})
    assert response.status_code == 200, response.text
    return response.json()['items'][0]


# 发布当天通告，作为后续复核对象；返回通告。
def publish_notice(c, pid, day='2026-11-10'):
    view = c.get(f'/api/projects/{pid}/shooting/days/{day}').json()
    details = {'assembly': '南门 07:00', 'makeup': '', 'transport': '', 'meals': '', 'notes': ''}
    response = c.post(f'/api/projects/{pid}/shooting/days/{day}/publish',
                      json={'revision': view['revision'], 'fingerprint': view['fingerprint'],
                            'details': details})
    assert response.status_code == 200, response.text
    return response.json()


# 建立已确认剧本、两个场次和开拍日期；返回项目、接口前缀和场次 ID 列表。
def setup(c):
    from backend.models.script import Script, SceneBreakdown
    pid = c.post('/api/projects', json={'name': 'V5 测试'}).json()['id']
    with c.app.state.sessions() as s:
        script = Script(project_id=pid, version_number=1, title='剧本', content='正文',
                        status='confirmed', confirmed_at='2026-11-04')
        s.add(script)
        s.flush()
        s.add(SceneBreakdown(script_id=script.id, sort_order=1, scene_number='1', location='教室'))
        s.add(SceneBreakdown(script_id=script.id, sort_order=2, scene_number='2', location='操场'))
        s.commit()
    settings = {'shoot_start': '2026-11-10', 'shoot_end': '2026-11-20', 'close_date': '2026-11-30'}
    assert c.put(f'/api/projects/{pid}/planning/settings',
                 json={'revision': 0, 'settings': settings}).status_code == 200
    scenes = [row['id'] for row in c.get(f'/api/projects/{pid}/shooting').json()['scenes']]
    return pid, f'/api/projects/{pid}/agent', scenes


# 构造一份联合候选：一个任务加一条拍摄安排；可只保留任务或替换任务字段。
def candidate(scenes, *, with_shoot=True, origin='manual', task_patch=None):
    operations = [{'op_id': 'op-1', 'entity': 'project_task', 'action': 'add', 'temp_id': 't1',
                   'patch': task_patch or {'title': '确认场地', 'phase': 'preparation'}, 'reason': '准备'}]
    if with_shoot:
        operations.append({'op_id': 'op-2', 'entity': 'shooting_item', 'action': 'add', 'temp_id': 's1',
                           'patch': {'title': '拍第1场', 'kind': 'shoot', 'scene_id': scenes[0],
                                     'start_at': '2026-11-10T09:00', 'end_at': '2026-11-10T12:00'},
                           'reason': '排期'})
    return {'origin': origin, 'operations': operations, 'summary': '联合调整'}


# 发起一次编排；返回运行详情，失败时输出响应正文。
def start(c, root, data, mode='compose'):
    response = c.post(root + '/runs', json={'mode': mode, 'message': '按范围编排',
                                            'scope': SCOPE, 'candidate': data})
    assert response.status_code == 200, response.text
    return response.json()


# 联合草稿同时包含任务和拍摄安排；未排场次必须显式知情后才允许确认。
def test_compose_saves_joint_draft_and_requires_uncovered_confirmation(client):
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes))
    assert run['status'] == 'waiting_review'
    draft = run['draft']
    assert draft['revision'] == 0
    assert {'task', 'shooting'} == set(draft['validation']['counts'])
    assert [row['scene_number'] for row in draft['validation']['uncovered']] == ['2']

    confirm = root + f'/drafts/{draft["id"]}/confirm'
    assert client.post(confirm, json={'revision': 0}).status_code == 422
    response = client.post(confirm, json={'revision': 0, 'accept_uncovered': True})
    assert response.status_code == 200, response.text
    assert len(response.json()['task_ids']) == 1 and len(response.json()['item_ids']) == 1
    assert len(client.get(f'/api/projects/{pid}/planning').json()['tasks']) == 1
    assert len(client.get(f'/api/projects/{pid}/shooting').json()['items']) == 1
    assert client.get(root + f'/runs/{run["id"]}').json()['status'] == 'completed'

    # 同一版草稿再次确认返回原结果，不重复写入。
    repeated = client.post(confirm, json={'revision': 0, 'accept_uncovered': True})
    assert repeated.status_code == 200 and repeated.json()['repeated'] is True
    assert len(client.get(f'/api/projects/{pid}/planning').json()['tasks']) == 1


# 任一业务写入失败时，任务和拍摄安排一起回滚，草稿与运行状态保持原样。
def test_confirm_rolls_back_task_and_shooting_together(client, monkeypatch):
    from backend.dao import shooting as shooting_dao
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes))

    def broken(*args, **kwargs):
        raise RuntimeError('模拟拍摄安排写入失败')

    monkeypatch.setattr(shooting_dao, 'write_item', broken)
    response = client.post(root + f'/drafts/{run["draft"]["id"]}/confirm',
                           json={'revision': 0, 'accept_uncovered': True})
    assert response.status_code == 500
    assert client.get(f'/api/projects/{pid}/planning').json()['tasks'] == []
    assert client.get(f'/api/projects/{pid}/shooting').json()['items'] == []
    stored = client.get(root + f'/runs/{run["id"]}').json()
    assert stored['status'] == 'waiting_review' and stored['draft']['status'] == 'pending'


# 并发确认同一版草稿只产生一次有效执行。
def test_concurrent_confirm_executes_once(client):
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes))
    url = root + f'/drafts/{run["draft"]["id"]}/confirm'
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url, json={'revision': 0, 'accept_uncovered': True}), range(4)))
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    assert sum(1 for r in responses if r.json().get('repeated')) == 3
    assert len(client.get(f'/api/projects/{pid}/planning').json()['tasks']) == 1
    assert len(client.get(f'/api/projects/{pid}/shooting').json()['items']) == 1


# 草稿生成后正式数据变化，确认被拒绝，不会用旧依据执行。
def test_confirm_rejects_changed_sources(client):
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes))
    plan = client.get(f'/api/projects/{pid}/planning').json()
    changed = {**plan['settings'], 'context': '开拍推迟一天'}
    assert client.put(f'/api/projects/{pid}/planning/settings',
                      json={'revision': plan['revision'], 'settings': changed}).status_code == 200
    response = client.post(root + f'/drafts/{run["draft"]["id"]}/confirm',
                           json={'revision': 0, 'accept_uncovered': True})
    assert response.status_code == 409


# 信息不足时暂停，恢复必须使用当前版本号，补充后继续到待审阅。
def test_resume_pauses_and_requires_current_version(client):
    pid, root, scenes = setup(client)
    response = client.post(root + '/runs', json={'mode': 'compose', 'message': '', 'scope': SCOPE})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run['status'] == 'waiting_input' and run['questions']
    stale = client.post(root + f'/runs/{run["id"]}/resume',
                        json={'expected_version': 0, 'decision': 'provide_input',
                              'candidate': candidate(scenes)})
    assert stale.status_code == 409
    resumed = client.post(root + f'/runs/{run["id"]}/resume',
                          json={'expected_version': run['version'], 'decision': 'provide_input',
                                'message': '按范围编排', 'candidate': candidate(scenes)})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()['status'] == 'waiting_review'


# 人工修改草稿递增版本，旧版本的确认请求失效。
def test_edit_draft_bumps_revision_and_invalidates_old_confirm(client):
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes))
    draft_id = run['draft']['id']
    edited = client.put(root + f'/runs/{run["id"]}/draft',
                        json={'revision': 0, 'candidate': candidate(scenes, with_shoot=False)})
    assert edited.status_code == 200, edited.text
    assert edited.json()['revision'] == 1
    assert edited.json()['validation']['counts']['shooting'] == 0
    assert client.post(root + f'/drafts/{draft_id}/confirm',
                       json={'revision': 0, 'accept_uncovered': True}).status_code == 409
    assert client.post(root + f'/drafts/{draft_id}/confirm',
                       json={'revision': 1, 'accept_uncovered': True}).status_code == 200


# 模型来源的候选不能填写人员落实字段，草稿不生成并停下询问。
def test_model_candidate_cannot_write_personnel(client):
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes, origin='model',
                                        task_patch={'title': '确认场地', 'details': {'person_ids': []}}))
    assert run['status'] == 'waiting_input'
    assert run['draft'] is None
    assert any('人员' in question for question in run['questions'])


# 跨项目不能读取或确认草稿；放弃草稿后不能执行。
def test_cross_project_isolation_and_discard(client):
    pid, root, scenes = setup(client)
    other_pid, other_root, _ = setup(client)
    run = start(client, root, candidate(scenes))
    draft_id = run['draft']['id']
    assert client.get(other_root + f'/runs/{run["id"]}').status_code == 404
    assert client.post(other_root + f'/drafts/{draft_id}/confirm',
                       json={'revision': 0, 'accept_uncovered': True}).status_code == 404
    assert client.request('DELETE', root + f'/drafts/{draft_id}', json={'revision': 0}).status_code == 200
    assert client.post(root + f'/drafts/{draft_id}/confirm',
                       json={'revision': 0, 'accept_uncovered': True}).status_code == 409


# 后端重启后运行状态和待审草稿仍在，不依赖进程内存。
def test_run_state_survives_restart(tmp_path):
    url = f'sqlite:///{tmp_path / "restart.db"}'
    with TestClient(create_app(url)) as first:
        pid, root, scenes = setup(first)
        run = start(first, root, candidate(scenes))
    with TestClient(create_app(url)) as second:
        restored = second.get(f'/api/projects/{pid}/agent/runs/{run["id"]}')
        assert restored.status_code == 200
        assert restored.json()['status'] == 'waiting_review'
        assert restored.json()['draft']['revision'] == run['draft']['revision']
        assert restored.json()['version'] == run['version']


# 改期后当天已发布通告需要复核；结果和执行记录都保留提示，不静默改写历史版本。
def test_confirm_reports_notices_to_review(client):
    pid, root, scenes = setup(client)
    item = create_item(client, pid, scenes[0])
    publish_notice(client, pid)
    candidate_data = {'origin': 'manual', 'operations': [
        {'op_id': 'op-1', 'entity': 'shooting_item', 'action': 'update', 'target_id': item['id'],
         'patch': {'start_at': '2026-11-10T10:00'}, 'reason': '改到十点开拍'}]}
    run = start(client, root, candidate_data)
    response = client.post(root + f'/drafts/{run["draft"]["id"]}/confirm',
                           json={'revision': 0, 'accept_uncovered': True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [notice['date'] for notice in result['notices']] == ['2026-11-10']
    assert result['applied'][0]['before']['start_at'] == '2026-11-10T09:00:00'
    assert result['applied'][0]['after']['start_at'] == '2026-11-10T10:00:00'
    stored = client.get(root + f'/runs/{run["id"]}').json()
    assert stored['execution']['notices'][0]['date'] == '2026-11-10'


# 人工改过草稿后，执行记录保留建议稿与最终稿的差异，供后续复盘。
def test_confirm_records_proposal_and_final_difference(client):
    pid, root, scenes = setup(client)
    run = start(client, root, candidate(scenes))
    draft_id = run['draft']['id']
    edited = candidate(scenes)
    edited['operations'].append({'op_id': 'op-3', 'entity': 'project_task', 'action': 'add',
                                 'temp_id': 't2', 'patch': {'title': '结清场地尾款', 'phase': 'closing'},
                                 'reason': '制片补充的收尾任务'})
    assert client.put(root + f'/runs/{run["id"]}/draft',
                      json={'revision': 0, 'candidate': edited}).status_code == 200
    result = client.post(root + f'/drafts/{draft_id}/confirm',
                         json={'revision': 1, 'accept_uncovered': True}).json()
    assert result['diff']['edited'] is True
    assert [item['status'] for item in result['diff']['changes']] == ['added']
    assert result['diff']['proposal_count'] == 2 and result['diff']['final_count'] == 3
    assert len(result['applied']) == 3
    stored = client.get(root + f'/runs/{run["id"]}').json()
    assert stored['draft']['status'] == 'confirmed'
    assert stored['execution']['diff']['final_count'] == 3
