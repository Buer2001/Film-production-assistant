from backend.ai.prompt_loader import load_prompt
from backend.common.errors import BusinessError
from pydantic import ValidationError
from backend.ai.client import ModelClient
from backend.schemas.script import Extraction
from backend.tools.script.evidence import locate


async def extract(text, model=None, *, single_scene=False):
    prompt = load_prompt('script_extraction.txt')
    if single_scene:
        prompt += '\n本次输入已是一个场次片段，只提交这一场，scenes必须恰好一条；保留原场号，不按片段内的回忆或蒙太奇再次分场。'
    tools = [{'type': 'function', 'function': {'name': 'submit_breakdown',
              'description': '提交完整场次拆解', 'parameters': Extraction.model_json_schema()}}]
    response = await (model or ModelClient()).chat(
        [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': text}], tools)
    try:
        calls = response.get('tool_calls') or []
        if len(calls) != 1 or calls[0]['function']['name'] != 'submit_breakdown':
            raise ValueError('需要一次结构化提交')
        return Extraction.model_validate_json(calls[0]['function']['arguments'])
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise BusinessError(422, '模型没有返回有效拆解结构，请重试或缩小剧本范围') from exc


async def extract_scene(source, model=None):
    """单场独立校验；异常交给任务编排隔离，不影响其他场。"""
    raw = source['evidence']['text']
    parsed = await extract(raw, model, single_scene=True)
    if len(parsed.scenes) != 1:
        raise BusinessError(422, '这一段未能拆为单场，请人工核对分场')
    entries, warnings = locate(raw, parsed)
    entry = entries[0]
    number = source.get('scene_number', '')
    if number and entry['scene_number'] != number:
        raise BusinessError(422, '模型场号与原场号不一致，请人工核对')
    # 使用分场时确定的全剧本位置，不使用模型给出的偏移。
    entry['evidence'] = dict(source['evidence'])
    entry['review_issues'] += warnings
    return entry
