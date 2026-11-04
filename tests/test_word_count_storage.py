# 测试职责：验证字数的正式存储和离线迁移，包括备份、幂等及失败补偿。
import json
import pytest

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models.script import SceneBreakdown
from backend.dao.script import scene as dao


# 用例：正式存储字数根据原文计算，不接受伪造字数并移除旧页数字段。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_confirmation_storage_uses_calculated_word_count(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'storage.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '统计持久化'}).json()['id']
        root = f'/api/projects/{pid}/script-workspace'
        doc = client.post(root, json={'title': '测试', 'content': '1 内 日 房间\n人物走入。'}).json()
        row = {'scene_number': '1', 'summary': '进入。', 'resolution': 'manual',
               'page_count': 3, 'word_count': 999}
        saved = client.put(f"{root}/{doc['id']}", json={'revision': 0, 'scenes': [row]}).json()
        result = client.post(f"{root}/{doc['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True})
        assert result.status_code == 200, result.text
        with client.app.state.sessions() as session:
            record = dao.list_for_script(session, doc['id'])[0]
            assert record.details['word_count'] is None
            assert 'page_count' not in record.details
            raw = '1 内 日 房间\n甲 A1。\n\t乙'
            # DAO也必须忽略伪造字数，不能依赖某个接口恰好先完成统计。
            data = dao.as_dict(record)
            data.update(word_count=999, page_count=3, evidence={'text': raw})
            dao.replace(session, doc['id'], [data])
            session.commit()
            assert record.details['word_count'] == 5
            assert 'page_count' not in record.details
            assert 'page_count' not in dao.as_dict(record)


# 用例：字数迁移先备份原始数据，保留人工自定义值且重复执行无新增变更。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_migration_backs_up_and_is_idempotent(tmp_path, monkeypatch):
    from scripts.migrate_word_counts import migrate
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'migration.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '旧数据'}).json()['id']
        root = f'/api/projects/{pid}/script-workspace'
        doc = client.post(root, json={'title': '旧版', 'content': '1 内 日 房间\n人物走入。'}).json()
        with client.app.state.sessions() as session:
            a = SceneBreakdown(script_id=doc['id'], sort_order=0, details={'page_count': 2, 'cast': []},
                evidence={'text': '1 内 日 房间\n人物走入。'})
            b = SceneBreakdown(script_id=doc['id'], sort_order=1, details={'page_count': 9}, evidence={})
            session.add_all([a, b]); session.commit()
        store = client.app.state.parse_jobs.store
        store.write(pid, doc['id'], {'id': doc['id'], 'project_id': pid, 'revision': 4,
            'progress': {'state': 'review'}, 'scenes': [{'page_count': 7, 'evidence': {'text': '1 内 日 房间\n人物走入。'},
            'custom_values': {'车辆': '自行车'}, 'review_issues': ['页数待补']}], 'previous_scenes': []})
        backup = tmp_path / 'backup'
        with client.app.state.sessions() as session:
            result = migrate(session, store, backup)
        assert result['database_rows'] == 2 and result['draft_files'] == 1
        old = json.loads((backup / 'database.json').read_text(encoding='utf-8'))
        assert old[0]['details']['page_count'] == 2
        with client.app.state.sessions() as session:
            records = dao.list_for_script(session, doc['id'])
            assert [r.details['word_count'] for r in records] == [5, None]
            assert all('page_count' not in r.details for r in records)
        draft = store.load(pid, doc['id'])
        assert draft['revision'] == 4
        assert draft['scenes'][0]['word_count'] == 5
        assert 'page_count' not in draft['scenes'][0]
        assert draft['scenes'][0]['custom_values'] == {'车辆': '自行车'}
        with client.app.state.sessions() as session:
            assert migrate(session, store, tmp_path / 'second') == {'database_rows': 0, 'draft_files': 0}


# 用例：模型提取Schema不要求页数或字数，统计由程序完成。
# 返回：无；使用断言或预期异常检查上述行为。
def test_model_schema_does_not_request_page_or_word_count():
    from backend.schemas.script import ExtractedScene
    fields = ExtractedScene.model_json_schema()['properties']
    assert 'page_count' not in fields and 'word_count' not in fields


# 用例：字数迁移失败时回滚数据库并尝试恢复全部已写草稿。
# 参数：tmp_path 为测试专用临时目录；monkeypatch 为临时替换配置或依赖的pytest工具；failure 为注入的迁移故障阶段。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('failure', ['write', 'commit', 'restore'])
def test_migration_failure_rolls_back_and_attempts_every_restore(tmp_path, monkeypatch, failure):
    from scripts.migrate_word_counts import migrate
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    monkeypatch.setenv('LOG_DIR', str(tmp_path / 'logs'))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'rollback.db'}")) as client:
        store = client.app.state.parse_jobs.store
        originals = {}
        for index in range(3):
            pid = client.post('/api/projects', json={'name': f'迁移{index}'}).json()['id']
            doc = client.post(f'/api/projects/{pid}/script-workspace', json={'title': '测试', 'content': '原文'}).json()
            draft = {'id': doc['id'], 'project_id': pid, 'scenes': [{'page_count': 7, 'evidence': {'text': '1 内 日 房间\n人。'}}]}
            store.write(pid, doc['id'], draft)
            originals[(pid, doc['id'])] = draft
        with client.app.state.sessions() as session:
            row = SceneBreakdown(script_id=doc['id'], sort_order=0, details={'page_count': 4}, evidence={})
            session.add(row); session.commit(); rid = row.id
        original_write, calls = store.write, []
        def failing_write(pid, sid, value):
            calls.append((pid, sid))
            if failure in ('write', 'restore') and len(calls) == 3:
                raise OSError('write failure')
            if failure == 'restore' and len(calls) == 4:
                raise OSError('restore failure')
            return original_write(pid, sid, value)
        monkeypatch.setattr(store, 'write', failing_write)
        with client.app.state.sessions() as session:
            if failure == 'commit':
                def failing_commit():
                    raise OSError('commit failure')
                monkeypatch.setattr(session, 'commit', failing_commit)
            with pytest.raises(RuntimeError if failure == 'restore' else OSError) as error:
                migrate(session, store, tmp_path / 'backup')
        if failure == 'restore':
            assert '原始备份' in str(error.value)
            assert len(calls) == 5  # 一个恢复失败后，仍继续恢复下一个文件。
            failed_key = calls[3]
        else:
            failed_key = None
        for key, draft in originals.items():
            if key != failed_key:
                assert store.load(*key) == draft
        with client.app.state.sessions() as session:
            assert session.get(SceneBreakdown, rid).details == {'page_count': 4}
