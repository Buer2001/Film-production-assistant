from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from backend.common.errors import BusinessError
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.main import create_app
from backend.common.database.store import Change, Event, Project, Record
from backend.service.change import confirm


@pytest.fixture
def race(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'race.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '并发测试'}).json()['id']
        drafts = []
        for title in ['草稿甲', '草稿乙']:
            response = client.post(f'/api/projects/{pid}/changes', json={
                'base_revision': 0, 'reason': title, 'operations': [
                    {'kind': 'task', 'data': {'title': title}}]})
            assert response.status_code == 200
            drafts.append(response.json()['id'])
        yield client, pid, drafts


def compete(actions):
    barrier = Barrier(len(actions))

    def run(action):
        return action(barrier)

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return list(pool.map(run, actions))


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


def persisted(client, pid):
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        records = session.scalars(select(Record).where(Record.project_id == pid)).all()
        events = session.scalars(select(Event).where(Event.project_id == pid)).all()
        changes = session.scalars(select(Change).where(Change.project_id == pid)).all()
        return project.revision, [r.data['title'] for r in records], len(events), {c.id: c.status for c in changes}


def test_eight_confirmations_write_once(race):
    client, pid, (cid, _) = race
    results = compete([accept(client, pid, cid) for _ in range(8)])
    assert all(code == 409 or (code, status) == (200, 'confirmed') for code, status in results)
    assert any(code == 200 for code, _ in results)
    revision, records, events, changes = persisted(client, pid)
    assert (revision, records, events) == (1, ['草稿甲'], 1)
    assert changes[cid] == 'confirmed'


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


def test_different_drafts_same_revision(race):
    client, pid, drafts = race
    results = compete([accept(client, pid, cid) for cid in drafts])
    assert sorted(code for code, _ in results) == [200, 409]
    winner = next(i for i, (code, _) in enumerate(results) if code == 200)
    revision, records, events, changes = persisted(client, pid)
    assert (revision, records, events) == (1, [['草稿甲', '草稿乙'][winner]], 1)
    assert changes[drafts[winner]] == 'confirmed'
    assert changes[drafts[1 - winner]] == 'pending'
