# 测试职责：验证日程任务、模型建议草稿、版本冲突、确认事务及正式剧本依据读取。
import json
import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


# 用途：创建使用临时SQLite数据库的测试应用，并由上下文管理应用生命周期。
# 参数：tmp_path 为pytest临时目录；存在 monkeypatch 参数时用于隔离草稿、日志或模型依赖。
# 产出：FastAPI TestClient；测试结束后退出客户端上下文，不连接正式数据库。
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DRAFT_DIR', str(tmp_path / 'drafts'))
    with TestClient(create_app(f'sqlite:///{tmp_path / "planning.db"}')) as c:
        yield c


# 用途：通过客户端创建隔离的测试项目。
# 参数：c/client 为测试客户端；返回：新项目ID及日程接口前缀。
def project(c):
    pid = c.post('/api/projects', json={'name': '日程测试'}).json()['id']
    return pid, f'/api/projects/{pid}/planning'


# 用途：通过任务接口按给定版本创建测试任务，失败时输出HTTP响应。
# 参数：c 为客户端，root 为日程路径，revision 为版本，title/data 为任务字段。
# 返回：保存后的日程响应字典。
def task(c, root, revision, title='清点器材', **data):
    response = c.post(root + '/tasks', json={'revision': revision, 'task': {'title': title, **data}})
    assert response.status_code == 200, response.text
    return response.json()


# 用例：人工任务和设置可保存，旧版本写入被拒绝，跨项目任务互相隔离。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_manual_tasks_settings_conflict_and_isolation(client):
    _, root = project(client)
    initial = client.get(root).json()
    assert initial['revision'] == 0 and initial['tasks'] == []
    saved = settings(client, root)
    assert saved['revision'] == 1
    data = task(client, root, 1, planned_end='2020-01-01')
    tid = data['tasks'][0]['id']
    assert data['tasks'][0]['overdue'] is True
    assert client.patch(root + '/tasks/' + tid, json={'revision': 1, 'changes': {'status': 'completed'}}).status_code == 409
    done = client.patch(root + '/tasks/' + tid, json={'revision': 2, 'changes': {'status': 'completed'}}).json()
    assert done['tasks'][0]['completed_at'] and not done['tasks'][0]['overdue']
    _, other = project(client)
    assert client.patch(other + '/tasks/' + tid, json={'revision': 0, 'changes': {'title': '越界'}}).status_code == 404
    assert client.get(root).json()['tasks'][0]['title'] == '清点器材'


# 用例：依赖环和不合法取消被拒绝，局部修改保留未提交字段。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_dependencies_cycles_cancellation_and_patch_preserves_fields(client):
    _, root = project(client)
    a = task(client, root, 0)['tasks'][0]['id']
    data = task(client, root, 1, '归还器材', details={'dependencies': [{'task_id': a}]})
    b = data['tasks'][1]['id']
    assert data['tasks'][1]['blocked']
    assert client.patch(root + '/tasks/' + a, json={'revision': 2, 'changes': {'details': {'dependencies': [{'task_id': b}]}}}).status_code == 422
    assert client.patch(root + '/tasks/' + a, json={'revision': 2, 'changes': {'status': 'cancelled'}}).status_code == 422
    changed = client.patch(root + '/tasks/' + b, json={'revision': 2, 'changes': {'title': '交还摄影器材'}})
    assert changed.status_code == 200, changed.text
    assert changed.json()['tasks'][1]['details']['dependencies'][0]['task_id'] == a
    assert client.patch(root + '/tasks/' + b, json={'revision': 3, 'changes': {'title': '   '}}).status_code == 422


# 用途：构造包含两项新增任务、依赖关系、待确认问题和检查覆盖的模拟计划。
# 参数：无；返回符合测试需要的建议字典，不执行模型调用。
def fake_result():
    from backend.ai.planning import checklist
    return {'operations': [
        {'action': 'add', 'ref': 'a', 'task': {'title': '清点器材', 'category': 'equipment'}},
        {'action': 'add', 'ref': 'b', 'task': {'title': '归还器材', 'phase': 'closing', 'details': {'dependencies': [{'task_id': 'a'}]}}}],
        'questions': ['请确认器材归还期限'],
        'coverage': [{'check_id': x['id'], 'status': 'unknown', 'reason': '需要制片确认', 'task_refs': []} for x in checklist()]}


