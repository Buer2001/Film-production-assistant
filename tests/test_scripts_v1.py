# 测试职责：验证剧本版本工作流：编辑、解析、匹配、确认、导出和并发版本保护。
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app

TEXT = "1 内 日 车内\n晚来握着玉佩。"
SCENE = {"scene_number": "1", "interior_exterior": "内", "atmosphere": "日",
         "location": "车内", "summary": "晚来握着玉佩", "cast": [{"name": "晚来", "category": "主要角色"}],
         "action_props": [{"name": "玉佩", "description": ""}], "evidence_text": TEXT}

# 用途：创建使用临时SQLite数据库的测试应用，并由上下文管理应用生命周期。
# 参数：tmp_path 为pytest临时目录；存在 monkeypatch 参数时用于隔离草稿、日志或模型依赖。
# 产出：FastAPI TestClient；测试结束后退出客户端上下文，不连接正式数据库。
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    from backend.ai.client import ModelClient
    async def chat(self, messages, tools):
        import json
        text = messages[-1]["content"]
        scene = {**SCENE, "evidence_text": text}
        if "手机" in text:
            scene["action_props"] = [{"name": "手机", "description": ""}]
            scene["summary"] = "晚来拿着手机"
        return {"tool_calls": [{"function": {"name": "submit_breakdown",
                "arguments": json.dumps({"scenes": [scene]}, ensure_ascii=False)}}]}
    monkeypatch.setattr(ModelClient, "chat", chat)
    with TestClient(create_app(f"sqlite:///{tmp_path / 'v1.db'}")) as c:
        yield c

# 用途：创建初稿或修订版本，启动模拟解析并读取完成后的草稿。
# 参数：c 为客户端，previous 为可选前版，text 为剧本文本；返回工作区路径和草稿。
# 副作用：需要时先确认前版，只修改测试项目中的剧本状态。
def setup(c, previous=None, text=TEXT):
    pid = previous["project_id"] if previous else c.post("/api/projects", json={"name": "降生"}).json()["id"]
    root = f"/api/projects/{pid}/script-workspace"
    if previous:
        latest = c.get(f"{root}/{previous['id']}").json()
        if latest['status'] != 'confirmed':
            result = c.post(f"{root}/{previous['id']}/confirm", json={'revision': latest['revision'], 'accept_missing': True})
            assert result.status_code == 200, result.text
    res = c.post(root, json={"title": "降生", "version_label": "修订" if previous else "初稿",
                           "content": text, "previous_script_id": previous["id"] if previous else None})
    assert res.status_code == 200, res.text
    doc = res.json()
    response = c.post(f"{root}/{doc['id']}/parse", json={"revision": doc["revision"]})
    assert response.status_code == 200, response.text
    c.get(f"{root}/{doc['id']}/events")
    return root, c.get(f"{root}/{doc['id']}").json()

# 用例：剧本可保存、确认和导出，旧版本请求不能覆盖新修改。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_edit_confirm_export_and_revision(client):
    root, doc = setup(client)
    row = doc["scenes"][0]
    row["notes"] = "制片人工补充"
    res = client.put(f"{root}/{doc['id']}", json={"revision": doc["revision"], "scenes": [row],
                                              "deleted_reviewed": True})
    assert res.status_code == 200, res.text
    saved = res.json()
    assert saved["scenes"][0]["notes"] == "制片人工补充"
    assert client.put(f"{root}/{doc['id']}", json={"revision": doc["revision"], "scenes": [row]}).status_code == 409
    assert client.post(f"{root}/{doc['id']}/confirm", json={"revision": saved["revision"],
                       "accept_missing": True}).status_code == 200
    data = client.get(f"{root}/{doc['id']}").json()
    exported = client.get(f"{root}/{doc['id']}/export")
    assert exported.status_code == 200 and exported.content[:2] == b"PK"
    assert data["status"] == "confirmed"
    assert client.post(f"{root}/{doc['id']}/parse", json={"revision": data["revision"]}).status_code == 409

# 用例：新剧本版本保留人工内容，旧版本进入只读状态。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_new_version_preserves_manual_and_locks_history(client):
    root, old = setup(client)
    old["scenes"][0]["notes"] = "自备雨伞"
    old = client.put(f"{root}/{old['id']}", json={"revision": old["revision"], "scenes": old["scenes"]}).json()
    root, new = setup(client, old)
    assert new["scenes"][0]["notes"] == "自备雨伞"
    assert new["scenes"][0]["previous_scene_id"] == old["scenes"][0]["id"]
    assert client.put(f"{root}/{old['id']}", json={"revision": old["revision"], "scenes": old["scenes"]}).status_code == 409
    assert client.get(f"{root}/{old['id']}").json()["scenes"][0]["notes"] == "自备雨伞"

