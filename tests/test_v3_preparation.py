# 测试职责：验证人员和资源筹备事实仅由人工维护，检查结果不擅自改变日程数据。
"""筹备检查关注真实落实资料，不把任务完成或旧金额当成确认事实。"""
from test_planning import client, project, task, settings, mock_model, fake_result


# 用例：旧任务读取筹备默认字段，查看筹备信息不推进项目或日程版本。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_old_tasks_read_defaults_and_preparation_does_not_change_versions(client):
    pid, root = project(client)
    saved = task(client, root, 0)
    details = saved['tasks'][0]['details']
    assert details['person_ids'] == [] and details['usage_period'] is None
    response = client.get(f'/api/projects/{pid}/preparation')
    assert response.status_code == 200, response.text
    assert response.json() == {'issues': [], 'checked_tasks': 1}
    assert client.get(root).json()['revision'] == saved['revision']


# 用例：任务完成不等于资源需求已落实，已取消任务不参与缺口检查。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_unresolved_completed_requirement_remains_a_gap_and_cancelled_is_ignored(client):
    pid, root = project(client)
    data = task(client, root, 0, '落实教室', status='completed', details={
        'requires_people': True, 'resource_refs': [{'type': 'location', 'name': '教室'}]})
    tid = data['tasks'][0]['id']
    issues = client.get(f'/api/projects/{pid}/preparation').json()['issues']
    assert {'resource_unresolved', 'people_unresolved', 'result_missing'} <= {i['code'] for i in issues}
    assert all(i['task_id'] == tid for i in issues)
    client.patch(root + '/tasks/' + tid, json={'revision': data['revision'], 'changes': {'status': 'cancelled'}})
    assert client.get(f'/api/projects/{pid}/preparation').json() == {'issues': [], 'checked_tasks': 0}


# 用例：可用时段合并和边界检查正确处理重叠、未知及不完整信息。
# 返回：无；使用断言或预期异常检查上述行为。
def test_pure_checks_cover_time_union_boundaries_and_unknown_information():
    from backend.tools.preparation import check_preparation
    use = {'start_date': '2030-01-03', 'end_date': '2030-01-03', 'start_time': '09:00:00', 'end_time': '17:00:00'}
    task_data = {'id': 't', 'title': '落实教室', 'status': 'completed', 'details': {
        'resource_refs': [{'name': '教室', 'record_id': 'r'}], 'usage_period': use}}
    available = [dict(use, state='available', end_time='12:00:00'), dict(use, state='available', start_time='12:00:00')]
    resource = {'id': 'r', 'data': {'title': '302', 'amount': '0', 'preparation': {'status': 'confirmed', 'availability': available}}}
    assert check_preparation([task_data], [resource], []) == []
    resource['data']['preparation']['availability'].append(dict(use, state='unavailable', start_time='16:00:00'))
    assert 'time_unavailable' in {i['code'] for i in check_preparation([task_data], [resource], [])}
    resource['data'].pop('preparation')
    codes = {i['code'] for i in check_preparation([task_data], [resource], [])}
    assert {'resource_pending', 'availability_unknown'} <= codes
    task_data['details'].pop('usage_period')
    assert 'usage_unknown' in {i['code'] for i in check_preparation([task_data], [resource], [])}


# 用例：局部修改保留人工人员字段，并拒绝跨项目人员引用。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_manual_person_fields_survive_patch_and_cross_project_reference_rejected(client):
    pid, root = project(client)
    person = client.post(f'/api/projects/{pid}/people', json={'revision': 0, 'person': {'name': '小王'}})
    assert person.status_code == 200, person.text
    person_id = person.json()['people'][0]['id']
    detail = {'person_ids': [person_id], 'result_notes': '张老师已口头同意', 'usage_period': {
        'start_date': '2030-01-03', 'end_date': '2030-01-03'}}
    saved = task(client, root, 0, details=detail)
    tid = saved['tasks'][0]['id']
    updated = client.patch(root + '/tasks/' + tid, json={'revision': 1, 'changes': {'status': 'in_progress'}})
    assert updated.status_code == 200, updated.text
    assert updated.json()['tasks'][0]['details']['person_ids'] == [person_id]
    assert updated.json()['tasks'][0]['details']['result_notes'] == detail['result_notes']
    _, other_root = project(client)
    rejected = client.post(other_root + '/tasks', json={'revision': 0, 'task': {'title': '越界', 'details': detail}})
    assert rejected.status_code == 422
    assert client.get(other_root).json()['revision'] == 0


