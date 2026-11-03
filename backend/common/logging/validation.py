"""安全的校验摘要：只输出Schema字段、标准错误码和固定文案，不输出值/响应。"""
from collections import Counter


def validation_paths(errors: list[dict], limit: int = 6) -> list[str]:
    if limit <= 0:
        return []
    paths = []
    seen = set()
    for error in errors:
        loc = error['loc']
        current_path = ''
        for part in loc:
            if isinstance(part, int):
                current_path += f'[{part}]'
            else:
                if not part.isidentifier():
                    part = 'field'
                if current_path == '':
                    current_path += part
                else:
                    current_path += f'.{part}'
        if not current_path:
            current_path = 'response'
        if current_path not in seen:
            seen.add(current_path)
            paths.append(current_path)
            if len(paths) >= limit:
                break
    return paths



ERROR_LABELS = {
    'missing': '缺少必填字段',
    'extra_forbidden': '存在不支持的字段',
    'literal_error': '取值不在允许范围',
    'enum': '取值不在允许范围',
    'json_invalid': '参数不是合法JSON（可能语法错误或内容不完整）',
    'json_type': '参数必须是JSON字符串',
    'string_type': '应为字符串',
    'string_too_short': '字符串为空或过短',
    'string_too_long': '字符串过长',
    'list_type': '应为列表',
    'dict_type': '应为对象',
    'model_type': '对象结构不正确',
    'model_attributes_type': '对象结构不正确',
    'int_type': '应为整数',
    'int_parsing': '无法转换为整数',
    'int_from_float': '应为整数而非小数',
    'float_type': '应为数字',
    'float_parsing': '无法转换为数字',
    'bool_type': '应为布尔值',
    'bool_parsing': '无法转换为布尔值',
    'date_type': '应为日期',
    'date_parsing': '日期格式无效',
    'date_from_datetime_parsing': '日期格式无效',
    'date_from_datetime_inexact': '日期不能包含非零时分秒',
    'greater_than': '数值低于允许下限',
    'greater_than_equal': '数值低于允许下限',
    'less_than': '数值超出允许上限',
    'less_than_equal': '数值超出允许上限',
    'too_long': '列表或内容超过长度上限',
    'too_short': '列表或内容不足最小长度',
    'value_error': '字段组合不符合规则，请核对日期顺序或操作所需字段',
    'validation_error': '字段未通过校验',
}


def validation_diagnostics(error, schema, limit=6):
    """计数完整、样例有界；未知字段和自定义错误码都不直接输出。"""
    document = schema.model_json_schema()
    allowed = set(document.get('properties', {}))
    for definition in document.get('$defs', {}).values():
        allowed.update(definition.get('properties', {}))
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    samples, seen, counts = [], set(), Counter()
    for item in errors:
        code = item['type'] if item['type'] in ERROR_LABELS else 'validation_error'
        counts[code] += 1
        if len(samples) >= limit:
            continue
        safe = tuple(part if isinstance(part, int) or part in allowed else 'field' for part in item['loc'])
        path = validation_paths([{'loc': safe}], 1)[0]
        if (path, code) not in seen:
            seen.add((path, code))
            samples.append({'field': path, 'type': code, 'reason': ERROR_LABELS[code]})
    return {'error_count': len(errors), 'error_types': dict(counts), 'validation_errors': samples,
            'field_name': '；'.join(dict.fromkeys(s['field'] for s in samples))}


def diagnostic_summary(diagnostics):
    return '；'.join(f"{item['field']}：{item['reason']}" for item in diagnostics['validation_errors'])
