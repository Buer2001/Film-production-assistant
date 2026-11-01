from backend.tools.normalization import normalized
from backend.common.errors import BusinessError
from backend.common.logging.config import logger
from backend.schemas.script import SceneData


def is_empty_placeholder(row):
    """只识别完全没有内容和提取依据的占位。"""
    return (all(row.get(key) in (None, '', [], {}) for key in SceneData.model_fields)
            and not row.get('extracted_data')
            and not row.get('evidence', {}).get('text')
            and not row.get('previous_scene_id')
            and not any(row.get('custom_values', {}).values()))


def field_claims(scene):
    claims = [(key, getattr(scene, key)) for key in
              ('scene_number', 'interior_exterior', 'atmosphere', 'location')]
    claims += [(f'cast[{i}].name', item.name) for i, item in enumerate(scene.cast)]
    for key in ('action_props', 'other_props'):
        claims += [(f'{key}[{i}].name', item.name) for i, item in enumerate(getattr(scene, key))]
    claims += [(f'makeup_costume[{i}].{key}', getattr(item, key))
               for i, item in enumerate(scene.makeup_costume) for key in ('character', 'description')]
    return claims


def locate(text, extraction):
    cursor, result, warnings, failures = 0, [], [], []
    for scene in extraction.scenes:
        raw = scene.evidence_text
        start = text.find(raw, cursor)
        if start < 0:
            logger.warning('evidence.source_mismatch', extra={
                'scene_number': scene.scene_number, 'scene_index': len(result) + 1,
                'field_name': 'evidence_text', 'value_length': len(raw)})
            raise BusinessError(422, f'第{scene.scene_number or len(result) + 1}场 evidence_text 原文不存在、顺序错误或重叠，未保存拆解结果')
        if text[cursor:start].strip():
            warnings.append(f'第{text.count(chr(10), 0, cursor) + 1}行起存在未覆盖原文')
        end = start + len(raw)
        data = scene.model_dump(mode='json', exclude={'evidence_text'})
        # 保留字段路径，区分模型改写和原文定位失败，禁止只报一句模糊错误。
        for field, value in field_claims(scene):
            if value and normalized(value) not in normalized(raw):
                logger.warning('evidence.unsupported_field', extra={
                    'scene_number': scene.scene_number, 'scene_index': len(result) + 1,
                    'field_name': field, 'value_length': len(value)})
                failures.append(f'第{scene.scene_number or len(result) + 1}场 {field}=「{value[:80]}」')
        evidence = {'text': raw, 'start': start, 'end': end,
                    'line_start': text.count('\n', 0, start) + 1,
                    'line_end': text.count('\n', 0, end - 1) + 1,
                    'manual_fields': []}
        result.append({**data, 'evidence': evidence, 'extracted_data': data,
                       'review_issues': missing(data), 'change_reviewed': False})
        cursor = end
    if text[cursor:].strip():
        warnings.append('剧本尾部有未覆盖原文')
    if failures:
        logger.warning('evidence.rejected', extra={'error_count': len(failures), 'scene_count': len(result)})
        preview = '；'.join(failures[:6])
        raise BusinessError(422, f'提取字段缺少该场原文依据（共{len(failures)}项）：{preview}。模型可能改写或合并了原文，请重试。')
    return result, warnings


def missing(data):
    labels = {'scene_number': '场号', 'interior_exterior': '内外', 'atmosphere': '气氛',
              'location': '场景', 'summary': '内容'}
    issues = [f'{label}待补' for key, label in labels.items() if not data.get(key)]
    if any(c['category'] == '待确认' for c in data.get('cast', [])):
        issues.append('演员分类待确认')
    return issues


def duplicate_warnings(entries):
    seen, warnings = set(), []
    for row in entries:
        number = row.get('scene_number')
        if number and number in seen:
            warnings.append(f'重复场号：{number}，请核对')
        seen.add(number)
    return warnings
