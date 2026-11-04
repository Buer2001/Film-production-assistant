# 测试职责：验证统一模型客户端的配置、鉴权、消息格式和失败行为；网络请求由本地transport接管。
"""模型通信契约：使用本地 HTTP transport，测试不访问云端或 Ollama。"""
import asyncio
import json

import httpx
import pytest

from backend.ai.client import ModelClient
from backend.router.health import health


# 用途：每个模型测试开始前清空相关环境变量，避免读取本机真实配置。
# 参数：monkeypatch 为pytest替换工具；返回：无，测试后pytest恢复原环境。
@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch):
    for name in ('LLM_PROVIDER', 'LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL',
                 'LLM_TIMEOUT', 'QWEN3_BASE_URL', 'QWEN3_MODEL', 'QWEN3_TIMEOUT'):
        monkeypatch.delenv(name, raising=False)


# 用途：以本地MockTransport替换HTTP客户端，记录请求并提供可修改的响应。
# 参数：monkeypatch 为pytest替换工具；返回请求列表及状态/响应体字典，不产生网络请求。
@pytest.fixture
def server(monkeypatch):
    requests = []
    state = {'status': 200, 'body': {'choices': [{'message': {
        'role': 'assistant', 'content': '测试回答'}}]}}
    original_client = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        return httpx.Response(state['status'], json=state['body'])

    def client(**kwargs):
        return original_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(httpx, 'AsyncClient', client)
    return requests, state


# 用例：新旧导入路径返回同一个客户端类，保证现有替换和调用继续生效。
# 返回：无；使用断言或预期异常检查上述行为。
def test_legacy_import_is_same_class():
    from backend.ai.llm import ModelClient as PackagedClient
    assert ModelClient is PackagedClient


# 用例：DeepSeek沿用原配置，发送正确鉴权、模型和工具参数并保留工具响应。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具；server 为本地模拟HTTP请求记录和可调整响应。
# 返回：无；使用断言或预期异常检查上述行为。
def test_existing_deepseek_config_and_tools_are_preserved(monkeypatch, server):
    monkeypatch.setenv('LLM_API_KEY', 'test-secret')
    monkeypatch.setenv('LLM_MODEL', 'test-deepseek-model')
    monkeypatch.setenv('LLM_BASE_URL', 'https://api.deepseek.com/')
    tools = [{'type': 'function', 'function': {'name': 'submit', 'parameters': {'type': 'object'}}}]
    message = {'role': 'assistant', 'tool_calls': [{'id': 'call-1', 'type': 'function',
               'function': {'name': 'submit', 'arguments': '{}'}}]}
    server[1]['body'] = {'choices': [{'message': message}]}
    assert asyncio.run(ModelClient().chat([{'role': 'user', 'content': '测试'}], tools)) == message
    request = server[0][0]
    assert str(request.url) == 'https://api.deepseek.com/chat/completions'
    assert request.headers['Authorization'] == 'Bearer test-secret'
    assert json.loads(request.content)['tools'] == tools
    assert json.loads(request.content)['model'] == 'test-deepseek-model'


# 用例：Qwen普通对话不要求密钥、不携带云端配置，并采用本地超时。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具；server 为本地模拟HTTP请求记录和可调整响应。
# 返回：无；使用断言或预期异常检查上述行为。
def test_qwen_plain_chat_needs_no_key_and_ignores_cloud_config(monkeypatch, server):
    monkeypatch.setenv('LLM_API_KEY', 'cloud-secret')
    monkeypatch.setenv('LLM_BASE_URL', 'https://cloud.invalid')
    monkeypatch.setenv('LLM_MODEL', 'cloud-model')
    result = asyncio.run(ModelClient(provider='qwen3').chat([{'role': 'user', 'content': '你好'}]))
    assert result['content'] == '测试回答'
    request = server[0][0]
    assert str(request.url) == 'http://localhost:11434/v1/chat/completions'
    assert 'Authorization' not in request.headers
    body = json.loads(request.content)
    assert body['model'] == 'qwen3:8b-q4_K_M'
    assert 'tools' not in body
    assert request.extensions['timeout']['read'] == 180


