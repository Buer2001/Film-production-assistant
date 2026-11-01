"""单次结构化建议，模型仅提交草稿，不执行业务工具。"""
import json
from pathlib import Path
import httpx
from pydantic import ValidationError
from backend.ai.client import ModelClient
from backend.ai.prompt_loader import load_prompt
from backend.schemas.planning import PlanResult
from backend.common.errors import BusinessError


def checklist():
    return json.loads((Path(__file__).parent / 'checklists' / 'production.json').read_text(encoding='utf-8'))['items']


async def generate(snapshot, instruction, model=None):
    payload = json.dumps({**snapshot, 'instruction': instruction, 'checklist': checklist()}, ensure_ascii=False)
    if len(payload) > 160000:
        raise BusinessError(422, '项目上下文过大，请减少冗余说明后再生成')
    tools = [{'type': 'function', 'function': {'name': 'submit_plan', 'description': '提交日程变更草稿、疑问及查漏结果',
              'parameters': PlanResult.model_json_schema()}}]
    try:
        response = await (model or ModelClient()).chat([
            {'role': 'system', 'content': load_prompt('planning.txt')}, {'role': 'user', 'content': payload}], tools)
    except (httpx.HTTPError, RuntimeError, KeyError, IndexError, TypeError) as exc:
        raise BusinessError(502, '日程生成失败，请检查模型配置或稍后重试；原有任务及草稿保留') from exc
    try:
        calls = response['tool_calls']
        if len(calls) != 1 or calls[0]['function']['name'] != 'submit_plan':
            raise ValueError('提交次数或名称错误')
        return PlanResult.model_validate_json(calls[0]['function']['arguments']).model_dump(mode='json')
    except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
        raise BusinessError(422, '模型未返回有效日程结构；原有任务及草稿保留') from exc
