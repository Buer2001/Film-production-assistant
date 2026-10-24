"""Offline business evaluations; no paid model requests."""
import asyncio
import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.production.analysis import extract_script


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'analysis.db'}")) as c:
        yield c


class Model:
    def __init__(self, scenes):
        self.scenes = scenes

    async def chat(self, messages, tools):
        return {'tool_calls': [{'function': {'name': 'submit_script',
            'arguments': json.dumps({'scenes': self.scenes}, ensure_ascii=False)}}]}


TEXT = '第1场 教室 日 内\n小雨拿起书包。'
SCENE = {'title': '第1场 教室 日 内', 'evidence': TEXT,
         'characters': ['小雨'], 'location': '教室', 'props': ['书包'],
         'time': '日', 'interior': '内', 'questions': []}


def test_parse_preserves_evidence_and_normalizes_names():
    result = asyncio.run(extract_script(TEXT, Model([{**SCENE, 'characters': [' 小雨 ', '小雨']}])) )
    assert result['scenes'][0]['characters'] == ['小雨']
    assert result['scenes'][0]['line_start'] == 1
    assert result['scenes'][0]['line_end'] == 2
    assert result['scenes'][0]['evidence'] == TEXT


@pytest.mark.parametrize('patch', [
    {'evidence': '不存在的原文'}, {'characters': ['杜撰演员']},
    {'props': ['不存在的手枪']}, {'location': '火星'},
    {'time': '夜'}, {'interior': '外'}, {'title': '不存在的标题'},
])
def test_parse_rejects_unsupported_claims(patch):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(extract_script(TEXT, Model([{**SCENE, **patch}])) )
    assert exc.value.status_code == 422


def create(c):
    return c.post('/api/projects', json={'name': '评估剧组'}).json()['id']


def save(c, p, ops):
    revision = c.get(f'/api/projects/{p}').json()['revision']
    draft = c.post(f'/api/projects/{p}/changes', json={
        'base_revision': revision, 'reason': '评估建档', 'operations': ops})
    assert draft.status_code == 200, draft.text
    assert c.post(f'/api/projects/{p}/changes/{draft.json()["id"]}/confirm').status_code == 200
    return c.get(f'/api/projects/{p}').json()


def test_parse_preview_draft_approval_and_stale_version(client, monkeypatch):
    from backend.common.llm.client import ModelClient
    monkeypatch.setattr(ModelClient, 'chat', Model([SCENE]).chat)
    p = create(client)
    preview = client.post(f'/api/projects/{p}/scripts/parse', json={
        'text': TEXT, 'source_name': '测试剧本', 'base_revision': 0})
    assert preview.status_code == 200, preview.text
    parsed = preview.json()
    assert client.get(f'/api/projects/{p}').json()['records'] == []
    url = f'/api/projects/{p}/scripts/{parsed["id"]}/draft'
    draft = client.post(url, json={}).json()
    assert client.post(url, json={}).json()['id'] == draft['id']
    assert client.get(f'/api/projects/{p}').json()['records'] == []
    assert client.post(f'/api/projects/{p}/changes/{draft["id"]}/confirm').status_code == 200
    state = client.get(f'/api/projects/{p}').json()
    assert state['records'][0]['data']['resources'] == ['小雨', '教室', '书包']
    assert TEXT in state['records'][0]['data']['notes']
    assert client.post(f'/api/projects/{create(client)}/scripts/{parsed["id"]}/draft', json={}).status_code == 404
    stale = client.post(f'/api/projects/{p}/scripts/parse', json={
        'text': TEXT, 'base_revision': 0})
    assert stale.status_code == 409


def test_impact_finds_paths_notices_and_isolates_project(client):
    p, other = create(client), create(client)
    st = save(client, p, [{'kind': 'scene', 'data': {'title': '教室', 'resources': ['小雨']}},
                         {'kind': 'scene', 'data': {'title': '操场', 'resources': ['小明']}}])
    a = next(r['id'] for r in st['records'] if r['data']['title'] == '教室')
    b = next(r['id'] for r in st['records'] if r['data']['title'] == '操场')
    st = save(client, p, [
        {'kind': 'schedule', 'data': {'title': '教室拍摄', 'scene_ids': [a], 'date': '2026-10-19'}},
        {'kind': 'task', 'data': {'title': '准备教室', 'scene_ids': [a]}},
        {'kind': 'schedule', 'data': {'title': '操场拍摄', 'scene_ids': [b], 'date': '2026-10-20'}}])
    for day in ['2026-10-19', '2026-10-20']:
        assert client.post(f'/api/projects/{p}/notices', json={'date': day, 'base_revision': 2}).status_code == 200
    response = client.post(f'/api/projects/{p}/impact', json={'resources': [' 小雨 '], 'base_revision': 2})
    assert response.status_code == 200, response.text
    result = response.json()
    assert {r['title'] for r in result['records']} == {'教室', '教室拍摄', '准备教室'}
    assert len(result['notices']) == 1 and result['notices'][0]['date'] == '2026-10-19'
    assert all(r['path'] for r in result['records'])
    assert client.get(f'/api/projects/{p}').json()['revision'] == 2
    assert client.post(f'/api/projects/{other}/impact', json={'record_ids': [a]}).status_code == 422
    assert client.post(f'/api/projects/{p}/impact', json={'record_ids': [a], 'base_revision': 0}).status_code == 409
    assert client.post(f'/api/projects/{p}/impact', json={}).status_code == 422