# 用途：为新日程保存固定拍摄日期、收尾日期和项目背景。
# 参数：c 为客户端，root 为日程路径；返回更新后的日程响应字典。
def settings(c, root):
    response = c.put(root + '/settings', json={'revision': 0, 'settings': {
        'shoot_start': '2026-11-05', 'shoot_end': '2026-11-07', 'close_date': '2026-11-10', 'context': '租用器材'}})
    assert response.status_code == 200, response.text
    return response.json()


# 用途：替换模型chat方法，使其以submit_plan工具调用返回指定建议。
# 参数：monkeypatch 为替换工具，result 为建议数据；返回：无，不调用真实模型。
def mock_model(monkeypatch, result):
    from backend.ai.client import ModelClient
    async def chat(self, messages, tools):
        return {'tool_calls': [{'function': {'name': 'submit_plan', 'arguments': json.dumps(result)}}]}
    monkeypatch.setattr(ModelClient, 'chat', chat)


# 用例：生成只创建建议草稿，确认映射临时引用且可幂等重试。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_generate_confirm_id_mapping_idempotency_and_later_manual_change(client, monkeypatch):
    _, root = project(client); settings(client, root)
    mock_model(monkeypatch, fake_result())
    response = client.post(root + '/generate', json={'revision': 1, 'instruction': ''})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['tasks'] == [] and data['draft']['status'] == 'pending'
    request = {'revision': data['revision'], 'draft_id': data['draft']['id']}
    done = client.post(root + '/draft/confirm', json=request)
    assert done.status_code == 200, done.text
    tasks = done.json()['tasks']
    assert tasks[1]['details']['dependencies'][0]['task_id'] == tasks[0]['id']
    task(client, root, done.json()['revision'], '补充任务')
    again = client.post(root + '/draft/confirm', json=request)
    assert again.status_code == 200 and len(again.json()['tasks']) == 3


# 用例：覆盖检查失败或生成期间版本变化时，保留已有任务和草稿。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_bad_coverage_and_stale_generation_preserve_state(client, monkeypatch):
    _, root = project(client); settings(client, root)
    mock_model(monkeypatch, fake_result())
    good = client.post(root + '/generate', json={'revision': 1}).json()
    broken = fake_result(); broken['coverage'] = []
    mock_model(monkeypatch, broken)
    assert client.post(root + '/generate', json={'revision': good['revision']}).status_code == 422
    assert client.get(root).json()['draft']['id'] == good['draft']['id']
    from backend.ai.client import ModelClient
    async def slow(self, messages, tools):
        await asyncio.to_thread(task, client, root, good['revision'], '生成期间人工新增')
        return {'tool_calls': [{'function': {'name': 'submit_plan', 'arguments': json.dumps(fake_result())}}]}
    monkeypatch.setattr(ModelClient, 'chat', slow)
    assert client.post(root + '/generate', json={'revision': good['revision']}).status_code == 409
    assert client.get(root).json()['draft']['id'] == good['draft']['id']


# 用例：任务不得引用其他项目的剧本场次。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_cross_project_scene_ref_rejected(client):
    _, root = project(client)
    response = client.post(root + '/tasks', json={'revision': 0, 'task': {'title': '申请场地', 'details': {'scene_refs': [{'script_id': 'foreign', 'scene_id': 'foreign'}]}}})
    assert response.status_code == 422


# 用例：模型补充的约束保持待确认，不能直接成为已确认事实。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_model_cannot_mark_invented_constraints_confirmed(client, monkeypatch):
    _, root = project(client); settings(client, root)
    result = fake_result()
    result['operations'][0]['task']['details'] = {'constraints': [{'kind': 'finish_by', 'date': '2026-11-04', 'strength': 'hard', 'confirmation': 'confirmed', 'source': '模型编造'}]}
    mock_model(monkeypatch, result)
    response = client.post(root + '/generate', json={'revision': 1})
    assert response.status_code == 200, response.text
    constraint = response.json()['draft']['result']['operations'][0]['task']['details']['constraints'][0]
    assert constraint['confirmation'] == 'pending'


