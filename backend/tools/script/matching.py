# 文件职责：根据原文相似度给出前版候选，不自动确认人工匹配。
from difflib import SequenceMatcher


# 用途：计算当前场次的前版匹配候选。
# 参数：current 为当前场次字典，previous 为前版场次列表。
# 返回及副作用：返回相似度不低于 0.35、按分数降序的前 3 项，含 ID、场号和三位小数分数；不修改匹配状态。
def suggest(current, previous):
    """只提供候选，不自动确认改写场次；此处无需额外模型调用。"""
    scores = []
    for old in previous:
        score = SequenceMatcher(None, current['evidence'].get('text', ''),
                                old['evidence'].get('text', '')).ratio()
        if score >= 0.35:
            scores.append({'id': old['id'], 'scene_number': old['scene_number'], 'score': round(score, 3)})
    return sorted(scores, key=lambda item: item['score'], reverse=True)[:3]
