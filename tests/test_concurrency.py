# 测试职责：使用独立数据库会话和线程屏障验证变更确认的并发一致性。
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from backend.common.errors import BusinessError
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.main import create_app
from backend.common.database.store import Change, Event, Project, Record
from backend.service.change import confirm


# 用途：构造共享基础版本的两份草稿，为并发确认提供测试数据。
# 参数：tmp_path 为临时目录；产出客户端、项目ID和草稿ID列表。
@pytest.fixture
def race(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'race.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '并发测试'}).json()['id']
        drafts = []
        for title in ['草稿甲', '草稿乙']:
            response = client.post(f'/api/projects/{pid}/changes', json={
                'base_revision': 0, 'reason': title, 'operations': [
                    {'kind': 'resource', 'data': {'title': title}}]})
            assert response.status_code == 200
            drafts.append(response.json()['id'])
        yield client, pid, drafts


# 用途：将一组操作在线程池中启动，并向每个操作传入同一个线程屏障。
# 参数：actions 为接收屏障的可调用列表；返回各操作的结果列表。
def compete(actions):
    barrier = Barrier(len(actions))

    def run(action):
        return action(barrier)

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


# 用途：构造在独立会话中预读草稿、等待并发屏障后确认的测试操作。
# 参数：client 为客户端，pid/cid 为项目和草稿ID；返回接收屏障的函数。
def accept(client, pid, cid):
    # 每个线程持有独立 session，并预读草稿以放大同一旧状态的竞争。
    def action(barrier):
        with client.app.state.sessions() as session:
            draft = session.get(Change, cid)
            assert draft.status == 'pending'
            barrier.wait(timeout=15)
            try:
                result = confirm(session, pid, cid)
                return 200, result['status']
            except BusinessError as exc:
                return exc.status_code, None
    return action


# 用途：直接读取数据库，核对并发请求后的真实持久化状态。
# 参数：client 为客户端，pid 为项目ID；返回版本、记录标题、事件数和草稿状态映射。
def persisted(client, pid):
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        records = session.scalars(select(Record).where(Record.project_id == pid)).all()
        events = session.scalars(select(Event).where(Event.project_id == pid)).all()
        changes = session.scalars(select(Change).where(Change.project_id == pid)).all()
        return project.revision, [r.data['title'] for r in records], len(events), {c.id: c.status for c in changes}


# 用例：八个并发确认请求最多产生一次正式写入和一次版本推进。
# 参数：race 为包含客户端、项目和两份草稿的并发测试夹具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_eight_confirmations_write_once(race):
    client, pid, (cid, _) = race
    results = compete([accept(client, pid, cid) for _ in range(8)])
    assert all(code == 409 or (code, status) == (200, 'confirmed') for code, status in results)
    assert any(code == 200 for code, _ in results)
    revision, records, events, changes = persisted(client, pid)
    assert (revision, records, events) == (1, ['草稿甲'], 1)
    assert changes[cid] == 'confirmed'


# 用例：同一草稿的确认和拒绝竞争时只允许一方成功，并保持数据一致。
# 参数：race 为包含客户端、项目和两份草稿的并发测试夹具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_confirm_competes_with_reject(race):
    client, pid, (cid, _) = race

    def reject(barrier):
        barrier.wait(timeout=15)
        response = client.post(f'/api/projects/{pid}/changes/{cid}/reject')
        return response.status_code, response.json().get('status')

    results = compete([accept(client, pid, cid), reject])
    assert sorted(code for code, _ in results) == [200, 409]
    revision, records, events, changes = persisted(client, pid)
    if changes[cid] == 'confirmed':
        assert (revision, records, events) == (1, ['草稿甲'], 1)
    else:
        assert changes[cid] == 'rejected'
        assert (revision, records, events) == (0, [], 0)


# 用例：相同基础版本的不同草稿并发确认时只允许一个成功。
# 参数：race 为包含客户端、项目和两份草稿的并发测试夹具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_different_drafts_same_revision(race):
    client, pid, drafts = race
    results = compete([accept(client, pid, cid) for cid in drafts])
    assert sorted(code for code, _ in results) == [200, 409]
    winner = next(i for i, (code, _) in enumerate(results) if code == 200)
    revision, records, events, changes = persisted(client, pid)
    assert (revision, records, events) == (1, [['草稿甲', '草稿乙'][winner]], 1)
    assert changes[drafts[winner]] == 'confirmed'
    assert changes[drafts[1 - winner]] == 'pending'