# 用例：确认失败完整回滚，并发重复确认不重复生成任务。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_confirm_rollback_and_real_concurrent_requests(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from backend.dao import planning as dao
    _, root = project(client); settings(client, root)
    mock_model(monkeypatch, fake_result())
    data = client.post(root + '/generate', json={'revision': 1}).json()
    request = {'revision': data['revision'], 'draft_id': data['draft']['id']}
    original = dao.write_task
    count = 0
    def broken(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError('模拟第二条写入失败')
        return original(*args, **kwargs)
    monkeypatch.setattr(dao, 'write_task', broken)
    assert client.post(root + '/draft/confirm', json=request).status_code == 500
    unchanged = client.get(root).json()
    assert unchanged['revision'] == data['revision'] and unchanged['tasks'] == []
    assert unchanged['draft']['status'] == 'pending'
    monkeypatch.setattr(dao, 'write_task', original)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(root + '/draft/confirm', json=request), range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert len(client.get(root).json()['tasks']) == 2


# 用例：草稿可编辑和丢弃，人工任务变化后旧草稿不能确认。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_draft_edit_discard_and_manual_changes_make_it_stale(client, monkeypatch):
    _, root = project(client); settings(client, root)
    mock_model(monkeypatch, fake_result())
    data = client.post(root + '/generate', json={'revision': 1}).json()
    result = data['draft']['result']; result['operations'][0]['task']['title'] = '核对摄影器材'
    edited = client.put(root + '/draft', json={'revision': data['revision'], 'draft_id': data['draft']['id'], 'result': result})
    assert edited.status_code == 200, edited.text
    data = edited.json()
    assert data['draft']['result']['operations'][0]['task']['title'] == '核对摄影器材'
    added = task(client, root, data['revision'], '人工新增')
    assert added['draft_stale'] is True
    request = {'revision': added['revision'], 'draft_id': data['draft']['id']}
    assert client.post(root + '/draft/confirm', json=request).status_code == 409
    discarded = client.request('DELETE', root + '/draft', json=request)
    assert discarded.status_code == 200 and len(discarded.json()['tasks']) == 1


# 用例：模型请求超时返回明确错误，已有任务和草稿保持原样。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_timeout_keeps_draft_and_tasks(client, monkeypatch):
    import httpx
    _, root = project(client); settings(client, root)
    mock_model(monkeypatch, fake_result())
    good = client.post(root + '/generate', json={'revision': 1}).json()
    from backend.ai.client import ModelClient
    async def timeout(*args, **kwargs):
        raise httpx.ReadTimeout('模拟超时')
    monkeypatch.setattr(ModelClient, 'chat', timeout)
    response = client.post(root + '/generate', json={'revision': good['revision']})
    assert response.status_code == 502
    assert client.get(root).json() == good


# 用例：生成依据已确认剧本，引用来源变化时拒绝保存过期建议。
# 参数：client 为测试应用客户端；monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_generation_uses_only_confirmed_script_and_rejects_source_change(client, monkeypatch):
    from backend.models.script import Script, SceneBreakdown
    from backend.ai.client import ModelClient
    pid, root = project(client); settings(client, root)
    with client.app.state.sessions() as session:
        script = Script(project_id=pid, version_number=1, title='剧本', content='1 内 日 教室', status='confirmed', revision=1)
        session.add(script); session.flush()
        scene = SceneBreakdown(script_id=script.id, sort_order=0, scene_number='1', location='教室', summary='交谈')
        session.add(scene); session.commit()
        sid = script.id
    async def chat(self, messages, tools):
        payload = json.loads(messages[-1]['content'])
        assert payload['breakdown'][0]['location'] == '教室'
        with client.app.state.sessions() as session:
            row = session.get(Script, sid); row.revision += 1; session.commit()
        return {'tool_calls': [{'function': {'name': 'submit_plan', 'arguments': json.dumps(fake_result())}}]}
    monkeypatch.setattr(ModelClient, 'chat', chat)
    assert client.post(root + '/generate', json={'revision': 1}).status_code == 409
    assert client.get(root).json()['draft'] is None


# 用例：重复运行计划表迁移不会丢失原有任务。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_migration_idempotent_preserves_tasks(client):
    from backend.common.database.migrations.planning_v2 import upgrade
    _, root = project(client)
    task(client, root, 0)
    with client.app.state.sessions() as session:
        engine = session.get_bind()
    upgrade(engine); upgrade(engine)
    assert client.get(root).json()['tasks'][0]['title'] == '清点器材'


# 用例：计算今日到期和临近到期，已完成任务不再显示到期警告。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_due_today_soon_and_completed_state(client):
    from datetime import timedelta
    from backend.tools.planning import today
    _, root = project(client)
    data = task(client, root, 0, planned_end=today().isoformat())
    assert data['tasks'][0]['due_state'] == 'today'
    data = task(client, root, 1, '临近事项', planned_end=(today() + timedelta(days=2)).isoformat())
    assert data['tasks'][1]['due_state'] == 'soon'
    key = data['tasks'][0]['id']
    done = client.patch(root + '/tasks/' + key, json={'revision': 2, 'changes': {'status': 'completed'}}).json()
    assert done['tasks'][0]['due_state'] is None


# 用途：创建两版已确认剧本及不同场次内容，供正式依据版本读取测试使用。
# 参数：client 为客户端，pid 为项目ID；返回两版剧本/场次的引用字典。
# 副作用：向测试数据库提交剧本和场次记录。
def evidence_fixture(client, pid):
    from backend.models.script import Script, SceneBreakdown
    with client.app.state.sessions() as session:
        first = Script(project_id=pid, version_number=1, title='依据剧本', version_label='初版',
                       content='1 内 日 教室\n小林拿起课本。', status='confirmed', revision=2)
        session.add(first); session.flush()
        scene = SceneBreakdown(script_id=first.id, sort_order=0, scene_number='1', location='教室',
            summary='小林拿起课本', details={'cast': [{'name': '小林', 'category': '主要角色'}],
            'action_props': [{'name': '课本', 'description': ''}]},
            evidence={'text': '1 内 日 教室\n小林拿起课本。', 'line_start': 1, 'line_end': 2})
        session.add(scene); session.flush()
        second = Script(project_id=pid, version_number=2, previous_script_id=first.id, title='新版剧本',
                        content='1 内 日 办公室\n小林拿起手机。', status='confirmed', revision=1)
        session.add(second); session.flush()
        other = SceneBreakdown(script_id=second.id, sort_order=0, scene_number='1', location='办公室')
        session.add(other); session.commit()
        return {'script_id': first.id, 'scene_id': scene.id}, {'script_id': second.id, 'scene_id': other.id}


# 用例：任务依据读取明确关联的正式剧本版本，不混入新版或未确认草稿。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_task_evidence_reads_linked_formal_version_not_latest_or_file_draft(client):
    from backend.tools.script.draft_store import DraftStore
    pid, root = project(client)
    ref, newer = evidence_fixture(client, pid)
    data = task(client, root, 0, '准备课本', details={'scene_refs': [ref]})
    tid = data['tasks'][0]['id']
    DraftStore().write(pid, ref['script_id'], {'id': ref['script_id'], 'project_id': pid,
        'scenes': [{'id': ref['scene_id'], 'summary': '未确认修改，禁止显示'}]})
    response = client.get(root + f'/tasks/{tid}/evidence', params=ref)
    assert response.status_code == 200, response.text
    evidence = response.json()
    assert evidence['script']['id'] == ref['script_id'] and evidence['script']['version_number'] == 1
    assert evidence['scene']['location'] == '教室'
    assert evidence['scene']['summary'] == '小林拿起课本'
    assert evidence['scene']['evidence']['line_start'] == 1
    assert '课本' in evidence['content'] and '未确认修改' not in response.text
    assert client.get(root).json()['revision'] == data['revision']
    assert client.get(root + f'/tasks/{tid}/evidence', params=newer).status_code == 404


# 用例：任务依据跨项目、已删除或未关联时明确拒绝，不猜测替代内容。
# 参数：client 为测试应用客户端。
# 返回：无；使用断言或预期异常检查上述行为。
def test_task_evidence_isolated_missing_and_unlinked_are_not_guessed(client):
    from backend.models.script import SceneBreakdown
    pid, root = project(client)
    ref, _ = evidence_fixture(client, pid)
    data = task(client, root, 0, details={'scene_refs': [ref]})
    tid = data['tasks'][0]['id']
    _, other = project(client)
    assert client.get(other + f'/tasks/{tid}/evidence', params=ref).status_code == 404
    assert client.get(root + '/tasks/missing/evidence', params=ref).status_code == 404
    with client.app.state.sessions() as session:
        session.delete(session.get(SceneBreakdown, ref['scene_id'])); session.commit()
    response = client.get(root + f'/tasks/{tid}/evidence', params=ref)
    assert response.status_code == 404 and '不存在' in response.json()['detail']
    assert client.get(root + f'/tasks/{tid}/evidence').status_code == 422