# 用例：默认服务遵循环境配置，显式指定服务时覆盖默认选择。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具；server 为本地模拟HTTP请求记录和可调整响应。
# 返回：无；使用断言或预期异常检查上述行为。
def test_default_provider_and_explicit_override(monkeypatch, server):
    monkeypatch.setenv('LLM_PROVIDER', 'qwen3')
    monkeypatch.setenv('QWEN3_BASE_URL', 'http://127.0.0.1:12345/v1/')
    monkeypatch.setenv('QWEN3_MODEL', 'local-test')
    monkeypatch.setenv('QWEN3_TIMEOUT', '240')
    asyncio.run(ModelClient().chat([]))
    request = server[0][0]
    assert str(request.url) == 'http://127.0.0.1:12345/v1/chat/completions'
    assert json.loads(request.content)['model'] == 'local-test'
    assert request.extensions['timeout']['read'] == 240
    monkeypatch.setenv('LLM_API_KEY', 'test-secret')
    monkeypatch.setenv('LLM_MODEL', 'cloud-test')
    asyncio.run(ModelClient(provider='deepseek').chat([]))
    assert str(server[0][1].url) == 'https://api.deepseek.com/chat/completions'


# 用例：非法服务、空模型地址或无效超时在发出网络请求前被拒绝。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具；server 为本地模拟HTTP请求记录和可调整响应；setting 为待覆盖的配置项名称；value 为参数化字段值。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('setting,value', [
    ('LLM_PROVIDER', 'unknown'), ('QWEN3_TIMEOUT', 'invalid'),
    ('QWEN3_TIMEOUT', '0'), ('QWEN3_TIMEOUT', '-1'),
    ('QWEN3_TIMEOUT', 'nan'), ('QWEN3_TIMEOUT', 'inf'), ('QWEN3_MODEL', ''),
    ('QWEN3_BASE_URL', ''),
])
def test_bad_configuration_fails_before_sending(monkeypatch, server, setting, value):
    monkeypatch.setenv('LLM_PROVIDER', 'qwen3')
    monkeypatch.setenv(setting, value)
    with pytest.raises(RuntimeError):
        asyncio.run(ModelClient().chat([]))
    assert not server[0]
    assert health()['agent_configured'] is False


# 用例：健康检查按默认模型检查配置，本地服务无需云端密钥。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_health_uses_selected_provider_without_network(monkeypatch):
    assert health()['agent_configured'] is False
    monkeypatch.setenv('LLM_PROVIDER', 'qwen3')
    assert health()['agent_configured'] is True
    monkeypatch.setenv('LLM_PROVIDER', 'deepseek')
    assert health()['agent_configured'] is False
    monkeypatch.setenv('LLM_API_KEY', 'test-secret')
    monkeypatch.setenv('LLM_MODEL', 'cloud-test')
    assert health()['agent_configured'] is True


# 用例：HTTP请求失败时直接传播异常，只发一次请求且不切换模型。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具；server 为本地模拟HTTP请求记录和可调整响应。
# 返回：无；使用断言或预期异常检查上述行为。
def test_http_failure_does_not_fall_back(monkeypatch, server):
    monkeypatch.setenv('LLM_PROVIDER', 'qwen3')
    server[1]['status'] = 503
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(ModelClient().chat([]))
    assert len(server[0]) == 1


# 用例：响应缺少有效消息结构时明确报错，不伪造成功结果。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具；server 为本地模拟HTTP请求记录和可调整响应；body 为模拟服务响应体。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('body', [{}, {'choices': []}, {'choices': [{'message': None}]}])
def test_malformed_response_is_explicit_error(monkeypatch, server, body):
    monkeypatch.setenv('LLM_PROVIDER', 'qwen3')
    server[1]['body'] = body
    with pytest.raises(TypeError, match='响应'):
        asyncio.run(ModelClient().chat([]))