# 用例：模型不得编造或覆盖人工筹备事实。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_model_cannot_invent_or_overwrite_preparation_facts(client, monkeypatch):
    _, root = project(client)
    settings(client, root)
    saved = task(client, root, 1, details={'result_notes': '制片人工结果', 'requires_people': True,
        'usage_period': {'start_date': '2030-01-03', 'end_date': '2030-01-03'}})
    tid = saved['tasks'][0]['id']
    result = fake_result()
    result['operations'][0]['task']['details'] = {'person_ids': ['invented'], 'result_notes': '虚构已确认',
        'usage_period': {'start_date': '2031-01-01', 'end_date': '2031-01-01'}}
    result['operations'].append({'action': 'update', 'ref': tid, 'changes': {'details': {
        'result_notes': '', 'person_ids': ['invented'], 'requires_people': False,
        'usage_period': None}}})
    mock_model(monkeypatch, result)
    response = client.post(root + '/generate', json={'revision': saved['revision']})
    assert response.status_code == 200, response.text
    ops = response.json()['draft']['result']['operations']
    assert ops[0]['task']['details']['person_ids'] == []
    assert ops[0]['task']['details']['result_notes'] == ''
    assert ops[0]['task']['details']['usage_period'] is None
    preserved = ops[-1]['changes']['details']
    assert preserved['result_notes'] == '制片人工结果'
    assert preserved['person_ids'] == [] and preserved['requires_people'] is True
    assert preserved['usage_period']['start_date'] == '2030-01-03'


# 用例：确认资源后更新检查结果，但不改任务内容或日程版本。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_resource_confirmation_changes_checks_without_changing_task_or_schedule_revision(client):
    pid, root = project(client)
    base = f'/api/projects/{pid}'
    usage = {'start_date': '2030-01-03', 'end_date': '2030-01-03', 'start_time': '09:00', 'end_time': '17:00'}
    resource = {'title': '教学楼302', 'preparation': {'status': 'confirmed', 'availability': [dict(usage, state='available')]}}
    response = client.post(base + '/resources', json={'revision': 0, 'resource': resource})
    assert response.status_code == 200, response.text
    rid = response.json()['resources'][0]['id']
    saved = task(client, root, 0, '落实教室', details={
        'usage_period': usage, 'resource_refs': [{'name': '教学楼302', 'record_id': rid}]})
    assert client.get(base + '/preparation').json()['issues'] == []
    resource['preparation']['status'] = 'unavailable'
    response = client.put(base + '/resources/' + rid, json={'revision': 1, 'resource': resource})
    assert response.status_code == 200, response.text
    issue = client.get(base + '/preparation').json()['issues'][0]
    assert issue['code'] == 'resource_unavailable' and issue['resource_id'] == rid
    unchanged = client.get(root).json()
    assert unchanged['revision'] == saved['revision'] and unchanged['tasks'] == saved['tasks']
    resource['preparation']['status'] = 'confirmed'
    resource['preparation']['availability'] = [dict(usage, state='available', end_time='12:00')]
    assert client.put(base + '/resources/' + rid, json={'revision': 2, 'resource': resource}).status_code == 200
    assert client.get(base + '/preparation').json()['issues'][0]['code'] == 'time_outside_available'


# 用例：旧Agent不能写V3筹备字段，旧更新路径仍保留人工事实。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_existing_agent_cannot_write_v3_fields_and_legacy_update_keeps_manual_facts(client):
    from pydantic import ValidationError
    import pytest
    from backend.agent.tools import execute
    pid, _ = project(client)
    base = f'/api/projects/{pid}'
    saved = client.post(base + '/resources', json={'revision': 0, 'resource': {'title': '摄影机',
        'preparation': {'status': 'confirmed', 'cost_status': 'free'}}}).json()['resources'][0]
    request = {'base_revision': 1, 'reason': '修改名称', 'operations': [
        {'kind': 'resource', 'id': saved['id'], 'data': {'title': '主摄影机'}}]}
    with client.app.state.sessions() as session:
        draft = execute(session, pid, 'propose_change', request)
    assert client.post(base + '/changes/' + draft['id'] + '/confirm').status_code == 200
    resource = client.get(base + '/resources').json()['resources'][0]['data']
    assert resource['title'] == '主摄影机' and resource['preparation']['status'] == 'confirmed'
    request['base_revision'] = 2
    request['operations'][0]['data']['preparation'] = {'status': 'unavailable'}
    with client.app.state.sessions() as session:
        with pytest.raises(ValidationError):
            execute(session, pid, 'propose_change', request)
