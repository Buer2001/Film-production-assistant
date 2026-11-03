import asyncio
import json
import pytest
from test_planning import client, project, task, settings, mock_model, fake_result


def department_model(monkeypatch, assignments, inspect=None):
    from backend.ai.client import ModelClient
    async def chat(self, messages, tools):
        assert tools[0]['function']['name'] == 'submit_departments'
        if inspect:
            await inspect(json.loads(messages[-1]['content']))
        return {'tool_calls': [{'function': {'name': 'submit_departments', 'arguments': json.dumps({'assignments': assignments})}}]}
    monkeypatch.setattr(ModelClient, 'chat', chat)


def suggestion(ref, department='摄影组', **extra):
    return {'ref': ref, 'department': department, 'collaborating_departments': ['制片组'], 'reason': '任务涉及摄影器材核对', **extra}


def test_formal_department_suggestions_are_only_drafts_and_preserve_manual_data(client, monkeypatch):
    _, root = project(client)
    original = task(client, root, 0, '确认摄影器材单', planned_start='2026-11-03', planned_end='2026-11-05',
                    details={'assignees': ['人工摄影师'], 'rationale': '原安排理由'})
    key = original['tasks'][0]['id']
    original = task(client, root, 1, '场地申请', details={'department': '人工主责组'})
    async def inspect(payload):
        assert [t['ref'] for t in payload['tasks']] == [key]
        assert '人工摄影师' not in json.dumps(payload, ensure_ascii=False)
    department_model(monkeypatch, [suggestion(key)], inspect)
    response = client.post(root + '/departments', json={'revision': 2})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['tasks'] == original['tasks']
    op = data['draft']['result']['operations'][0]
    assert op['action'] == 'update' and op['ref'] == key
    assert set(op['changes']) == {'details'}
    assert set(op['changes']['details']) <= {'department', 'collaborating_departments'}
    confirmed = client.post(root + '/draft/confirm', json={'revision': data['revision'], 'draft_id': data['draft']['id']})
    assert confirmed.status_code == 200, confirmed.text
    after = confirmed.json()['tasks'][0]
    assert after['details']['department'] == '摄影组'
    assert after['details']['assignees'] == ['人工摄影师'] and after['details']['rationale'] == '原安排理由'
    assert after['planned_start'] == '2026-11-03' and after['planned_end'] == '2026-11-05'
    assert confirmed.json()['tasks'][1]['details']['department'] == '人工主责组'


def test_pending_draft_is_supplemented_not_replaced(client, monkeypatch):
    _, root = project(client); settings(client, root)
    result = fake_result()
    result['operations'][0]['task']['details'] = {'department': '人工填写的部门'}
    mock_model(monkeypatch, result)
    before = client.post(root + '/generate', json={'revision': 1}).json()
    department_model(monkeypatch, [suggestion('b')])
    response = client.post(root + '/departments', json={'revision': before['revision']})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['tasks'] == [] and data['draft']['id'] == before['draft']['id']
    assert data['draft']['result']['questions'] == before['draft']['result']['questions']
    assert data['draft']['result']['coverage'] == before['draft']['result']['coverage']
    assert data['draft']['result']['operations'][0] == before['draft']['result']['operations'][0]
    assert data['draft']['result']['operations'][1]['task']['details']['department'] == '摄影组'
    assert data['draft']['result']['operations'][1]['task']['details']['dependencies'] == before['draft']['result']['operations'][1]['task']['details']['dependencies']


@pytest.mark.parametrize('kind', ['unknown', 'duplicate', 'missing', 'extra_fields'])
def test_bad_suggestions_preserve_plan_and_draft(client, monkeypatch, kind):
    _, root = project(client)
    before = task(client, root, 0)
    key = before['tasks'][0]['id']
    values = [suggestion('foreign')] if kind == 'unknown' else [suggestion(key), suggestion(key)] if kind == 'duplicate' else [] if kind == 'missing' else [suggestion(key, planned_end='2030-01-01')]
    department_model(monkeypatch, values)
    response = client.post(root + '/departments', json={'revision': 1})
    assert response.status_code == 422, response.text
    assert client.get(root).json() == before


def test_departments_generation_conflict_preserves_newer_manual_edit(client, monkeypatch):
    _, root = project(client)
    before = task(client, root, 0)
    key = before['tasks'][0]['id']
    async def inspect(payload):
        await asyncio.to_thread(task, client, root, 1, '生成期间新增')
    department_model(monkeypatch, [suggestion(key)], inspect)
    assert client.post(root + '/departments', json={'revision': 1}).status_code == 409
    after = client.get(root).json()
    assert len(after['tasks']) == 2 and after['draft'] is None


def test_no_missing_departments_does_not_call_model(client, monkeypatch):
    _, root = project(client)
    task(client, root, 0, details={'department': '摄影组'})
    async def inspect(payload):
        raise AssertionError('不应调用模型')
    department_model(monkeypatch, [], inspect)
    response = client.post(root + '/departments', json={'revision': 1})
    assert response.status_code == 422


def test_uncertain_department_remains_unassigned_and_is_question(client, monkeypatch):
    _, root = project(client)
    before = task(client, root, 0)
    key = before['tasks'][0]['id']
    department_model(monkeypatch, [suggestion(key, '', reason='需要确认此项目的部门分工')])
    response = client.post(root + '/departments', json={'revision': 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['draft']['result']['operations'] == []
    assert any('部门' in q for q in data['draft']['result']['questions'])
    assert data['tasks'][0]['details']['department'] == ''


def test_department_batches_are_bounded_without_losing_remaining_tasks(client, monkeypatch):
    from sqlalchemy import select
    from backend.models.planning import ProjectPlan, ProjectTask
    pid, root = project(client)
    task(client, root, 0)
    with client.app.state.sessions() as session:
        plan = session.scalar(select(ProjectPlan).where(ProjectPlan.project_id == pid))
        session.add_all([ProjectTask(plan_id=plan.id, title=f'器材任务{i}') for i in range(300)])
        session.commit()
    before = client.get(root).json()
    keys = [t['id'] for t in before['tasks'][:300]]
    async def inspect(payload):
        assert len(payload['tasks']) == 300
    department_model(monkeypatch, [suggestion(key) for key in keys], inspect)
    response = client.post(root + '/departments', json={'revision': 1})
    assert response.status_code == 200, response.text
    meta = response.json()['draft']['department_assignment']
    assert meta['target_count'] == 300 and meta['remaining_count'] == 1
    assert response.json()['tasks'] == before['tasks']