# 用例：变化场次需要人工处理匹配和差异确认。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_changed_scene_requires_manual_match_and_review(client):
    root, old = setup(client)
    root, new = setup(client, old, "1 内 日 车内\n晚来拿着手机。")
    assert new["scenes"][0]["match_status"] == "pending"
    assert client.post(f"{root}/{new['id']}/confirm", json={"revision": new["revision"], "accept_missing": True}).status_code == 422
    row = new["scenes"][0]
    row.update(previous_scene_id=old["scenes"][0]["id"], match_status="matched", change_reviewed=True)
    new = client.put(f"{root}/{new['id']}", json={"revision": new["revision"],
                      "scenes": [row], "deleted_reviewed": True}).json()
    assert client.post(f"{root}/{new['id']}/confirm", json={"revision": new["revision"], "accept_missing": True}).status_code == 200
    assert "action_props" in new["comparison"]["changed"][0]["fields"]


# 用例：修订剧本可在明确批量确认差异后提交正式版本。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_revision_can_be_confirmed_with_batch_acknowledgement(client):
    from io import BytesIO
    from zipfile import ZipFile
    root, old = setup(client)
    root, new = setup(client, old, '1 内 日 车内\n晚来拿着手机。')
    response = client.post(f"{root}/{new['id']}/confirm", json={
        'revision': new['revision'], 'accept_missing': True, 'accept_unreviewed': True})
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed['scenes'][0]['match_status'] == 'pending'
    assert confirmed['scenes'][0]['previous_scene_id'] is None
    assert confirmed['scenes'][0]['change_reviewed'] is False
    assert confirmed['deleted_reviewed'] is False
    assert confirmed['comparison']['added'] == []
    assert confirmed['comparison']['deleted'] == []
    assert len(confirmed['comparison']['unlinked']) == 1
    exported = client.get(f"{root}/{new['id']}/export")
    with ZipFile(BytesIO(exported.content)) as z:
        xml = z.read('xl/worksheets/sheet2.xml').decode()
    assert '待匹配' in xml and '未关联旧场次' in xml
    assert '>删除<' not in xml and '>新增<' not in xml
    store = client.app.state.parse_jobs.store
    store.delete(confirmed['project_id'], confirmed['id'])
    restored = client.get(f"{root}/{new['id']}").json()
    assert restored['scenes'][0]['match_status'] == 'pending'
    assert restored['scenes'][0]['change_reviewed'] is False
    assert restored['comparison']['deleted'] == []


# 用例：已匹配且未变化的场次无需逐条勾选即可确认。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_matched_unchanged_scene_does_not_require_individual_check(client):
    root, old = setup(client)
    root, new = setup(client, old)
    assert new['scenes'][0]['match_status'] == 'matched'
    assert new['scenes'][0]['change_reviewed'] is False
    response = client.post(f"{root}/{new['id']}/confirm", json={
        'revision': new['revision'], 'accept_missing': True, 'accept_unreviewed': True})
    assert response.status_code == 200, response.text
    assert response.json()['scenes'][0]['change_reviewed'] is False


# 用例：只有明确复核的未关联旧场次才归为删除，其余仍待处理。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_only_reviewed_unlinked_scenes_are_classified_as_deleted(client):
    root, old = setup(client)
    root, new = setup(client, old, '1 内 日 车内\n晚来拿着手机。')
    row = dict(new['scenes'][0], match_status='new', previous_scene_id=None, change_reviewed=False)
    saved = client.put(f"{root}/{new['id']}", json={'revision': new['revision'], 'scenes': [row]}).json()
    assert saved['comparison']['deleted'] == []
    assert len(saved['comparison']['unlinked']) == 1
    saved = client.put(f"{root}/{new['id']}", json={
        'revision': saved['revision'], 'scenes': saved['scenes'], 'deleted_reviewed': True}).json()
    assert len(saved['comparison']['deleted']) == 1
    assert saved['comparison']['unlinked'] == []

# 用例：跨项目访问被隔离，证据校验失败不会丢失可编辑草稿。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_project_isolation_and_evidence_failure(client, monkeypatch):
    root, doc = setup(client)
    other = client.post("/api/projects", json={"name": "其他"}).json()["id"]
    assert client.get(f"/api/projects/{other}/script-workspace/{doc['id']}").status_code == 404
    from backend.ai.client import ModelClient
    async def bad(self, messages, tools):
        return {"tool_calls": [{"function": {"name": "submit_breakdown", "arguments":
            '{"scenes":[{"scene_number":"1","evidence_text":"不存在的原文"}]}'}}]}
    monkeypatch.setattr(ModelClient, "chat", bad)
    client.post(f"{root}/{doc['id']}/confirm", json={"revision": doc["revision"], "accept_missing": True})
    res = client.post(root, json={"title": "新版", "content": "其他原文", "previous_script_id": doc["id"]}).json()
    failed = client.post(f"{root}/{res['id']}/parse", json={"revision": 0})
    assert failed.status_code == 200
    client.get(f"{root}/{res['id']}/events")
    state = client.get(f"{root}/{res['id']}").json()
    assert state["status"] == "review" and state["scenes"][0]["parse_status"] == "failed"
    assert client.get(f"{root}/{doc['id']}").json()["scenes"]

