import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


def test_streaming_drafts_do_not_enter_formal_scenes(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    async def extract(source, model=None):
        return {'summary': '完成', 'review_issues': [], 'extracted_data': {}}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extract)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '流式测试'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。'}).json()
        response = client.post(f"{url}/{doc['id']}/parse", json={'revision': 0})
        assert response.status_code == 200
        assert response.json()['progress']['state'] == 'running'
        with client.app.state.sessions() as session:
            from backend.dao.script.scene import list_for_script
            assert list_for_script(session, doc['id']) == []
        with client.stream('GET', f"{url}/{doc['id']}/events") as events:
            assert 'event: complete' in events.read().decode()
        final = client.get(f"{url}/{doc['id']}").json()
        assert final['scenes'][0]['parse_status'] == 'succeeded'
        assert final['progress']['state'] == 'review'


def test_failure_isolated_then_explicit_manual_or_excluded_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    from backend.service.script.jobs import ParseJobs
    from backend.service.script import breakdown
    from backend.schemas.script import SaveInput, ConfirmInput
    from backend.common.errors import BusinessError
    from backend.dao.script.scene import list_for_script
    async def extractor(source, model=None):
        if source['scene_number'] == '1':
            raise BusinessError(503, '首场失败')
        return {'summary': '第二场完成', 'review_issues': []}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '失败隔离'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。\n2 外 夜 街道\n人物离开。'}).json()
        jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)
        async def scenario():
            with jobs.sessions() as session:
                await breakdown.parse(session, pid, doc['id'], 0, jobs)
            await jobs.tasks[pid, doc['id']]
        asyncio.run(scenario())
        final = client.get(f"{url}/{doc['id']}").json()
        assert [r['parse_status'] for r in final['scenes']] == ['failed', 'succeeded']
        assert final['progress']['failed'] == 1 and final['progress']['completed'] == 1
        assert client.post(f"{url}/{doc['id']}/confirm", json={'revision': 1, 'accept_missing': True}).status_code == 422
        final['scenes'][0]['resolution'] = 'excluded'
        final['scenes'][0]['summary'] = '不应导出的非场次'
        saved = client.put(f"{url}/{doc['id']}", json={'revision': 1, 'scenes': final['scenes']}).json()
        confirmed = client.post(f"{url}/{doc['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True})
        assert confirmed.status_code == 200, confirmed.text
        with jobs.sessions() as session:
            assert len(list_for_script(session, doc['id'])) == 1
        assert len(confirmed.json()['scenes']) == 2
        from io import BytesIO
        from zipfile import ZipFile
        exported = client.get(f"{url}/{doc['id']}/export")
        with ZipFile(BytesIO(exported.content)) as archive:
            assert '不应导出的非场次' not in archive.read('xl/worksheets/sheet1.xml').decode('utf-8')
        again = client.post(f"{url}/{doc['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True})
        assert again.json()['revision'] == confirmed.json()['revision']


def test_save_during_model_call_preserves_manual_fields_and_late_result(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    from backend.service.script.jobs import ParseJobs
    from backend.service.script import breakdown
    from backend.schemas.script import SaveInput
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '交错保存'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。'}).json()
        jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)
        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            async def extractor(source, model=None):
                started.set()
                await release.wait()
                return {'summary': '模型概述', 'location': '模型地点', 'notes': '模型备注'}
            monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
            with jobs.sessions() as session:
                initial = await breakdown.parse(session, pid, doc['id'], 0, jobs)
            await started.wait()
            edited = dict(initial['scenes'][0], notes='人工备注')
            with jobs.sessions() as session:
                saved = breakdown.save(session, pid, doc['id'], SaveInput(revision=1, scenes=[edited], edited_fields={edited['id']: ['notes']}), jobs.store)
            release.set()
            await jobs.tasks[pid, doc['id']]
            with jobs.sessions() as session:
                final = breakdown.detail(session, pid, doc['id'], jobs.store)
            assert final['scenes'][0]['notes'] == '人工备注'
            assert final['scenes'][0]['summary'] == '模型概述'
            # A form opened before completion saves only its actual edit.
            edited['location'] = '人工地点'
            with jobs.sessions() as session:
                latest = breakdown.save(session, pid, doc['id'], SaveInput(revision=saved['revision'], scenes=[edited], edited_fields={edited['id']: ['location']}), jobs.store)
            assert latest['scenes'][0]['summary'] == '模型概述'
            assert latest['scenes'][0]['notes'] == '人工备注'
            assert latest['scenes'][0]['location'] == '人工地点'
        asyncio.run(scenario())


def test_restart_marks_running_draft_interrupted_and_preserves_finished_scenes(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    from backend.service.script import breakdown
    from backend.service.script.jobs import ParseJobs
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '恢复'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。'}).json()
        jobs = client.app.state.parse_jobs
        doc.update(status='parsing', progress={'state': 'running', 'stage': '解析', 'total': 2, 'completed': 1, 'failed': 0, 'sequence': 9, 'started_at': None})
        from backend.schemas.script import SceneEdit
        base = SceneEdit().model_dump(mode='json')
        doc['scenes'] = [dict(base, id='done', summary='已经完成', parse_status='succeeded'), dict(base, id='pending', parse_status='running')]
        jobs.store.write(pid, doc['id'], doc)
        result = client.get(f"{url}/{doc['id']}").json()
        assert result['progress']['state'] == 'interrupted'
        assert result['scenes'][0]['summary'] == '已经完成'
        assert result['scenes'][1]['parse_status'] == 'pending'


def test_retry_only_failed_scene_and_excluded_scene_is_not_requested(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    from backend.service.script.jobs import ParseJobs
    from backend.service.script import breakdown
    from backend.schemas.script import SaveInput
    from backend.common.errors import BusinessError
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '逐场重试'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。\n2 外 夜 街道\n人物离开。\n3 内 日 大堂\n人物返回。'}).json()
        jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)
        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            calls = []
            async def extractor(source, model=None):
                calls.append(source['scene_number'])
                if len(calls) == 1:
                    started.set()
                    await release.wait()
                    raise BusinessError(503, '暂时失败')
                return {'summary': '成功'}
            monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
            with jobs.sessions() as session:
                initial = await breakdown.parse(session, pid, doc['id'], 0, jobs)
            await started.wait()
            # Exclude the pending third scene before its request begins.
            rows = initial['scenes']
            rows[2]['resolution'] = 'excluded'
            with jobs.sessions() as session:
                saved = breakdown.save(session, pid, doc['id'], SaveInput(revision=1, scenes=rows, edited_fields={rows[2]['id']: ['resolution']}), jobs.store)
            release.set()
            await jobs.tasks[pid, doc['id']]
            assert calls == ['1', '2']
            with jobs.sessions() as session:
                retried = await breakdown.retry(session, pid, doc['id'], rows[0]['id'], saved['revision'], jobs)
            await jobs.tasks[pid, doc['id']]
            assert calls == ['1', '2', '1']
            with jobs.sessions() as session:
                final = breakdown.detail(session, pid, doc['id'], jobs.store)
                # Stale/no-op form cannot erase late model fields or omitted rows.
                unchanged = breakdown.save(session, pid, doc['id'], SaveInput(revision=retried['revision'], scenes=[rows[0]], edited_fields={}), jobs.store)
            assert len(unchanged['scenes']) == 3
            assert unchanged['scenes'][0]['summary'] == '成功'
            assert final['scenes'][2]['resolution'] == 'excluded'
            assert final['scenes'][0]['parse_status'] == 'succeeded'
        asyncio.run(scenario())


def test_file_save_and_sql_confirm_failures_can_retry_without_revision_drift(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    from backend.service.script import breakdown
    from backend.schemas.script import SaveInput, ConfirmInput
    from backend.dao.script import version as scripts, scene as scenes
    async def extractor(source, model=None):
        return {'summary': '完成'}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '失败重试'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。'}).json()
        client.post(f"{url}/{doc['id']}/parse", json={'revision': 0})
        client.get(f"{url}/{doc['id']}/events")
        doc = client.get(f"{url}/{doc['id']}").json()
        jobs = client.app.state.parse_jobs
        original = jobs.store._write
        def failed_write(path, value):
            raise OSError('模拟磁盘失败')
        with monkeypatch.context() as patch:
            patch.setattr(jobs.store, '_write', failed_write)
            with jobs.sessions() as session, pytest.raises(OSError):
                breakdown.save(session, pid, doc['id'], SaveInput(revision=doc['revision'], scenes=doc['scenes']), jobs.store)
        assert jobs.store.load(pid, doc['id'])['revision'] == doc['revision']
        with jobs.sessions() as session:
            assert scripts.get(session, pid, doc['id']).revision == doc['base_revision']
            saved = breakdown.save(session, pid, doc['id'], SaveInput(revision=doc['revision'], scenes=doc['scenes']), jobs.store)
        request = ConfirmInput(revision=saved['revision'], accept_missing=True)
        with jobs.sessions() as session:
            with monkeypatch.context() as patch:
                def failed_commit():
                    raise OSError('模拟SQL提交失败')
                patch.setattr(session, 'commit', failed_commit)
                with pytest.raises(OSError):
                    breakdown.confirm(session, pid, doc['id'], request, jobs.store)
        with jobs.sessions() as session:
            assert scenes.list_for_script(session, doc['id']) == []
            assert scripts.get(session, pid, doc['id']).revision == doc['base_revision']
        assert jobs.store.load(pid, doc['id'])['revision'] == saved['revision']
        # Commit succeeds but updating the file fails: SQL is the confirmation receipt.
        def fail_confirm_receipt(path, value):
            if value['status'] == 'confirmed':
                raise OSError('模拟确认回执写入失败')
            return original(path, value)
        with monkeypatch.context() as patch:
            patch.setattr(jobs.store, '_write', fail_confirm_receipt)
            with jobs.sessions() as session, pytest.raises(OSError):
                breakdown.confirm(session, pid, doc['id'], request, jobs.store)
        with jobs.sessions() as session:
            repaired = breakdown.confirm(session, pid, doc['id'], request, jobs.store)
            assert repaired['status'] == 'confirmed'
            assert len(scenes.list_for_script(session, doc['id'])) == 1
            assert repaired['revision'] == saved['revision'] + 1


def test_edit_confirmed_script_keeps_formal_rows_until_second_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    async def extractor(source, model=None):
        return {'summary': '原来的概述'}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
    from backend.dao.script import scene as scenes
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '二次确认'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。'}).json()
        endpoint = f"{url}/{doc['id']}"
        client.post(endpoint + '/parse', json={'revision': 0})
        client.get(endpoint + '/events')
        doc = client.get(endpoint).json()
        confirmed = client.post(endpoint + '/confirm', json={'revision': doc['revision'], 'accept_missing': True}).json()
        confirmed['scenes'][0]['summary'] = '人工新概述'
        saved = client.put(endpoint, json={'revision': confirmed['revision'], 'scenes': confirmed['scenes']}).json()
        assert saved['status'] == 'review'
        with client.app.state.sessions() as session:
            assert scenes.list_for_script(session, doc['id'])[0].summary == '原来的概述'
        assert client.post(url, json={'title': '新版', 'content': '新原文', 'previous_script_id': doc['id']}).status_code == 409
        result = client.post(endpoint + '/confirm', json={'revision': saved['revision'], 'accept_missing': True})
        assert result.status_code == 200, result.text
        with client.app.state.sessions() as session:
            assert scenes.list_for_script(session, doc['id'])[0].summary == '人工新概述'


def test_late_confirmation_receipt_repair_cannot_overwrite_new_manual_save(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, current_thread
    from backend.service.script import breakdown
    from backend.schemas.script import SaveInput
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    async def extractor(source, model=None):
        return {'summary': '原来的概述'}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '回执竞态'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        doc = client.post(url, json={'title': '测试', 'content': '1 内 日 房间\n人物进入。'}).json()
        sid = doc['id']
        endpoint = f'{url}/{sid}'
        client.post(endpoint + '/parse', json={'revision': 0})
        client.get(endpoint + '/events')
        jobs = client.app.state.parse_jobs
        stale = jobs.store.load(pid, sid)
        response = client.post(endpoint + '/confirm', json={'revision': stale['revision'], 'accept_missing': True})
        assert response.status_code == 200
        # Reproduce the durable state after SQL commits but its file receipt fails.
        jobs.store.write(pid, sid, stale)
        loaded, resume = Event(), Event()
        original_load = jobs.store.load
        intercepted = False
        def delayed_load(project_id, script_id):
            nonlocal intercepted
            value = original_load(project_id, script_id)
            if current_thread().name.startswith('late-reader') and not intercepted:
                intercepted = True
                loaded.set()
                assert resume.wait(5), '等待并发人工保存超时'
            return value
        monkeypatch.setattr(jobs.store, 'load', delayed_load)
        def late_reader():
            with jobs.sessions() as session:
                return breakdown.detail(session, pid, sid, jobs.store)
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='late-reader') as pool:
            late = pool.submit(late_reader)
            try:
                assert loaded.wait(5), '旧草稿读取未开始'
                with jobs.sessions() as session:
                    repaired = breakdown.detail(session, pid, sid, jobs.store)
                    repaired['scenes'][0]['summary'] = '刚保存的人工修改'
                    saved = breakdown.save(session, pid, sid, SaveInput(revision=repaired['revision'], scenes=repaired['scenes']), jobs.store)
            finally:
                resume.set()
            late_result = late.result(timeout=5)
        durable = original_load(pid, sid)
        assert durable['scenes'][0]['summary'] == '刚保存的人工修改'
        assert durable['revision'] == saved['revision']
        assert durable['status'] == 'review'
        assert late_result['revision'] == saved['revision']
        assert late_result['scenes'][0]['summary'] == '刚保存的人工修改'


def test_completed_sse_snapshot_has_current_comparison_and_manual_missing_hints(tmp_path, monkeypatch):
    import json
    from backend.service.script import breakdown
    from backend.service.script.jobs import ParseJobs
    from backend.schemas.script import SaveInput
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    async def initial_extractor(source, model=None):
        return {'location': '房间', 'summary': '人物进入'}
    monkeypatch.setattr('backend.ai.script_extractor.extract_scene', initial_extractor)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '流式比较'}).json()['id']
        url = f'/api/projects/{pid}/script-workspace'
        old = client.post(url, json={'title': '初版', 'content': '1 内 日 房间\n人物进入。'}).json()
        endpoint = f"{url}/{old['id']}"
        client.post(endpoint + '/parse', json={'revision': 0})
        client.get(endpoint + '/events')
        old = client.get(endpoint).json()
        response = client.post(endpoint + '/confirm', json={'revision': old['revision'], 'accept_missing': True})
        assert response.status_code == 200
        new = client.post(url, json={'title': '新版', 'content': old['content'], 'previous_script_id': old['id']}).json()
        jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)
        async def scenario():
            started, release = asyncio.Event(), asyncio.Event()
            async def extractor(source, model=None):
                started.set()
                await release.wait()
                return {'location': '', 'summary': '人物进入', 'review_issues': ['场景待补']}
            monkeypatch.setattr('backend.ai.script_extractor.extract_scene', extractor)
            with jobs.sessions() as session:
                parsed = await breakdown.parse(session, pid, new['id'], 0, jobs)
            await started.wait()
            entry = dict(parsed['scenes'][0], notes='人工确认的新备注', location='人工场景')
            with jobs.sessions() as session:
                breakdown.save(session, pid, new['id'], SaveInput(revision=parsed['revision'], scenes=[entry], edited_fields={entry['id']: ['notes', 'location']}), jobs.store)
            release.set()
            await jobs.tasks[pid, new['id']]
            events = [event async for event in jobs.events(pid, new['id'])]
            payload = json.loads(events[-1].split('data: ', 1)[1])['document']
            assert payload['progress']['state'] == 'review'
            assert payload['comparison']['deleted'] == []
            assert payload['comparison']['pending'] == []
            assert len(payload['comparison']['changed']) == 1
            assert 'notes' in payload['comparison']['changed'][0]['fields']
            assert 'location' in payload['comparison']['changed'][0]['fields']
            assert '场景待补' not in payload['scenes'][0]['review_issues']
            assert payload['comparison'] == jobs.store.load(pid, new['id'])['comparison']
        asyncio.run(scenario())
