import json, logging
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.common.errors import BusinessError
from backend.schemas.script import Extraction
from backend.tools.script.evidence import locate
import pytest


def test_missing_field_error_identifies_scene_and_field(caplog):
    parsed = Extraction.model_validate({'scenes': [{'scene_number': '1', 'location': '不存在场地',
        'evidence_text': '1 内 日 车内\n晚来握着玉佩。'}]})
    with caplog.at_level(logging.WARNING, logger='film'):
        with pytest.raises(BusinessError) as error:
            locate('1 内 日 车内\n晚来握着玉佩。', parsed)
    assert '第1场' in error.value.detail and 'location' in error.value.detail
    assert any(getattr(record, 'field_name', '') == 'location' for record in caplog.records)


def test_middleware_logs_requests_without_business_decorators(tmp_path, monkeypatch):
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    app = create_app(f"sqlite:///{tmp_path / 'logs.db'}")
    @app.get('/test/success')
    def endpoint():
        return {'ok': True}
    @app.get('/test/error')
    def bad():
        raise ValueError('SECRET_ERROR_TEXT')
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/test/success', headers={'Authorization': 'Bearer SECRET_TOKEN'})
        assert response.status_code == 200
        request_id = response.headers['x-request-id']
        failed = client.get('/test/error?token=SECRET_QUERY')
        assert failed.status_code == 500 and failed.headers.get('x-request-id')
        missing = client.get('/not-found')
        assert missing.status_code == 404 and missing.headers.get('x-request-id')
    raw = (tmp_path / 'logs/app.jsonl').read_text(encoding='utf-8')
    assert 'SECRET_TOKEN' not in raw and 'SECRET_ERROR_TEXT' not in raw and 'SECRET_QUERY' not in raw
    logs = [json.loads(line) for line in raw.splitlines()]
    assert any(row['event'] == 'http.complete' and row['request_id'] == request_id for row in logs)
    assert any(row['event'] == 'http.complete' and row.get('status') == 500 for row in logs)
    assert any(row['event'] == 'http.complete' and row.get('status') == 404 for row in logs)


def test_async_and_validation_errors_have_request_ids(tmp_path, monkeypatch):
    from backend.common.logging.context import request_id
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    app = create_app(f"sqlite:///{tmp_path / 'async.db'}")
    @app.get('/test/async')
    async def endpoint():
        raise HTTPException(422, 'SECRET_DETAIL')
    @app.get('/test/parameter')
    def parameter(number: int):
        return number
    with TestClient(app) as client:
        failed = client.get('/test/async')
        invalid = client.get('/test/parameter?number=SECRET_PARAMETER')
    assert failed.status_code == invalid.status_code == 422
    assert failed.headers['x-request-id'] != invalid.headers['x-request-id']
    raw = (tmp_path / 'logs/app.jsonl').read_text(encoding='utf-8')
    assert 'SECRET_DETAIL' not in raw and 'SECRET_PARAMETER' not in raw
    records = [json.loads(line) for line in raw.splitlines()]
    assert any(r['event'] == 'http.complete' and r.get('error_type') == 'HTTPException' and r['request_id'] == failed.headers['x-request-id'] for r in records)
    assert request_id.get() == '-'


@pytest.mark.parametrize('operation', ['parse_script', 'run'])
def test_legacy_errors_use_same_middleware_log(tmp_path, monkeypatch, caplog, operation):
    import backend.agent.router as agent_router
    import backend.router.legacy_script as legacy_router
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    async def fail(*args, **kwargs):
        raise ValueError('SECRET_MODEL_PAYLOAD')
    monkeypatch.setattr(legacy_router if operation == 'parse_script' else agent_router, operation, fail)
    app = create_app(f"sqlite:///{tmp_path / 'legacy.db'}")
    with TestClient(app) as client:
        pid = client.post('/api/projects', json={'name': '日志测试'}).json()['id']
        if operation == 'run':
            response = client.post(f'/api/projects/{pid}/agent', json={'message': 'test'})
        else:
            response = client.post(f'/api/projects/{pid}/scripts/parse', json={'text': 'test', 'base_revision': 0})
    assert response.status_code == 502
    rows = [json.loads(line) for line in (tmp_path / 'logs/app.jsonl').read_text(encoding='utf-8').splitlines()]
    failure = next(r for r in rows if r['request_id'] == response.headers['x-request-id'])
    assert failure['event'] == 'http.complete' and failure['error_type'] == 'ValueError'
    assert 'SECRET_MODEL_PAYLOAD' not in caplog.text
