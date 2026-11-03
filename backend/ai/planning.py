"""单次结构化建议及安全诊断；模型仅提交草稿，不执行业务工具。"""
import json
from pathlib import Path
from time import perf_counter
import httpx
from pydantic import ValidationError
from backend.ai.client import ModelClient
from backend.ai.prompt_loader import load_prompt
from backend.schemas.planning import PlanResult, DepartmentResult
from backend.common.errors import BusinessError
from backend.common.logging.config import logger
from backend.common.logging.validation import validation_diagnostics, diagnostic_summary


def checklist():
    return json.loads((Path(__file__).parent / 'checklists' / 'production.json').read_text(encoding='utf-8'))['items']


async def _request(data, model, context, *, schema, tool_name, prompt_name, label, operation):
    start = perf_counter()
    payload = json.dumps(data, ensure_ascii=False)
    fields = {k: v for k, v in (context or {}).items() if k in ('project_id', 'script_id', 'revision')}
    fields.update(operation=operation, input_chars=len(payload))

    def reject(reason, message, *, diagnostics=None, status=422, metadata=None):
        diagnostics = diagnostics or {'error_count': 1, 'error_types': {}, 'validation_errors': [], 'field_name': ''}
        logger.warning('planning.rejected', extra={**fields, **(metadata or {}), **diagnostics,
                       'error_type': reason, 'duration_ms': round((perf_counter() - start) * 1000, 2)})
        summary = diagnostic_summary(diagnostics)
        detail = f'{message}' + (f'（{summary}）' if summary else '')
        raise BusinessError(status, f'{detail}；原有任务及草稿保留 [{reason}]')

    if len(payload) > 160000:
        reject('context_too_large', '项目上下文过大，请减少冗余说明后再生成')
    tools = [{'type': 'function', 'function': {'name': tool_name, 'description': f'提交{label}结构化结果',
              'parameters': schema.model_json_schema()}}]
    logger.info('planning.requested', extra=fields)
    try:
        response = await (model or ModelClient()).chat([
            {'role': 'system', 'content': load_prompt(prompt_name)}, {'role': 'user', 'content': payload}], tools)
    except httpx.TimeoutException:
        reject('model_timeout', '模型请求超时，请稍后手动重试', status=502)
    except httpx.HTTPError:
        reject('model_transport_error', '模型通信失败，请检查服务后手动重试', status=502)
    except RuntimeError:
        reject('model_configuration_error', '模型配置或运行异常，请检查模型配置', status=502)
    except (KeyError, IndexError, TypeError):
        reject('response_invalid', '模型服务响应结构不正确', status=502)
    if not isinstance(response, dict):
        reject('response_invalid', '模型响应不是有效对象')
    calls = response.get('tool_calls')
    if calls is None or calls == []:
        reject('tool_missing', f'模型未调用 {tool_name} 提交{label}')
    if not isinstance(calls, list):
        reject('response_invalid', '模型工具调用应为列表')
    if len(calls) != 1:
        reject('tool_count', f'模型必须恰好提交一次{label}', metadata={'tool_call_count': len(calls)})
    function = calls[0].get('function') if isinstance(calls[0], dict) else None
    if not isinstance(function, dict):
        reject('response_invalid', '模型工具调用结构不正确')
    if function.get('name') != tool_name:
        reject('tool_name', f'模型调用的工具不是 {tool_name}')
    arguments = function.get('arguments')
    if not isinstance(arguments, str):
        reject('arguments_invalid', f'模型{label}参数必须是JSON字符串')
    try:
        result = schema.model_validate_json(arguments).model_dump(mode='json')
    except ValidationError as exc:
        diagnostics = validation_diagnostics(exc, schema)
        reason = 'json_invalid' if 'json_invalid' in diagnostics['error_types'] else 'schema_invalid'
        message = f'模型{label}参数不是合法JSON' if reason == 'json_invalid' else f'模型{label}字段未通过校验'
        reject(reason, message, diagnostics=diagnostics, metadata={'value_length': len(arguments)})
    logger.info('planning.response_validated', extra={**fields, 'value_length': len(arguments),
                'operation_count': len(result.get('operations', result.get('assignments', []))), 'duration_ms': round((perf_counter() - start) * 1000, 2)})
    return result


async def generate(snapshot, instruction, model=None, *, context=None):
    return await _request({**snapshot, 'instruction': instruction, 'checklist': checklist()}, model, context,
        schema=PlanResult, tool_name='submit_plan', prompt_name='planning.txt', label='日程', operation='planning.generate')


async def departments(tasks, model=None, *, context=None):
    return await _request({'tasks': tasks}, model, context, schema=DepartmentResult, tool_name='submit_departments',
        prompt_name='planning_departments.txt', label='部门建议', operation='planning.departments')
