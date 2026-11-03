from backend.ai.prompt_loader import load_prompt
from backend.common.errors import BusinessError
from backend.common.logging.validation import validation_paths
from backend.common.logging.config import logger
from pydantic import ValidationError
from backend.ai.client import ModelClient
from backend.schemas.script import Extraction
from backend.tools.script.evidence import locate




def reject(reason, message, scene_number='', paths=None, error_count=1):
    paths = paths or []
    logger.warning('extraction.rejected', extra={
        'scene_number': scene_number, 'error_type': reason,
        'field_name': '；'.join(paths), 'error_count': error_count})
    prefix = f'第{scene_number}场：' if scene_number else ''
    fields = f'（字段：{"；".join(paths)}）' if paths else ''
    raise BusinessError(422, f'{prefix}{message}{fields} [{reason}]')


async def extract(text, model=None, *, single_scene=False, scene_number=''):
    prompt = load_prompt('script_extraction.txt')
    if single_scene:
        prompt += '\n本次输入已是一个场次片段，只提交这一场，scenes必须恰好一条；保留原场号，不按片段内的回忆或蒙太奇再次分场。'
    tools = [{'type': 'function', 'function': {'name': 'submit_breakdown',
              'description': '提交完整场次拆解', 'parameters': Extraction.model_json_schema()}}]
    response = await (model or ModelClient()).chat(
        [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': text}], tools)
    if not isinstance(response, dict):
        reject('response_invalid', '模型响应结构不正确', scene_number)
    calls = response.get('tool_calls')
    if calls is None or calls == []:
        reject('tool_missing', '模型未调用 submit_breakdown 提交拆解', scene_number)
    if not isinstance(calls, list):
        reject('response_invalid', '模型工具调用结构不正确', scene_number)
    if len(calls) != 1:
        reject('tool_count', '模型必须恰好提交一次拆解', scene_number)
    function = calls[0].get('function') if isinstance(calls[0], dict) else None
    if not isinstance(function, dict):
        reject('response_invalid', '模型工具调用结构不正确', scene_number)
    if function.get('name') != 'submit_breakdown':
        reject('tool_name', '模型调用的工具不是 submit_breakdown', scene_number)
    arguments = function.get('arguments')
    if not isinstance(arguments, str):
        reject('arguments_invalid', '模型工具参数必须是 JSON 字符串', scene_number)
    try:
        return Extraction.model_validate_json(arguments)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False, include_input=False)
        reason = 'json_invalid' if any(e['type'] == 'json_invalid' for e in errors) else 'schema_invalid'
        message = '模型工具参数不是合法 JSON' if reason == 'json_invalid' else '模型字段类型、必填项或取值不符合拆解格式'
        # 仅保留 Schema 中的字段名，额外字段可能携带任意模型文本。
        schema = Extraction.model_json_schema()
        fields = set(schema['properties'])
        for schema in schema.get('$defs', {}).values():
            fields.update(schema.get('properties', {}))
        safe_errors = [{'loc': tuple(part if isinstance(part, int) or part in fields else 'field'
                                     for part in e['loc'])} for e in errors]
        reject(reason, message, scene_number, validation_paths(safe_errors), len(errors))


async def extract_scene(source, model=None):
    """单场独立校验；异常交给任务编排隔离，不影响其他场。"""
    raw = source['evidence']['text']
    parsed = await extract(raw, model, single_scene=True, scene_number=source.get('scene_number', ''))
    if len(parsed.scenes) != 1:
        reject('scene_count', '这一段未能拆为单场，请人工核对分场', source.get('scene_number', ''))
    entries, warnings = locate(raw, parsed)
    entry = entries[0]
    number = source.get('scene_number', '')
    if number and entry['scene_number'] != number:
        reject('scene_number_mismatch', '模型场号与原场号不一致，请人工核对', number)
    # 使用分场时确定的全剧本位置，不使用模型给出的偏移。
    entry['evidence'] = dict(source['evidence'])
    entry['review_issues'] += warnings
    return entry
