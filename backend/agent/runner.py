import json
from pathlib import Path
from backend.ai.prompt_loader import load_prompt
from backend.common.errors import BusinessError
from backend.agent.context import build_context
from backend.agent.tools import execute, schemas
from backend.common.database.base import uid
from backend.service.event import save_chat
from backend.ai.client import ModelClient


async def run(s, pid, request, model=None):
    session_id = request.session_id or uid()
    context, history = build_context(s, pid, session_id)
    # Agent使用自己的提示词，模型通信与读取能力仍复用AI层。
    prompt = load_prompt('system.txt', directory=Path(__file__).parent / 'prompts')
    messages = [{'role': 'system', 'content': prompt},
                {'role': 'system', 'content': '当前项目索引：' + context},
                *history, {'role': 'user', 'content': request.message}]
    client = model or ModelClient()
    trace = []
    for _ in range(8):
        result = await client.chat(messages, schemas())
        messages.append({k: v for k, v in result.items() if k in ('role', 'content', 'tool_calls')})
        calls = result.get('tool_calls') or []
        if not calls:
            answer = result.get('content') or '未生成回答，请补充具体问题。'
            save_chat(s, pid, {'session_id': session_id,
                'message': request.message, 'answer': answer, 'tools': trace})
            return {'session_id': session_id, 'answer': answer, 'tools': trace}
        if len(calls) > 8:
            raise BusinessError(422, '单轮工具数量超出限制')
        for call in calls:
            fn = call['function']
            try:
                output = execute(s, pid, fn['name'], json.loads(fn['arguments']))
            except (ValueError, BusinessError) as exc:
                output = {'error': str(getattr(exc, 'detail', exc))}
            trace.append({'tool': fn['name'], 'result': output})
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': json.dumps(output, ensure_ascii=False)})
    raise BusinessError(422, '已达到工具调用轮次限制，请缩小问题范围；已生成的草稿可在待确认区查看')
