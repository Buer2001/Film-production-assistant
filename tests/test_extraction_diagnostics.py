import asyncio
import json
import logging

import pytest

from backend.ai.script_extractor import extract_scene
from backend.common.errors import BusinessError
from backend.common.logging.config import JsonFormatter


class Reply:
    def __init__(self, response):
        self.response = response

    async def chat(self, messages, tools):
        return self.response


def call(arguments, name='submit_breakdown'):
    return {'tool_calls': [{'function': {'name': name, 'arguments': arguments}}]}


@pytest.mark.parametrize('response, reason, path', [
    ({'content': 'SECRET_RESPONSE'}, 'tool_missing', ''),
    ({'tool_calls': [{}, {}]}, 'tool_count', ''),
    (call('{}', 'SECRET_TOOL'), 'tool_name', ''),
    (call('{SECRET_JSON'), 'json_invalid', ''),
    (call(None), 'arguments_invalid', ''),
    ({'tool_calls': [None]}, 'response_invalid', ''),
    (None, 'response_invalid', ''),
    (call(json.dumps({'scenes': [{'evidence_text': '8 日 内 研究室'}] * 2})), 'scene_count', ''),
    (call(json.dumps({'scenes': [{'scene_number': '', 'evidence_text': '8 日 内 研究室'}]})),
        'scene_number_mismatch', ''),
    (call(json.dumps({'scenes': [{'evidence_text': '8 日 内 研究室',
        'cast': [{'name': '刘念', 'category': 'SECRET_CATEGORY'}]}]})),
        'schema_invalid', 'scenes[0].cast[0].category'),
    (call(json.dumps({'scenes': [{'evidence_text': '8 日 内 研究室',
        'SECRET_KEY': 'SECRET_VALUE'}]})), 'schema_invalid', 'scenes[0].field'),
])
def test_scene_diagnostics_are_specific_and_safe(response, reason, path, caplog):
    source = {'scene_number': '8', 'evidence': {'text': '8 日 内 研究室'}}
    with caplog.at_level(logging.WARNING, logger='film'):
        with pytest.raises(BusinessError) as error:
            asyncio.run(extract_scene(source, Reply(response)))
    assert error.value.status_code == 422
    assert reason in error.value.detail
    assert '第8场' in error.value.detail
    assert path in error.value.detail
    records = [r for r in caplog.records if r.getMessage() == 'extraction.rejected']
    assert len(records) == 1
    logged = json.loads(JsonFormatter().format(records[0]))
    assert logged['scene_number'] == '8'
    assert logged['error_type'] == reason
    assert 'SECRET' not in error.value.detail + json.dumps(logged)


def test_valid_response_keeps_evidence_validation():
    source = {'scene_number': '8', 'evidence': {'text': '8 日 内 研究室'}}
    args = json.dumps({'scenes': [{'scene_number': '8', 'location': '研究室',
        'evidence_text': source['evidence']['text']}]})
    result = asyncio.run(extract_scene(source, Reply(call(args))))
    assert result['location'] == '研究室'
    args = json.dumps({'scenes': [{'scene_number': '8', 'location': '不存在场地',
        'evidence_text': source['evidence']['text']}]})
    with pytest.raises(BusinessError, match='原文依据'):
        asyncio.run(extract_scene(source, Reply(call(args))))


def test_validation_paths_are_bounded_unique_and_do_not_mutate_input():
    from backend.ai.script_extractor import validation_paths
    errors = [{'loc': ('scenes', 0, 'cast', 1, 'category')},
              {'loc': ('scenes', 0, 'cast', 1, 'category')},
              {'loc': ()}, {'loc': ('unsafe.key',)}]
    assert validation_paths(errors) == ['scenes[0].cast[1].category', 'response', 'field']
    assert validation_paths(errors, 1) == ['scenes[0].cast[1].category']
    assert validation_paths(errors, 0) == validation_paths(errors, -1) == []
    assert validation_paths([]) == []
    assert errors[0]['loc'] == ('scenes', 0, 'cast', 1, 'category')
