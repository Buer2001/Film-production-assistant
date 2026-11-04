# 封装兼容 Chat Completions 的异步 HTTP 请求，统一配置读取和响应结构校验。
"""DeepSeek、Ollama 共用兼容接口；不处理业务提示词和拆解结果。"""
import httpx

from .config import load_config


# 可指定服务提供者的轻量客户端，每次调用独立创建并关闭 HTTP 客户端。
class ModelClient:
    # 保存可选 provider，配置在每次调用时读取；不缓存密钥。
    def __init__(self, provider=None):
        self.provider = provider

    # 接收 messages 和可选 tools，返回响应首项 message 字典；HTTP 失败向上传递，响应缺字段或类型错误抛 TypeError。
    async def chat(self, messages, tools=None):

        # 调用时读取配置，保留现有测试/业务通过替换 chat 注入模型的用法。
        config = load_config(self.provider)
        headers = {'Authorization': f'Bearer {config.api_key}'} if config.api_key else {}
        payload = {'model': config.model, 'messages': messages}
        if tools:
            payload['tools'] = tools
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            response = await client.post(config.base_url + '/chat/completions',
                                         headers=headers, json=payload)
            response.raise_for_status()
        try:
            message = response.json()['choices'][0]['message']
        except (ValueError, KeyError, IndexError, TypeError):
            raise TypeError('模型服务响应结构不正确') from None
        if not isinstance(message, dict):
            raise TypeError('模型服务响应 message 必须是对象')
        return message