def test_impact_of_pending_deletion_uses_existing_links(client):
    p = create(client)
    st = save(client, p, [{'kind': 'scene', 'data': {'title': '教室'}}])
    scene = st['records'][0]['id']
    st = save(client, p, [{'kind': 'schedule', 'data': {'title': '教室拍摄', 'scene_ids': [scene]}}])
    schedule = next(r for r in st['records'] if r['kind'] == 'schedule')
    draft = client.post(f'/api/projects/{p}/changes', json={'base_revision': 2,
        'reason': '取消拍摄', 'operations': [{'kind': 'schedule', 'id': schedule['id'], 'delete': True}]}).json()
    result = client.post(f'/api/projects/{p}/impact', json={'change_id': draft['id']}).json()
    assert schedule['id'] in {r['id'] for r in result['records']}
    assert client.get(f'/api/projects/{p}').json()['changes'][-1]['status'] == 'pending'


def test_new_schedule_draft_finds_shared_resources_and_notice(client):
    p = create(client)
    st = save(client, p, [{'kind': 'schedule', 'data': {'title': '原计划',
        'resources': ['摄影机'], 'date': '2026-10-19'}}])
    client.post(f'/api/projects/{p}/notices', json={'date': '2026-10-19', 'base_revision': 1})
    draft = client.post(f'/api/projects/{p}/changes', json={'base_revision': 1,
        'reason': '新增拍摄', 'operations': [{'kind': 'schedule', 'data': {
            'title': '新增计划', 'resources': ['摄影机']}}]}).json()
    result = client.post(f'/api/projects/{p}/impact', json={'change_id': draft['id']}).json()
    assert st['records'][0]['id'] in {r['id'] for r in result['records']}
    assert result['notices'][0]['date'] == '2026-10-19'


def test_parse_reports_missing_conditions_and_uncovered_text():
    scene = {**SCENE, 'characters': [], 'time': '', 'interior': ''}
    result = asyncio.run(extract_script('说明文字\n' + TEXT + '\n未拆解结尾', Model([scene])))
    assert len(result['warnings']) == 2
    assert {'人物待确认', '昼夜待确认', '内外景待确认'} <= set(result['scenes'][0]['questions'])


def test_stale_parse_cannot_be_imported_and_unknown_resource_warns(client, monkeypatch):
    from backend.common.llm.client import ModelClient
    monkeypatch.setattr(ModelClient, 'chat', Model([SCENE]).chat)
    p = create(client)
    parsed = client.post(f'/api/projects/{p}/scripts/parse', json={'text': TEXT, 'base_revision': 0}).json()
    save(client, p, [{'kind': 'task', 'data': {'title': '其他变化'}}])
    assert client.post(f'/api/projects/{p}/scripts/{parsed["id"]}/draft', json={}).status_code == 409
    result = client.post(f'/api/projects/{p}/impact', json={'resources': ['未知演员']}).json()
    assert not result['records'] and result['warnings']
    assert client.get(f'/api/projects/{p}').json()['changes'][0]['status'] == 'confirmed'


def test_concurrent_parse_conversion_does_not_duplicate_drafts(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from backend.common.llm.client import ModelClient
    monkeypatch.setattr(ModelClient, 'chat', Model([SCENE]).chat)
    p = create(client)
    parsed = client.post(f'/api/projects/{p}/scripts/parse', json={'text': TEXT, 'base_revision': 0}).json()
    url = f'/api/projects/{p}/scripts/{parsed["id"]}/draft'
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: client.post(url, json={}), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()['id'] == responses[1].json()['id']
    assert len(client.get(f'/api/projects/{p}').json()['changes']) == 1


@pytest.mark.parametrize('name,args', [
    ('confirm', {}), ('search_records', {'unexpected': True}),
    ('propose_change', {'base_revision': 99, 'reason': '过期', 'operations': [
        {'kind': 'task', 'data': {'title': '不应写入'}}]}),
])
def test_agent_recovers_from_invalid_tools_without_writing(client, name, args):
    from backend.agent.runtime.runner import run
    from backend.production.project.schemas import AgentInput

    class BadThenRecover:
        calls = 0
        async def chat(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return {'role': 'assistant', 'tool_calls': [{'id': 'bad', 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}]}
            assert 'error' in json.loads(messages[-1]['content'])
            return {'role': 'assistant', 'content': '条件不足，请核实后再修改'}

    p = create(client)
    with client.app.state.sessions() as s:
        result = asyncio.run(run(s, p, AgentInput(message='评估非法调用'), BadThenRecover()))
    assert result['tools'][0]['result'].get('error')
    st = client.get(f'/api/projects/{p}').json()
    assert not st['records'] and not st['changes'] and st['revision'] == 0
