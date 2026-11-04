# 测试职责：验证项目变更、确认、拒绝、通告和Agent建议的基础业务闭环。
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


# 用途：创建使用临时SQLite数据库的测试应用，并由上下文管理应用生命周期。
# 参数：tmp_path 为pytest临时目录；存在 monkeypatch 参数时用于隔离草稿、日志或模型依赖。
# 产出：FastAPI TestClient；测试结束后退出客户端上下文，不连接正式数据库。
@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as c:
        yield c


# 用途：通过客户端创建隔离的测试项目。
# 参数：c/client 为测试客户端；返回：新项目ID。
def project(c):
    return c.post('/api/projects', json={'name': '学生短片'}).json()['id']


# 用途：通过接口提交一批待确认变更，不自动执行确认。
# 参数：c 为客户端，pid 为项目ID，revision 为基础版本，operations 为操作列表。
# 返回：原始HTTP响应，供测试检查成功或错误状态。
def propose(c, pid, revision, operations):
    return c.post(f'/api/projects/{pid}/changes', json={
        'base_revision': revision, 'reason': '测试调整', 'operations': operations})


# 用例：重复确认同一变更不重复写入，旧基础版本的其他变更被拒绝。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_confirmation_is_idempotent_and_old_changes_conflict(client):
    p = project(client)
    op = {'kind': 'resource', 'data': {'title': '联系礼堂', 'category': '场地'}}
    a = propose(client, p, 0, [op]).json()
    b = propose(client, p, 0, [op]).json()
    assert client.get(f'/api/projects/{p}').json()['records'] == []
    assert client.post(f'/api/projects/{p}/changes/{a["id"]}/confirm').status_code == 200
    assert client.post(f'/api/projects/{p}/changes/{a["id"]}/confirm').status_code == 200
    assert client.post(f'/api/projects/{p}/changes/{b["id"]}/confirm').status_code == 409
    assert len(client.get(f'/api/projects/{p}').json()['records']) == 1


# 用例：批量操作任一项非法则整批不落库，且变更只能在所属项目确认。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_failed_batch_is_atomic_and_project_scoped(client):
    p, other = project(client), project(client)
    draft = propose(client, p, 0, [
        {'kind': 'resource', 'data': {'title': '不应该保存'}},
        {'kind': 'resource', 'id': 'missing', 'data': {'title': '错误'}}])
    assert draft.status_code == 422
    assert client.get(f'/api/projects/{p}').json()['records'] == []
    good = propose(client, p, 0, [{'kind': 'resource', 'data': {'title': '任务'}}]).json()
    assert client.post(f'/api/projects/{other}/changes/{good["id"]}/confirm').status_code == 404


# 用例：仅修改场次标题不会让原通告快照失效或改变快照内容。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_notice_snapshot_remains_valid_after_scene_title_change(client):
    p = project(client)
    a = propose(client, p, 0, [{'kind': 'scene', 'data': {'title': '礼堂演讲'}}]).json()
    client.post(f'/api/projects/{p}/changes/{a["id"]}/confirm')
    notice = client.post(f'/api/projects/{p}/notices', json={
        'date': '2026-02-06', 'base_revision': 1, 'notes': '七点集合'}).json()
    record = client.get(f'/api/projects/{p}').json()['records'][0]
    a = propose(client, p, 1, [{'kind': 'scene', 'id': record['id'], 'data': {'title': '改名'}}]).json()
    client.post(f'/api/projects/{p}/changes/{a["id"]}/confirm')
    state = client.get(f'/api/projects/{p}').json()
    assert state['notices'][0]['stale'] is False
    assert state['notices'][0]['reasons'] == []
    assert state['notices'][0]['snapshot'] == notice['snapshot']
    assert notice['version'] == 1


# 用例：日程检查能识别共享资源冲突和准备状态未知的情况。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_schedule_checks_shared_resources_and_unknown_readiness(client):
    p = project(client)
    ops = [{'kind': 'schedule', 'data': {
        'title': title, 'date': '2026-02-06', 'start': start, 'minutes': 90,
        'resources': ['摄影师'], 'status': '待确认'}}
        for title, start in [('礼堂', '09:00'), ('操场', '10:00')]]
    a = propose(client, p, 0, ops).json()
    client.post(f'/api/projects/{p}/changes/{a["id"]}/confirm')
    checks = client.get(f'/api/projects/{p}/checks').json()
    assert any(x['type'] == 'conflict' for x in checks)
    assert any(x['type'] == 'unknown' for x in checks)


# 用例：未配置模型时Agent返回不可用错误，不伪造处理成功。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_unconfigured_agent_does_not_fake_success(client, monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    monkeypatch.delenv('LLM_MODEL', raising=False)
    p = project(client)
    response = client.post(f'/api/projects/{p}/agent', json={'message': '检查筹备'})
    assert response.status_code == 503


# 用例：非法费用被拒绝，已拒绝草稿不能再次确认且不推进版本。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_rejected_draft_cannot_be_confirmed_and_invalid_expense_rejected(client):
    p = project(client)
    invalid = propose(client, p, 0, [{'kind': 'expense', 'data': {'title': '机票', 'category': '交通', 'amount': '100'}}])
    assert invalid.status_code == 422
    draft = propose(client, p, 0, [{'kind': 'resource', 'data': {'title': '取消任务'}}]).json()
    rejected = client.post(f'/api/projects/{p}/changes/{draft["id"]}/reject')
    assert rejected.status_code == 200
    assert rejected.json() == {'status': 'rejected'}
    assert client.get(f'/api/projects/{p}').json()['changes'][0]['status'] == 'rejected'
    assert client.post(f'/api/projects/{p}/changes/{draft["id"]}/confirm').status_code == 409
    assert client.get(f'/api/projects/{p}').json()['revision'] == 0


# 用例：Agent工具循环只生成待确认建议，未经人工确认不写正式记录。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_agent_tool_loop_creates_only_pending_draft(client):
    import asyncio
    from backend.agent.runner import run
    from backend.agent.schemas import AgentInput

    class FakeModel:
        def __init__(self): self.calls = 0
        async def chat(self, messages, tools):
            self.calls += 1
            assert 'confirm' not in str(tools)
            if self.calls == 1:
                import json
                return {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': 'call_1', 'type': 'function', 'function': {'name': 'propose_change',
                    'arguments': json.dumps({'base_revision': 0, 'reason': '沟通整理', 'operations': [
                        {'kind': 'resource', 'data': {'title': '联系演员', 'source': '测试沟通'}}]})}}]}
            assert messages[-1]['role'] == 'tool'
            return {'role': 'assistant', 'content': '已生成草稿，请确认。'}

    p = project(client)
    with client.app.state.sessions() as s:
        result = asyncio.run(run(s, p, AgentInput(message='联系演员'), FakeModel()))
    state = client.get(f'/api/projects/{p}').json()
    assert result['session_id']
    assert state['records'] == []
    assert state['changes'][0]['status'] == 'pending'
    assert state['changes'][0]['operations'][0]['data']['source'] == '测试沟通'
