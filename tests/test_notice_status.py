from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def day(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'notice.db'}")) as client:
        pid = client.post('/api/projects', json={'name': '通告测试'}).json()['id']
        apply(client, pid, [{'kind': 'scene', 'data': {'title': '礼堂场次'}}])
        scene = client.get(f'/api/projects/{pid}').json()['records'][0]['id']
        apply(client, pid, [
            {'kind': 'schedule', 'data': {'title': '礼堂拍摄', 'date': '2026-02-06', 'scene_ids': [scene]}},
            {'kind': 'task', 'data': {'title': '确认礼堂', 'scene_ids': [scene]}},
            {'kind': 'requirement', 'data': {'title': '导演要求', 'scene_ids': [scene]}}])
        response = client.post(f'/api/projects/{pid}/notices', json={'date': '2026-02-06', 'base_revision': 2})
        assert response.status_code == 200
        yield client, pid, response.json()['snapshot']


def apply(client, pid, operations):
    revision = client.get(f'/api/projects/{pid}').json()['revision']
    draft = client.post(f'/api/projects/{pid}/changes', json={
        'base_revision': revision, 'reason': '测试调整', 'operations': operations})
    assert draft.status_code == 200, draft.text
    response = client.post(f'/api/projects/{pid}/changes/{draft.json()["id"]}/confirm')
    assert response.status_code == 200, response.text


def status(day):
    client, pid, snapshot = day
    notice = client.get(f'/api/projects/{pid}').json()['notices'][0]
    assert notice['snapshot'] == snapshot
    return notice


def test_unrelated_changes_remain_valid(day):
    client, pid, snapshot = day
    scene = snapshot['records'][0]
    apply(client, pid, [
        {'kind': 'scene', 'id': scene['id'], 'data': {'title': '改场次标题'}},
        {'kind': 'schedule', 'data': {'title': '次日拍摄', 'date': '2026-02-07'}},
        {'kind': 'task', 'data': {'title': '无关筹备'}},
        {'kind': 'expense', 'data': {'title': '车费', 'category': '预算', 'amount': '20'}}])
    assert status(day)['stale'] is False
    assert status(day)['reasons'] == []


@pytest.mark.parametrize('kind,field,value', [
    ('schedule', 'minutes', 120), ('schedule', 'date', '2026-02-07'),
    ('task', 'status', '已确认'), ('requirement', 'notes', '需要雨景'),
    ('task', 'title', '新标题'), ('task', 'date', '2026-02-05'),
    ('task', 'scene_ids', [])])
def test_relevant_change_and_restore(day, kind, field, value):
    client, pid, snapshot = day
    original = next(r for r in snapshot['records'] if r['kind'] == kind)
    changed = deepcopy(original)
    changed['data'][field] = value
    apply(client, pid, [changed])
    assert status(day)['stale'] is True
    assert status(day)['reasons']
    if field == 'status':
        assert '状态由 待确认 变为 已确认' in status(day)['reasons'][0]
    apply(client, pid, [original])
    assert status(day)['stale'] is False
    assert status(day)['reasons'] == []


@pytest.mark.parametrize('kind', ['schedule', 'task', 'requirement'])
def test_new_relevant_record(day, kind):
    client, pid, snapshot = day
    scene = snapshot['schedule'][0]['data']['scene_ids'][0]
    apply(client, pid, [{'kind': kind, 'data': {
        'title': '新增记录', 'date': '2026-02-06', 'scene_ids': [scene]}}])
    assert status(day)['stale'] is True
    assert '新增' in status(day)['reasons'][0]


@pytest.mark.parametrize('kind', ['schedule', 'task', 'requirement'])
def test_deleted_relevant_record(day, kind):
    client, pid, snapshot = day
    record = next(r for r in snapshot['records'] if r['kind'] == kind)
    apply(client, pid, [{'kind': kind, 'id': record['id'], 'delete': True}])
    assert status(day)['stale'] is True
    assert '删除' in status(day)['reasons'][0]


def test_scene_deletion_alone_does_not_affect_status(day):
    from types import SimpleNamespace
    from backend.tools.notice import notice_status

    snapshot = day[2]
    records = [r for r in snapshot['records'] if r['kind'] != 'scene']
    # 接口禁止删除仍被引用的场次；纯函数单独覆盖通告的判定规则。
    assert notice_status(SimpleNamespace(date='2026-02-06', snapshot=snapshot), records) == {
        'stale': False, 'reasons': []}