# 用例：重复确认保持版本不变，确认后的编辑重新进入待复核状态。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_confirmation_retry_and_edit_reopens(client):
    root, doc = setup(client)
    url = f"{root}/{doc['id']}"
    confirmed = client.post(url + '/confirm', json={'revision': doc['revision'], 'accept_missing': True}).json()
    retry = client.post(url + '/confirm', json={'revision': confirmed['revision'], 'accept_missing': True})
    assert retry.status_code == 200
    assert retry.json()['revision'] == confirmed['revision']
    confirmed['scenes'][0]['notes'] = '确认后修订'
    edited = client.put(url, json={'revision': confirmed['revision'], 'scenes': confirmed['scenes']}).json()
    assert edited['status'] == 'review' and edited['confirmed_at'] is None


# 用例：伪造场次ID写入失败不推进版本，导出文件仍为有效XML内容。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_fake_scene_id_rolls_back_revision_and_export_is_valid_xml(client):
    from io import BytesIO
    from zipfile import ZipFile
    from xml.etree import ElementTree
    root, doc = setup(client)
    row = {**doc['scenes'][0], 'id': 'foreign-id'}
    assert client.put(f"{root}/{doc['id']}", json={'revision': doc['revision'], 'scenes': [row]}).status_code == 422
    assert client.get(f"{root}/{doc['id']}").json()['revision'] == doc['revision']
    response = client.get(f"{root}/{doc['id']}/export")
    with ZipFile(BytesIO(response.content)) as archive:
        for path in archive.namelist():
            ElementTree.fromstring(archive.read(path))
        assert '玉佩' in archive.read('xl/worksheets/sheet1.xml').decode()


# 用例：同一版本的并发保存只允许一个成功，其余返回版本冲突。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_same_revision_concurrent_save_has_one_winner(client):
    from concurrent.futures import ThreadPoolExecutor
    root, doc = setup(client)
    def edit(note):
        row = {**doc['scenes'][0], 'notes': note}
        return client.put(f"{root}/{doc['id']}", json={'revision': doc['revision'], 'scenes': [row]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(edit, ['第一台', '第二台']))
    assert sorted(codes) == [200, 409]

# 用例：增量创建剧本表时保留已有项目数据。
# 参数：tmp_path 为测试专用临时目录。
# 返回：无；使用断言或预期异常检查上述行为。
def test_additive_migration_preserves_existing_data(tmp_path):
    from sqlalchemy import inspect
    from backend.common.database.store import database, Project
    from backend.common.database.migrations.script_v1 import upgrade
    engine, sessions = database(f"sqlite:///{tmp_path / 'existing.db'}")
    with sessions() as session:
        session.add(Project(id='old-project', name='已有项目'))
        session.commit()
    upgrade(engine)
    upgrade(engine)
    assert {'scripts', 'scene_breakdowns'} <= set(inspect(engine).get_table_names())
    with sessions() as session:
        assert session.get(Project, 'old-project').name == '已有项目'
    engine.dispose()

# 用例：取消解析后到达的模型结果不能覆盖更新后的任务状态。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_cancelled_parse_cannot_overwrite_newer_state(client, monkeypatch):
    import asyncio
    from backend.service.script.breakdown import parse, recover
    from backend.service.script.jobs import ParseJobs
    pid = client.post('/api/projects', json={'name': '恢复测试'}).json()['id']
    root = f'/api/projects/{pid}/script-workspace'
    doc = client.post(root, json={'title': '恢复', 'content': TEXT}).json()

    async def scenario():
        started = asyncio.Event()
        async def slow(source, model=None):
            started.set()
            await asyncio.Event().wait()
        monkeypatch.setattr('backend.ai.script_extractor.extract_scene', slow)
        jobs = ParseJobs(client.app.state.sessions, client.app.state.parse_jobs.store)
        with client.app.state.sessions() as first:
            await parse(first, pid, doc['id'], 0, jobs)
        await started.wait()
        with client.app.state.sessions() as second:
            cancelled = await recover(second, pid, doc['id'], 1, jobs)
            assert cancelled['progress']['state'] == 'interrupted'
            assert cancelled['scenes'][0]['parse_status'] == 'pending'
        await jobs.shutdown()
    asyncio.run(scenario())
    result = client.get(f"{root}/{doc['id']}").json()
    assert len(result['scenes']) == 1 and result['revision'] == 2


# 用例：删除差异未明确复核时不能直接确认新版本。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_deletion_needs_explicit_review(client):
    root, old = setup(client)
    root, new = setup(client, old, '1 内 日 车内\n晚来拿着手机。')
    row = new['scenes'][0]
    row.update(match_status='new', previous_scene_id=None, change_reviewed=True)
    saved = client.put(f"{root}/{new['id']}", json={'revision': new['revision'], 'scenes': [row]}).json()
    rejected = client.post(f"{root}/{new['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True})
    assert rejected.status_code == 422 and '直接确认本版' in rejected.json()['detail']
    saved = client.put(f"{root}/{new['id']}", json={'revision': saved['revision'], 'scenes': saved['scenes'], 'deleted_reviewed': True}).json()
    assert client.post(f"{root}/{new['id']}/confirm", json={'revision': saved['revision'], 'accept_missing': True}).status_code == 200
