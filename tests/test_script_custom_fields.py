from io import BytesIO
from zipfile import ZipFile
import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'fields.db'}")) as value:
        yield value


def project(client):
    pid = client.post('/api/projects', json={'name': '字段测试'}).json()['id']
    return pid, f'/api/projects/{pid}/script-workspace'


def test_count_body_ignores_header_and_whitespace():
    from backend.tools.script.text import scene_word_count
    assert scene_word_count('1、日 内 房间\n甲 A1。\n\t乙') == 5
    assert scene_word_count('INT. ROOM - DAY\r\n A B ！') == 3
    assert scene_word_count('第十二场 日 内 房间\n人物走入。') == 5
    assert scene_word_count('人物走入。') == 5
    assert scene_word_count('') == 0


def test_project_fields_are_isolated_versioned_and_archived(client):
    pid, root = project(client)
    _, other = project(client)
    initial = client.get(f'{root}/fields').json()
    assert initial == {'revision': 0, 'fields': []}
    response = client.put(f'{root}/fields', json={'revision': 0, 'fields': [{'name': '车辆', 'description': '需要准备的车辆'}]})
    assert response.status_code == 200, response.text
    config = response.json()
    column = config['fields'][0]
    assert column['id'] and config['revision'] == 1
    assert client.get(f'{other}/fields').json()['fields'] == []
    assert client.put(f'{root}/fields', json={'revision': 0, 'fields': []}).status_code == 409
    archived = client.put(f'{root}/fields', json={'revision': 1, 'fields': []}).json()
    assert archived['fields'][0]['id'] == column['id']
    assert archived['fields'][0]['active'] is False
    assert client.put(f'{root}/fields', json={'revision': 2, 'fields': [column, column]}).status_code == 422
    assert client.put(f'{root}/fields', json={'revision': 2, 'fields': [{'name': '场号'}]}).status_code == 422
    assert client.get('/api/projects/missing/script-workspace/fields').status_code == 404


def test_custom_values_survive_confirmation_export_and_removed_draft(client):
    pid, root = project(client)
    config = client.put(f'{root}/fields', json={'revision': 0, 'fields': [{'name': '车辆'}]}).json()
    key = config['fields'][0]['id']
    doc = client.post(root, json={'title': '字段测试', 'content': '1 内 日 房间\n人物走入。'}).json()
    import uuid
    scene = {'id': str(uuid.uuid4()), 'scene_number': '1', 'summary': '人物进入房间。',
             'resolution': 'manual', 'custom_values': {key: '自行车'},
             'action_props': [{'name': '手表', 'description': '不应导出的人物动作'}]}
    saved = client.put(f"{root}/{doc['id']}", json={'revision': 0, 'scenes': [scene]})
    assert saved.status_code == 200, saved.text
    value = saved.json()
    assert value['scenes'][0]['custom_values'][key] == '自行车'
    assert '页数待补' not in value['scenes'][0]['review_issues']
    result = client.post(f"{root}/{doc['id']}/confirm", json={'revision': value['revision'], 'accept_missing': True})
    assert result.status_code == 200, result.text
    client.app.state.parse_jobs.store.delete(pid, doc['id'])
    reloaded = client.get(f"{root}/{doc['id']}").json()
    assert reloaded['scenes'][0]['custom_values'][key] == '自行车'
    exported = client.get(f"{root}/{doc['id']}/export")
    assert exported.status_code == 200, exported.text
    with ZipFile(BytesIO(exported.content)) as z:
        xml = z.read('xl/worksheets/sheet1.xml').decode()
    assert '车辆' in xml and '自行车' in xml and '字数' in xml
    assert '页数' not in xml and '不应导出的人物动作' not in xml
    archived = client.put(f'{root}/fields', json={'revision': config['revision'], 'fields': []})
    assert archived.status_code == 200
    assert client.get(f"{root}/{doc['id']}").json()['scenes'][0]['custom_values'][key] == '自行车'
    restored = client.put(f'{root}/fields', json={'revision': archived.json()['revision'], 'fields': config['fields']})
    assert restored.status_code == 200


