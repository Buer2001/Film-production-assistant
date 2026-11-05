# 文件职责：推进 V5 状态机并在步骤边界保存进度；旧的对话工具循环保持原样，供旧助手入口使用。
import json
from pathlib import Path
from backend.ai.prompt_loader import load_prompt
from backend.common.errors import BusinessError
from backend.agent import steps, state_machine
from backend.agent.context import build_context
from backend.agent.tools import execute, schemas
from backend.common.database.base import uid
from backend.dao import agent as agent_dao
from backend.service.event import save_chat
from backend.ai.client import ModelClient

# 单次请求最多推进的步骤数；超出说明转换有问题，不能无限循环。
MAX_STEPS = 12


# 按 current_step 依次推进直到进入等待状态；每步结束后条件更新运行状态并提交一次。
# 使用 version 条件更新，两个请求同时推进同一次工作时只有一个能成功。
# 模型步骤会先提交读事务再等待响应，因此步骤返回后运行记录可能已过期，取值前会重新加载。
async def advance(session, pid, run, payload=None):
    for _ in range(MAX_STEPS):
        step = run.current_step
        handler = getattr(steps, f'step_{step}', None)
        if handler is None:
            raise BusinessError(500, f'未知步骤：{step}')
        result = await handler(session, pid, run, payload)
        payload = None
        target = result['next']
        state_machine.check(step, target)
        state = {**(run.state_json or {}), **result.get('patch', {})}
        fields = {'current_step': target, 'status': state_machine.status_for(target),
                  'state_json': state, **result.get('columns', {})}
        # 步骤边界保存：状态写入数据库，进程重启后仍能从这里继续。
        if agent_dao.claim_run(session, run.id, run.version, fields=fields) != 1:
            raise BusinessError(409, '该工作已被其他请求推进，请刷新后重试')
        session.commit()
        session.refresh(run)
        if run.status != 'running':
            return run
    raise BusinessError(422, '步骤数量超出上限，请缩小范围后重试')


# 接收会话 s、项目 pid、对话 request 及可注入 model；返回会话 ID、回答和轨迹，最多执行八轮工具调用并保存聊天事件。
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

    # 限制整个对话的工具往返次数；另对单轮工具数设限，防止失控循环。
    for _ in range(8):
        result = await client.chat(messages, schemas())
        messages.append({k: v for k, v in result.items() if k in ('role', 'content', 'tool_calls')})
        calls = result.get('tool_calls') or []
        # 模型停止调用工具才记入完成的聊天事件；此前产生的草稿由各业务工具独立维护。
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

                # 工具失败后先释放事务和项目锁，不能持锁等待下一轮模型响应。
                s.rollback()
                output = {'error': str(getattr(exc, 'detail', exc))}
            trace.append({'tool': fn['name'], 'result': output})
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': json.dumps(output, ensure_ascii=False)})
    raise BusinessError(422, '已达到工具调用轮次限制，请缩小问题范围；已生成的草稿可在待确认区查看')
