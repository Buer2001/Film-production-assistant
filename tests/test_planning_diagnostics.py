# 测试职责：验证计划生成和任务校验的安全错误说明、日志追踪及失败状态保护。
import asyncio
import json
import logging
import pytest
from backend.ai.planning import generate
from backend.common.errors import BusinessError
from backend.common.logging.config import JsonFormatter


# 测试替身：保存预设模型结果，chat返回固定响应，不连接真实模型。
# 构造参数：response 为待校验的完整响应对象。
class Reply:
    # 保存构造时传入的预设响应，供后续chat使用；不进行校验。
    def __init__(self, response):
        self.response = response

    # 接收messages和tools以兼容真实客户端接口；返回预设响应，不产生网络请求。
    async def chat(self, messages, tools):
        return self.response


# 用途：构造单个工具调用响应，不预先解析或校验参数。
# 参数：arguments 为待校验工具参数，name 为工具名；返回包含 tool_calls 的字典。
def call(arguments, name='submit_plan'):
    return {'tool_calls': [{'function': {'name': name, 'arguments': arguments}}]}


# 用例：计划生成失败说明具体原因及字段，并屏蔽敏感内容。
# 参数：response 为待验证的模拟模型响应；reason 为预期错误原因标识；field 为预期字段路径；caplog 为捕获日志的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('response, reason, field', [
    (None, 'response_invalid', ''),
    ({'content': 'SECRET_RESPONSE'}, 'tool_missing', ''),
    ({'tool_calls': {'SECRET_KEY': 1}}, 'response_invalid', ''),
    ({'tool_calls': [{}, {}]}, 'tool_count', ''),
    ({'tool_calls': [None]}, 'response_invalid', ''),
    (call('{}', name='SECRET_TOOL'), 'tool_name', ''),
    (call(None), 'arguments_invalid', ''),
    (call('{SECRET_JSON'), 'json_invalid', 'response'),
    (call(json.dumps({'operations': [{'action': 'add', 'ref': 'a', 'task': {'title': 'SECRET_TITLE', 'phase': 'SECRET_PHASE'}}], 'coverage': []})), 'schema_invalid', 'operations[0].task.phase'),
    (call(json.dumps({'coverage': [], 'SECRET_KEY': 'SECRET_VALUE'})), 'schema_invalid', 'field'),
    (call(json.dumps({'operations': [{'action': 'add', 'ref': 'a'}], 'coverage': []})), 'schema_invalid', 'operations[0]'),
])
def test_specific_safe_planning_diagnostics(response, reason, field, caplog):
    with caplog.at_level(logging.INFO, logger='film'):
        with pytest.raises(BusinessError) as error:
            asyncio.run(generate({}, '', Reply(response)))
    assert error.value.status_code == 422
    assert reason in error.value.detail and field in error.value.detail
    rejected = [r for r in caplog.records if r.getMessage() == 'planning.rejected']
    assert len(rejected) == 1
    value = json.loads(JsonFormatter().format(rejected[0]))
    assert value['error_type'] == reason
    assert value['operation'] == 'planning.generate' and value['duration_ms'] >= 0
    assert value['input_chars'] > 0 and value['error_count'] >= 1
    assert 'SECRET' not in error.value.detail + json.dumps(value)
    if reason == 'schema_invalid':
        assert value['validation_errors'][0]['field'] == field
        assert value['validation_errors'][0]['type']
        assert value['validation_errors'][0]['reason']


# 用例：诊断展示数量有限，同时保留全部错误数量统计。
# 参数：caplog 为捕获日志的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_diagnostics_bounded_and_count_all_errors(caplog):
    payload = {'operations': [{'action': 'add', 'ref': f't{i}', 'task': {'title': 'SECRET_TITLE', 'phase': 'SECRET_PHASE', 'category': 'SECRET_CATEGORY'}} for i in range(10)], 'coverage': []}
    with caplog.at_level(logging.INFO, logger='film'):
        with pytest.raises(BusinessError):
            asyncio.run(generate({}, '', Reply(call(json.dumps(payload)))))
    record = next(r for r in caplog.records if r.getMessage() == 'planning.rejected')
    logged = json.loads(JsonFormatter().format(record))
    assert logged['error_count'] == 20
    assert len(logged['validation_errors']) == 6
    assert logged['error_types']['literal_error'] == 20
    assert 'SECRET' not in json.dumps(logged)


# 用例：校验失败日志关联HTTP请求，保留项目原状态且不泄露字段值。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_validation_log_has_http_request_id_and_preserves_state(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.ai.client import ModelClient
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    async def invalid(*args, **kwargs):
        return call(json.dumps({'operations': [{'action': 'add', 'ref': 'a', 'task': {'title': 'SECRET_TASK', 'phase': 'SECRET_PHASE'}}], 'coverage': []}))
    monkeypatch.setattr(ModelClient, 'chat', invalid)
    with TestClient(create_app(f'sqlite:///{tmp_path / "diagnostics.db"}')) as client:
        pid = client.post('/api/projects', json={'name': '日志测试'}).json()['id']
        root = f'/api/projects/{pid}/planning'
        before = client.put(root + '/settings', json={'revision': 0, 'settings': {'shoot_start': '2026-11-05'}}).json()
        response = client.post(root + '/generate', json={'revision': 1})
        assert response.status_code == 422
        assert client.get(root).json() == before
    rows = [json.loads(line) for line in (tmp_path / 'logs/app.jsonl').read_text(encoding='utf-8').splitlines()]
    rejected = next(r for r in rows if r['event'] == 'planning.rejected')
    assert rejected['request_id'] == response.headers['x-request-id']
    assert rejected['project_id'] == pid and rejected['revision'] == 1
    assert rejected['validation_errors'][0]['field'] == 'operations[0].task.phase'
    assert 'SECRET' not in json.dumps(rows)


# 用例：后续任务校验输出安全的字段路径和原因，不包含原始敏感值。
# 参数：caplog 为捕获日志的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_later_task_validation_has_safe_field_and_reason(caplog):
    from backend.service.planning import validate
    from backend.schemas.planning import TaskData
    with caplog.at_level(logging.WARNING, logger='film'):
        with pytest.raises(BusinessError) as error:
            validate(TaskData, {'title': 'SECRET_TITLE', 'phase': 'SECRET_PHASE'})
    record = next(r for r in caplog.records if r.getMessage() == 'planning.validation_failed')
    logged = json.loads(JsonFormatter().format(record))
    assert logged['validation_errors'][0] == {'field': 'phase', 'type': 'literal_error', 'reason': '取值不在允许范围'}
    assert 'phase' in error.value.detail
    assert 'SECRET' not in error.value.detail + json.dumps(logged)


# 用例：模型通信超时有明确状态和日志，远端异常文本不进入用户提示。
# 参数：caplog 为捕获日志的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_transport_failure_is_logged_without_remote_body(caplog):
    import httpx
    class Timeout:
        async def chat(self, messages, tools):
            raise httpx.ReadTimeout('SECRET_REMOTE_RESPONSE')
    with caplog.at_level(logging.INFO, logger='film'):
        with pytest.raises(BusinessError) as error:
            asyncio.run(generate({}, '', Timeout()))
    assert error.value.status_code == 502 and 'model_timeout' in error.value.detail
    record = next(r for r in caplog.records if r.getMessage() == 'planning.rejected')
    logged = json.loads(JsonFormatter().format(record))
    assert logged['error_type'] == 'model_timeout'
    assert 'SECRET' not in error.value.detail + json.dumps(logged)
