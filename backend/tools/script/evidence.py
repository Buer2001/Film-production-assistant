# 文件职责：检查模型字段的原文依据，生成定位证据和待核对提示。
from backend.tools.normalization import normalized
from backend.common.errors import BusinessError
from backend.common.logging.config import logger
from backend.schemas.script import SceneData


# 用途：判定场次是否为完全无内容的占位。
# 参数：row 为场次字典。
# 返回及副作用：返回 bool；同时检查固定字段、提取结果、原文、前版关联和自定义值。
def is_empty_placeholder(row):
    """只识别完全没有内容和提取依据的占位。"""
    return (all(row.get(key) in (None, '', [], {}) for key in SceneData.model_fields)
            and not row.get('extracted_data')
            and not row.get('evidence', {}).get('text')
            and not row.get('previous_scene_id')
            and not any(row.get('custom_values', {}).values()))


# 用途：展开需要原文支持的提取字段。
# 参数：scene 为模型提取场次对象。
# 返回及副作用：返回字段路径及文本值二元组列表，覆盖场号、内外、气氛、场景、角色、道具及妆造。
def field_claims(scene):
    claims = [(key, getattr(scene, key)) for key in
              ('scene_number', 'interior_exterior', 'atmosphere', 'location')]
    claims += [(f'cast[{i}].name', item.name) for i, item in enumerate(scene.cast)]
    for key in ('action_props', 'other_props'):
        claims += [(f'{key}[{i}].name', item.name) for i, item in enumerate(getattr(scene, key))]
    claims += [(f'makeup_costume[{i}].{key}', getattr(item, key))
               for i, item in enumerate(scene.makeup_costume) for key in ('character', 'description')]
    return claims


# 用途：按提取顺序定位场次原文并验证字段依据。
# 参数：text 为完整保存原文，extraction 为含 scenes 的提取结果模型。
# 返回及副作用：返回场次列表及未覆盖原文提醒；证据缺失、重叠、乱序或字段无原文支持时记诊断日志并抛 BusinessError，不保存结果。
def locate(text, extraction):
    cursor, result, warnings, failures = 0, [], [], []
    for scene in extraction.scenes:
        raw = scene.evidence_text
        # 从上一场结束位置向后查找，既验证顺序，也禁止同一段证据被重叠复用。
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


# 用途：生成场次必需信息缺失提醒。
# 参数：data 为场次字段字典。
# 返回及副作用：返回场号、内外、气氛、场景、内容待补及演员分类待确认提示，不修改输入。
def missing(data):
    labels = {'scene_number': '场号', 'interior_exterior': '内外', 'atmosphere': '气氛',
              'location': '场景', 'summary': '内容'}
    issues = [f'{label}待补' for key, label in labels.items() if not data.get(key)]
    if any(c['category'] == '待确认' for c in data.get('cast', [])):
        issues.append('演员分类待确认')
    return issues


# 用途：检测重复非空场号。
# 参数：entries 为场次字典列表。
# 返回及副作用：返回按遇到顺序生成的重复场号提示，不修改场次或自动去重。
def duplicate_warnings(entries):
    seen, warnings = set(), []
    for row in entries:
        number = row.get('scene_number')
        if number and number in seen:
            warnings.append(f'重复场号：{number}，请核对')
        seen.add(number)
    return warnings