def test_running_job_preserves_manual_custom_values_and_counts(client, monkeypatch):
    from backend.service.script import breakdown
    from backend.schemas.script import SaveInput
    from backend.service.script.jobs import ParseJobs
    pid, root = project(client)
    config = client.put(f'{root}/fields', json={'revision': 0, 'fields': [{'name': '车辆'}]}).json()
    key = config['fields'][0]['id']
    doc = client.post(root, json={'title': '异步', 'content': '1 内 日 房间\n人物走入。'}).json()
    jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)

    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def fake(source, model=None):
            started.set()
            await release.wait()
            return {'summary': '人物进入。', 'review_issues': []}
        monkeypatch.setattr('backend.ai.script_extractor.extract_scene', fake)
        with jobs.sessions() as session:
            initial = await breakdown.parse(session, pid, doc['id'], 0, jobs)
        await started.wait()
        row = dict(initial['scenes'][0], custom_values={key: '轿车'}, word_count=999)
        with jobs.sessions() as session:
            breakdown.save(session, pid, doc['id'], SaveInput(revision=1, scenes=[row],
                edited_fields={row['id']: ['custom_values', 'word_count']}), jobs.store)
        release.set()
        await jobs.tasks[pid, doc['id']]
    asyncio.run(scenario())
    final = client.get(f"{root}/{doc['id']}").json()
    assert final['scenes'][0]['word_count'] == 5
    assert final['scenes'][0]['custom_values'][key] == '轿车'
    assert final['scenes'][0]['parse_status'] == 'succeeded'
    unknown = dict(final['scenes'][0], custom_values={'unknown': '值'})
    assert client.put(f"{root}/{doc['id']}", json={'revision': final['revision'], 'scenes': [unknown]}).status_code == 422


def test_old_draft_without_custom_values_can_confirm_reload_and_save(client):
    pid, root = project(client)
    doc = client.post(root, json={'title': '旧版草稿', 'content': '1 内 日 房间\n人物走入。'}).json()
    row = {'scene_number': '1', 'summary': '人物进入。', 'resolution': 'manual'}
    saved = client.put(f"{root}/{doc['id']}", json={'revision': 0, 'scenes': [row]}).json()
    store = client.app.state.parse_jobs.store
    def legacy(value):
        for entry in value['scenes']:
            entry.pop('custom_values', None)
        return value
    store.update(pid, doc['id'], legacy)
    response = client.post(f"{root}/{doc['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True})
    assert response.status_code == 200, response.text
    store.delete(pid, doc['id'])
    reloaded = client.get(f"{root}/{doc['id']}").json()
    assert reloaded['scenes'][0]['custom_values'] == {}
    assert client.get(f"{root}/{doc['id']}/export").status_code == 200
    response = client.put(f"{root}/{doc['id']}", json={'revision': reloaded['revision'], 'scenes': reloaded['scenes']})
    assert response.status_code == 200, response.text


def test_change_export_does_not_include_prop_descriptions():
    from backend.tools.script.exporter import export_workbook
    before = {'action_props': [{'name': '手表', 'description': 'SECRET_OLD_ACTION'}]}
    after = {'action_props': [{'name': '怀表', 'description': 'SECRET_NEW_ACTION'}]}
    doc = {'title': '导出测试', 'version_number': 2, 'version_label': '', 'revision': 1,
           'status': 'confirmed', 'confirmed_at': '', 'scenes': [], 'comparison': {
               'changed': [{'scene_number': '1', 'fields': ['action_props'], 'before': before, 'after': after}],
               'added': [], 'deleted': []}}
    with ZipFile(BytesIO(export_workbook(doc))) as z:
        xml = z.read('xl/worksheets/sheet2.xml').decode()
    assert '手表' in xml and '怀表' in xml and 'SECRET' not in xml


def test_unchanged_script_version_inherits_custom_values(client, monkeypatch):
    from backend.service.script import breakdown
    from backend.service.script.jobs import ParseJobs
    pid, root = project(client)
    config = client.put(f'{root}/fields', json={'revision': 0, 'fields': [{'name': '车辆'}]}).json()
    key = config['fields'][0]['id']
    text = '1 内 日 房间\n人物走入。'
    async def fake(source, model=None):
        return {'summary': '人物进入。', 'review_issues': []}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', fake)
    first = client.post(root, json={'title': '版本一', 'content': text}).json()
    jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)
    async def parse(doc):
        with jobs.sessions() as session:
            await breakdown.parse(session, pid, doc['id'], doc['revision'], jobs)
        await jobs.tasks[pid, doc['id']]
    asyncio.run(parse(first))
    first = client.get(f"{root}/{first['id']}").json()
    row = dict(first['scenes'][0], custom_values={key: '自行车'})
    saved = client.put(f"{root}/{first['id']}", json={'revision': first['revision'], 'scenes': [row]}).json()
    confirmed = client.post(f"{root}/{first['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True})
    assert confirmed.status_code == 200, confirmed.text
    newer = client.post(root, json={'title': '版本二', 'content': text, 'previous_script_id': first['id']}).json()
    asyncio.run(parse(newer))
    newer = client.get(f"{root}/{newer['id']}").json()
    assert newer['scenes'][0]['custom_values'][key] == '自行车'
    assert newer['scenes'][0]['match_status'] == 'matched'
    assert client.put(f"{root}/{first['id']}", json={'revision': saved['revision'], 'scenes': [row]}).status_code == 409
