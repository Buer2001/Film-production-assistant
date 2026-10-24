import os
import httpx


class ModelClient:
    """OpenAI-compatible chat API; credentials never reach the browser."""
    async def chat(self, messages, tools):
        key, model = os.getenv('LLM_API_KEY'), os.getenv('LLM_MODEL')
        if not key or not model:
            raise RuntimeError('请配置 LLM_API_KEY 和 LLM_MODEL 后使用 Agent')
        base = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(base + '/chat/completions', headers={
                'Authorization': f'Bearer {key}'}, json={
                'model': model, 'messages': messages, 'tools': tools})
            response.raise_for_status()
            return response.json()['choices'][0]['message']
