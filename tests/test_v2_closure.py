"""V2收口：只在临时库验证资源、旧写入边界及正式任务统计。"""
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.models.change import Change


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    with TestClient(create_app(f'sqlite:///{tmp_path / "closure.db"}')) as c:
        yield c


def project(c):
    return c.post('/api/projects', json={'name': '收口测试'}).json()['id']


def test_old_task_writes_and_pending_confirmation_are_closed(client):
    pid = project(client)
    operation = {'kind': 'task', 'data': {'title': '旧筹备'}}
    payload = {'base_revision': 0, 'reason': '旧入口', 'operations': [operation]}
    assert client.post(f'/api/projects/{pid}/changes', json=payload).status_code == 422
    # 模拟升级前遗留草稿，不通过已关闭的写入入口建测试数据。
    with client.app.state.sessions() as s:
        row = Change(project_id=pid, base_revision=0, reason='历史草稿', operations=[operation], before=[None])
        s.add(row); s.commit(); cid = row.id
    assert client.post(f'/api/projects/{pid}/changes/{cid}/confirm').status_code == 422
    state = client.get(f'/api/projects/{pid}').json()
    assert state['revision'] == 0 and not state['records']
    assert client.post(f'/api/projects/{pid}/changes/{cid}/reject').status_code == 200


def test_resources_are_shared_with_tasks_and_guarded_at_both_delete_paths(client):
    pid, other = project(client), project(client)
    root = f'/api/projects/{pid}'
    created = client.post(root + '/resources', json={'revision': 0, 'resource': {'title': '教室', 'category': 'location'}})
    assert created.status_code == 200, created.text
    data = created.json(); rid = data['resources'][0]['id']
    assert data['revision'] == 1
    assert client.put(root + '/resources/' + rid, json={'revision': 0, 'resource': {'title': '覆盖'}}).status_code == 409
    assert client.put(f'/api/projects/{other}/resources/{rid}', json={'revision': 0, 'resource': {'title': '越界'}}).status_code == 404
    ref = {'type': 'location', 'name': '教室', 'record_id': rid}
    saved = client.post(root + '/planning/tasks', json={'revision': 0, 'task': {'title': '确认场地', 'planned_end': '2000-01-01', 'details': {'resource_refs': [ref]}}})
    assert saved.status_code == 200, saved.text
    assert client.get(root + '/planning').json()['resource_options'][0]['id'] == rid
    assert client.delete(root + f'/resources/{rid}?revision=1').status_code == 422
    blocked = client.post(root + '/changes', json={'base_revision': 1, 'reason': '绕过资源接口', 'operations': [{'kind': 'resource', 'id': rid, 'delete': True}]})
    assert blocked.status_code == 422
    changed = client.put(root + '/resources/' + rid, json={'revision': 1, 'resource': {'title': '一号教室', 'category': 'location'}})
    assert changed.status_code == 200, changed.text
    assert client.get(root + '/planning').json()['tasks'][0]['details']['resource_refs'][0]['record_id'] == rid
    assert client.get(root).json()['planning_summary'] == {'total': 1, 'unfinished': 1, 'overdue': 1}
    tid = saved.json()['tasks'][0]['id']
    assert client.patch(root + '/planning/tasks/' + tid, json={'revision': 1, 'changes': {'status': 'completed'}}).status_code == 200
    assert client.get(root).json()['planning_summary'] == {'total': 1, 'unfinished': 0, 'overdue': 0}


def test_pending_draft_protects_resource_and_is_not_counted(client):
    from backend.schemas.planning import PlanResult
    pid = project(client); root = f'/api/projects/{pid}'
    created = client.post(root + '/resources', json={'revision': 0, 'resource': {'title': '摄影机'}})
    assert created.status_code == 200, created.text
    rid = created.json()['resources'][0]['id']
    from backend.models.planning import ProjectPlan
    result = PlanResult(operations=[{'action': 'add', 'ref': 'new-1', 'task': {'title': '借器材', 'details': {'resource_refs': [{'name': '摄影机', 'record_id': rid}]}}}], coverage=[]).model_dump(mode='json')
    with client.app.state.sessions() as s:
        s.add(ProjectPlan(project_id=pid, draft={'id': 'existing-draft', 'status': 'pending', 'base_revision': 0, 'source': None, 'result': result}))
        s.commit()
    assert client.delete(root + f'/resources/{rid}?revision=1').status_code == 422
    assert client.get(root).json()['planning_summary']['total'] == 0
    assert client.get(root + '/planning').json()['draft']['id'] == 'existing-draft'


def test_unreferenced_resource_can_be_deleted(client):
    pid = project(client); root = f'/api/projects/{pid}/resources'
    created = client.post(root, json={'revision': 0, 'resource': {'title': '临时资源'}})
    assert created.status_code == 200, created.text
    rid = created.json()['resources'][0]['id']
    deleted = client.delete(root + f'/{rid}?revision=1')
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()['resources'] == []


def test_generation_receives_resources_without_marking_them_ready(client, monkeypatch):
    from backend.ai import planning as ai
    pid = project(client); root = f'/api/projects/{pid}'
    response = client.post(root + '/resources', json={'revision': 0, 'resource': {'title': '待确认场地', 'category': 'location'}})
    rid = response.json()['resources'][0]['id']

    async def generate(snapshot, instruction, model=None, **kwargs):
        assert snapshot['resources'][0]['id'] == rid
        assert snapshot['resources'][0]['data']['status'] == '待确认'
        return {'operations': [{'action': 'add', 'ref': 'location', 'task': {'title': '落实场地', 'details': {'resource_refs': [{'type': 'location', 'name': '待确认场地', 'record_id': rid}]}}}], 'questions': [],
                'coverage': [{'check_id': item['id'], 'status': 'unknown', 'reason': '待核对', 'task_refs': []} for item in ai.checklist()]}

    monkeypatch.setattr(ai, 'generate', generate)
    assert client.put(root + '/planning/settings', json={'revision': 0, 'settings': {'shoot_start': '2030-01-01'}}).status_code == 200
    generated = client.post(root + '/planning/generate', json={'revision': 1})
    assert generated.status_code == 200, generated.text
    draft = generated.json()['draft']
    assert not generated.json()['tasks']
    assert client.delete(root + f'/resources/{rid}?revision=1').status_code == 422
    confirmed = client.post(root + '/planning/draft/confirm', json={'revision': generated.json()['revision'], 'draft_id': draft['id']})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['tasks'][0]['details']['resource_refs'][0]['record_id'] == rid


def test_agent_cannot_bypass_old_task_write_guard(client):
    from backend.agent.tools import execute
    from backend.common.errors import BusinessError
    pid = project(client)
    with client.app.state.sessions() as s:
        with pytest.raises(BusinessError, match='项目日程'):
            execute(s, pid, 'propose_change', {'base_revision': 0, 'reason': '工具调用', 'operations': [{'kind': 'task', 'data': {'title': '旧任务'}}]})
        s.rollback()
    assert client.get(f'/api/projects/{pid}').json()['changes'] == []
