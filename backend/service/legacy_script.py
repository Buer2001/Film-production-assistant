from backend.ai.legacy_extractor import extract_script
from backend.schemas.legacy_script import Strict, ScriptInput, Scene, Extraction
from backend.common.errors import BusinessError
from backend.schemas.change import ChangeInput
from backend.service.project import get_project, state, change_dict
from backend.service.change import propose
from backend.dao.change import get_change
from backend.dao.event import add_event, get_event, list_events, set_event_data
from backend.dao.project import lock_project
from backend.tools.normalization import normalized, unique


async def parse_script(s, pid, request):
    if get_project(s, pid).revision != request.base_revision:
        raise BusinessError(409, '项目版本已变化，请刷新后重新解析')
    result = await extract_script(request.text)
    s.expire_all()
    if get_project(s, pid).revision != request.base_revision:
        raise BusinessError(409, '解析期间项目已变化，请刷新后重新解析')
    existing = {normalized(r['data']['title']) for r in state(s, pid)['records'] if r['kind'] == 'scene'}
    for scene in result['scenes']:
        if scene['title'] in existing:
            result['warnings'].append(f'已有同名场次：{scene["title"]}；导入将新增，不会覆盖')
    event = add_event(s, pid, 'script_parse', {**result,
        'source_name': request.source_name, 'base_revision': request.base_revision})
    s.commit()
    return {'id': event.id, **event.data}


def script_draft(s, pid, eid):
    # 复用项目行锁，同一解析记录只转换为一个草稿。
    event = get_event(s, eid)
    if not event or event.project_id != pid or event.type != 'script_parse':
        raise BusinessError(404, '解析记录不存在')
    lock_project(s, pid)
    s.refresh(event)
    if event.data.get('change_id'):
        return change_dict(get_change(s, event.data['change_id']))
    data = event.data
    operations = []
    for scene in data['scenes']:
        notes = f"人物：{'、'.join(scene['characters'])}\n场地：{scene['location']}\n道具：{'、'.join(scene['props'])}\n"
        notes += f"昼夜：{scene['time']}；内外景：{scene['interior']}\n待确认：{'；'.join(scene['questions'])}\n原文：\n{scene['evidence']}"
        operations.append({'kind': 'scene', 'data': {'title': scene['title'], 'status': '待确认',
            'resources': unique([*scene['characters'], scene['location'], *scene['props']]),
            'source': f"{data['source_name']} L{scene['line_start']}-{scene['line_end']}", 'notes': notes}})
    request = ChangeInput(base_revision=data['base_revision'], reason='剧本解析：' + data['source_name'], operations=operations)
    change = propose(s, pid, request, commit=False)
    set_event_data(event, {**event.data, 'change_id': change['id']})
    s.commit()
    return change


def script_history(s, pid):
    get_project(s, pid)
    return [{'id': event.id, **event.data} for event in sorted(list_events(s, pid),
        key=lambda event: event.created_at, reverse=True) if event.type == 'script_parse'][:20]
