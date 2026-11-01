from backend.tools.script.splitter import HEADER, ENGLISH


def scene_word_count(text: str) -> int:
    lines = text.splitlines()
    if not lines:
        return 0
    if HEADER.match(lines[0]) or ENGLISH.match(lines[0]):
        processed_lines = lines[1:]
    else:
        processed_lines = lines
    return sum(not char.isspace() for line in processed_lines for char in line)


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
