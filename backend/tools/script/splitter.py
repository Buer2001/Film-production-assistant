# 文件职责：按明确标题分场并保存原文证据；无法识别可靠边界时保留内容供人工核对。
"""根据明确场次标题分段；不确定边界保留原文，交人工核对。"""
import re

NUMBER = r'[0-9０-９]+[A-Za-z]?|[一二三四五六七八九十百零〇]+'
HEADER = re.compile(
    rf'^\s*(?:第\s*(?P<chinese>{NUMBER})\s*[场幕](?:戏)?|'
    rf'(?:场次|场号|场)\s*[:：]?\s*(?P<label>{NUMBER})|'
    rf'(?P<number>{NUMBER})(?:[、.．:：）)]|\s+))(?P<rest>.*)$')
ENGLISH = re.compile(r'^\s*(?:INT\.?|EXT\.?|INT\.?\s*/\s*EXT\.?)\s', re.I)
NON_SCENE = re.compile(r'演职人员表|演职员表|演员表|制作人员|片尾字幕|片头字幕|^目录\s*$')


# 用途：识别中文编号或英文内外景标题并按字符位置切分。
# 参数：text 为已规范换行的剧本原文。
# 返回及副作用：返回 scenes 和 warnings；保留原文偏移及行号，排除明确非叙事资料，超过 200 场抛 BusinessError，不静默截断。
def split_scenes(text):
    lines = text.splitlines(keepends=True)
    markers, cursor = [], 0
    for line in lines:
        title = line.strip()
        match = HEADER.match(title)
        if match and len(title) <= 180:
            number = next((match.group(key) for key in ('chinese', 'label', 'number') if match.group(key)), '')
            markers.append((cursor, number, bool(NON_SCENE.search(match.group('rest')))))
        elif len(title) <= 180 and ENGLISH.match(title):
            markers.append((cursor, '', False))
        elif NON_SCENE.fullmatch(title):
            markers.append((cursor, '', True))
        # 偏移按原始字符累计而非 strip 后标题长度，确保切片及行号仍对应完整保存原文。
        cursor += len(line)
    warnings, scenes = [], []
    if not markers:
        markers = [(0, '', False)]
        warnings.append('未识别可靠场次标题，已保留整段原文，请人工核对分场并增删场次')
    elif text[:markers[0][0]].strip():
        warnings.append('首个场次前有标题或说明文字，未作为场次，请核对')
    for index, (start, number, excluded) in enumerate(markers):
        end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        if excluded:
            warnings.append(f'第{text.count(chr(10), 0, start) + 1}行起为非叙事资料，未自动作为场次')
            continue
        raw = text[start:end]
        if not raw.strip():
            continue
        evidence = {'text': raw, 'start': start, 'end': end,
                    'line_start': text.count('\n', 0, start) + 1,
                    'line_end': text.count('\n', 0, max(start, end - 1)) + 1, 'manual_fields': []}
        scenes.append({'scene_number': number, 'source_start': start, 'source_end': end, 'evidence': evidence})
    if len(scenes) > 200:
        from backend.common.errors import BusinessError
        raise BusinessError(422, '超过200场，请拆分剧本；未静默截断')
    if not scenes:
        warnings.append('没有识别到叙事场次，可手工增加场次')
    return {'scenes': scenes, 'warnings': warnings}
