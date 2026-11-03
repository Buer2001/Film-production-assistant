import asyncio
import json
import logging
import pytest
from backend.ai.planning import generate
from backend.common.errors import BusinessError
from backend.common.logging.config import JsonFormatter


class Reply:
    def __init__(self, response):
        self.response = response

    async def chat(self, messages, tools):
        return self.response


def call(arguments, name='submit_plan'):
    return {'tool_calls': [{'function': {'name': name, 'arguments': arguments}}]}


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
