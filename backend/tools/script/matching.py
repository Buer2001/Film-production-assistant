from difflib import SequenceMatcher


def suggest(current, previous):
    """只提供候选，不自动确认改写场次；此处无需额外模型调用。"""
    scores = []
    for old in previous:
        score = SequenceMatcher(None, current['evidence'].get('text', ''),
                                old['evidence'].get('text', '')).ratio()
        if score >= 0.35:
            scores.append({'id': old['id'], 'scene_number': old['scene_number'], 'score': round(score, 3)})
    return sorted(scores, key=lambda item: item['score'], reverse=True)[:3]
