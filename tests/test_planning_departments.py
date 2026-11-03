from test_planning import client, project, task, settings, mock_model, fake_result


def test_department_assignments_survive_status_patch_and_refresh(client):
    _, root = project(client)
    data = task(client, root, 0, details={'department': '摄影组', 'collaborating_departments': ['灯光组'], 'assignees': ['张三', '李四']})
    key = data['tasks'][0]['id']
    saved = client.patch(root + '/tasks/' + key, json={'revision': 1, 'changes': {'status': 'in_progress'}})
    assert saved.status_code == 200, saved.text
    detail = client.get(root).json()['tasks'][0]['details']
    assert detail['department'] == '摄影组' and detail['collaborating_departments'] == ['灯光组']
    assert detail['assignees'] == ['张三', '李四']
    assert client.post(root + '/tasks', json={'revision': 2, 'task': {'title': '错误人员', 'details': {'assignees': ['']}}}).status_code == 422


def test_old_tasks_have_unassigned_defaults_without_migration(client):
    _, root = project(client)
    detail = task(client, root, 0)['tasks'][0]['details']
    assert detail['department'] == '' and detail['assignees'] == [] and detail['collaborating_departments'] == []


def test_model_suggests_department_but_cannot_invent_assignees(client, monkeypatch):
    _, root = project(client); settings(client, root)
    result = fake_result()
    result['operations'][0]['task']['details'] = {'department': '摄影组', 'assignees': ['模型编造的人']}
    mock_model(monkeypatch, result)
    response = client.post(root + '/generate', json={'revision': 1})
    assert response.status_code == 200, response.text
    detail = response.json()['draft']['result']['operations'][0]['task']['details']
    assert detail['department'] == '摄影组' and detail['assignees'] == []


def test_model_adjustments_preserve_existing_manual_assignees(client, monkeypatch):
    _, root = project(client); settings(client, root)
    data = task(client, root, 1, '确认摄影器材单', details={'department': '摄影组', 'assignees': ['张三']})
    key = data['tasks'][0]['id']
    result = fake_result()
    result['operations'].append({'action': 'update', 'ref': key, 'changes': {'details': {'assignees': ['模型编造的人'], 'department': '模型改派的部门'}}})
    mock_model(monkeypatch, result)
    response = client.post(root + '/generate', json={'revision': data['revision']})
    assert response.status_code == 200, response.text
    update = response.json()['draft']['result']['operations'][-1]
    assert update['changes']['details']['assignees'] == ['张三']
    assert update['changes']['details']['department'] == '摄影组'
