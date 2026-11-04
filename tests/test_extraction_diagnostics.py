# 测试职责：验证拆解工具响应的错误诊断、字段定位及敏感文本屏蔽。
import asyncio
import json
import logging

import pytest

from backend.ai.script_extractor import extract_scene
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
def call(arguments, name='submit_breakdown'):
    return {'tool_calls': [{'function': {'name': name, 'arguments': arguments}}]}


# 用例：拆解失败指出具体原因和字段路径，日志不包含模型敏感文本。
# 参数：response 为待验证的模拟模型响应；reason 为预期错误原因标识；path 为预期字段路径；caplog 为捕获日志的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
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


# 用例：格式正确的工具响应仍须通过原文证据校验。
# 返回：无；使用断言或预期异常检查上述行为。
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


# 用例：校验路径输出去重且限制数量，不修改原始错误输入。
# 返回：无；使用断言或预期异常检查上述行为。
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
