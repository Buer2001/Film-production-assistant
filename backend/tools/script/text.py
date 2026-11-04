# 文件职责：从保存原文重算字数，清理停用页数信息及对应提醒。
from backend.tools.script.splitter import HEADER, ENGLISH


# 用途：统计去掉首行场次标题后的非空白字符数。
# 参数：text 为场次原文。
# 返回及副作用：返回整数；仅首行匹配分场标题时去掉首行，空文本返回 0。
def scene_word_count(text: str) -> int:
    lines = text.splitlines()
    if not lines:
        return 0
    if HEADER.match(lines[0]) or ENGLISH.match(lines[0]):
        processed_lines = lines[1:]
    else:
        processed_lines = lines
    return sum(not char.isspace() for line in processed_lines for char in line)


# 用途：刷新场次统计及兼容字段。
# 参数：row 为可变场次字典。
# 返回及副作用：原地重算 word_count、移除 page_count 及相关人工标记和提示、补空 custom_values，再返回 row；无原文时字数为 None。
def refresh_scene_metadata(row):
    """统计只相信保留的原文；无原文的人工场次不能伪造字数。"""
    raw = row.get('evidence', {}).get('text', '')
    row['word_count'] = scene_word_count(raw) if raw else None
    row.pop('page_count', None)
    if 'manual_fields' in row.get('evidence', {}):
        row['evidence']['manual_fields'] = [field for field in row['evidence']['manual_fields'] if field != 'page_count']
    row['custom_values'] = row.get('custom_values') or {}
    row['review_issues'] = [issue for issue in row.get('review_issues', []) if issue != '页数待补']
    return row
