# 测试职责：旧版解析和影响分析的业务契约；模拟模型只提供固定响应，不验证真实模型准确率。
"""Offline business evaluations; no paid model requests."""
import asyncio
import json
import pytest
from backend.common.errors import BusinessError
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.ai.legacy_extractor import extract_script


# 用途：创建使用临时SQLite数据库的测试应用，并由上下文管理应用生命周期。
# 参数：tmp_path 为pytest临时目录；存在 monkeypatch 参数时用于隔离草稿、日志或模型依赖。
# 产出：FastAPI TestClient；测试结束后退出客户端上下文，不连接正式数据库。
@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'analysis.db'}")) as c:
        yield c


# 测试替身：保存预设模型结果，chat返回固定响应，不连接真实模型。
# 构造参数：scenes 为旧版场次列表。
class Model:
    # 保存构造时传入的预设响应，供后续chat使用；不进行校验。
    def __init__(self, scenes):
        self.scenes = scenes

    # 接收messages和tools以兼容真实客户端接口；返回预设响应，不产生网络请求。
    async def chat(self, messages, tools):
        return {'tool_calls': [{'function': {'name': 'submit_script',
            'arguments': json.dumps({'scenes': self.scenes}, ensure_ascii=False)}}]}


TEXT = '第1场 教室 日 内\n小雨拿起书包。'
SCENE = {'title': '第1场 教室 日 内', 'evidence': TEXT,
         'characters': ['小雨'], 'location': '教室', 'props': ['书包'],
         'time': '日', 'interior': '内', 'questions': []}


# 用例：解析后保留原文及行号，并规范化人物名称。
# 返回：无；使用断言或预期异常检查上述行为。
def test_parse_preserves_evidence_and_normalizes_names():
    result = asyncio.run(extract_script(TEXT, Model([{**SCENE, 'characters': [' 小雨 ', '小雨']}])) )
    assert result['scenes'][0]['characters'] == ['小雨']
    assert result['scenes'][0]['line_start'] == 1
    assert result['scenes'][0]['line_end'] == 2
    assert result['scenes'][0]['evidence'] == TEXT


# 用例：模型声称的内容缺乏原文支持时，拒绝接受解析结果。
# 参数：patch 为构造不受原文支持结果的字段修改。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('patch', [
    {'evidence': '不存在的原文'}, {'characters': ['杜撰演员']},
    {'props': ['不存在的手枪']}, {'location': '火星'},
    {'time': '夜'}, {'interior': '外'}, {'title': '不存在的标题'},
])
def test_parse_rejects_unsupported_claims(patch):
    with pytest.raises(BusinessError) as exc:
        asyncio.run(extract_script(TEXT, Model([{**SCENE, **patch}])) )
    assert exc.value.status_code == 422


# 用途：通过HTTP创建测试项目。参数 c 为测试客户端；返回新项目ID。
def create(c):
    return c.post('/api/projects', json={'name': '评估剧组'}).json()['id']


# 用途：按项目当前版本提交并确认测试变更。
# 参数：c 为客户端，p 为项目ID，ops 为变更列表；返回确认后的项目快照。
def save(c, p, ops):
    revision = c.get(f'/api/projects/{p}').json()['revision']
    draft = c.post(f'/api/projects/{p}/changes', json={
        'base_revision': revision, 'reason': '评估建档', 'operations': ops})
    assert draft.status_code == 200, draft.text
    assert c.post(f'/api/projects/{p}/changes/{draft.json()["id"]}/confirm').status_code == 200
    return c.get(f'/api/projects/{p}').json()


# 用例：解析预览和草稿不会直接写正式记录，确认才落库，过期版本禁止转换。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_parse_preview_draft_approval_and_stale_version(client, monkeypatch):
    from backend.ai.client import ModelClient
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


# 用例：影响分析沿关联路径查找记录和通告，并校验项目隔离及版本。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_impact_finds_paths_notices_and_isolates_project(client):
    p, other = create(client), create(client)
    st = save(client, p, [{'kind': 'scene', 'data': {'title': '教室', 'resources': ['小雨']}},
                         {'kind': 'scene', 'data': {'title': '操场', 'resources': ['小明']}}])
    a = next(r['id'] for r in st['records'] if r['data']['title'] == '教室')
    b = next(r['id'] for r in st['records'] if r['data']['title'] == '操场')
    st = save(client, p, [
        {'kind': 'schedule', 'data': {'title': '教室拍摄', 'scene_ids': [a], 'date': '2026-10-19'}},
        {'kind': 'requirement', 'data': {'title': '准备教室', 'scene_ids': [a]}},
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


# 用例：删除建议仍根据现有记录的关联分析影响，且不自动确认变更。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
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


# 用例：新增拍摄建议能找到共享资源冲突及相关日期的通告。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
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


# 用例：缺失人物、昼夜、内外景或未覆盖原文时生成待确认提示。
# 返回：无；使用断言或预期异常检查上述行为。
def test_parse_reports_missing_conditions_and_uncovered_text():
    scene = {**SCENE, 'characters': [], 'time': '', 'interior': ''}
    result = asyncio.run(extract_script('说明文字\n' + TEXT + '\n未拆解结尾', Model([scene])))
    assert len(result['warnings']) == 2
    assert {'人物待确认', '昼夜待确认', '内外景待确认'} <= set(result['scenes'][0]['questions'])


# 用例：过期解析禁止转入变更草稿，未知资源的影响分析给出提示。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_stale_parse_cannot_be_imported_and_unknown_resource_warns(client, monkeypatch):
    from backend.ai.client import ModelClient
    monkeypatch.setattr(ModelClient, 'chat', Model([SCENE]).chat)
    p = create(client)
    parsed = client.post(f'/api/projects/{p}/scripts/parse', json={'text': TEXT, 'base_revision': 0}).json()
    save(client, p, [{'kind': 'requirement', 'data': {'title': '其他变化'}}])
    assert client.post(f'/api/projects/{p}/scripts/{parsed["id"]}/draft', json={}).status_code == 409
    result = client.post(f'/api/projects/{p}/impact', json={'resources': ['未知演员']}).json()
    assert not result['records'] and result['warnings']
    assert client.get(f'/api/projects/{p}').json()['changes'][0]['status'] == 'confirmed'


# 用例：并发转换同一解析结果时复用草稿，避免重复创建。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_concurrent_parse_conversion_does_not_duplicate_drafts(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from backend.ai.client import ModelClient
    monkeypatch.setattr(ModelClient, 'chat', Model([SCENE]).chat)
    p = create(client)
    parsed = client.post(f'/api/projects/{p}/scripts/parse', json={'text': TEXT, 'base_revision': 0}).json()
    url = f'/api/projects/{p}/scripts/{parsed["id"]}/draft'
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: client.post(url, json={}), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()['id'] == responses[1].json()['id']
    assert len(client.get(f'/api/projects/{p}').json()['changes']) == 1


# 用例：Agent收到非法工具调用结果后可继续回答，且不写入业务数据。
# 参数：client 为测试应用客户端；name 为模拟工具名称；args 为模拟工具参数。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('name,args', [
    ('confirm', {}), ('search_records', {'unexpected': True}),
    ('propose_change', {'base_revision': 99, 'reason': '过期', 'operations': [
        {'kind': 'requirement', 'data': {'title': '不应写入'}}]}),
])
def test_agent_recovers_from_invalid_tools_without_writing(client, name, args):
    from backend.agent.runner import run
    from backend.agent.schemas import AgentInput

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
