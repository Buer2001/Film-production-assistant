# 测试职责：验证通告快照的有效性判断；历史任务通过测试数据模拟，不重开旧写接口。
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


# 用途：创建含场次、日程和历史任务的测试项目，并生成固定日期通告。
# 参数：tmp_path 为临时数据库目录；产出客户端、项目ID及原通告快照。
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


# 用途：在测试数据库中直接写入历史记录，模拟升级前仍存在的数据。
# 参数：client 为客户端，pid 为项目ID，operations 为变更操作；返回：无。
# 副作用：推进项目版本并提交测试事务；该辅助函数不是重新开放旧业务接口。
def apply(client, pid, operations):
    # 旧task写入已经关闭；这里直接模拟升级前的历史数据及历史变更，
    # 专门验证旧通告快照仍可读取比较，不能借测试重新开放旧任务接口。
    from backend.models.project import Project
    from backend.schemas.record import Item
    from backend.dao.record import apply_operation
    with client.app.state.sessions() as session:
        for operation in operations:
            value = {**operation}
            if not value.get('delete'):
                value['data'] = Item.model_validate(value['data']).model_dump(mode='json')
            apply_operation(session, pid, value)
        session.get(Project, pid).revision += 1
        session.commit()


# 用途：重新读取通告，先确认原快照未被修改，再返回最新通告状态。
# 参数：day 为通告测试夹具；返回通告字典，快照被修改时断言失败。
def status(day):
    client, pid, snapshot = day
    notice = client.get(f'/api/projects/{pid}').json()['notices'][0]
    assert notice['snapshot'] == snapshot
    return notice


# 用例：无关日期、记录或仅改场次标题不会使既有通告失效。
# 参数：day 为包含客户端、项目和原通告快照的夹具。
# 返回：无；使用断言或预期异常检查上述行为。
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


# 用例：相关字段变化使通告失效，恢复原值后重新有效且保留原快照。
# 参数：day 为包含客户端、项目和原通告快照的夹具；kind 为参数化测试的场景类型；field 为预期字段路径；value 为参数化字段值。
# 返回：无；使用断言或预期异常检查上述行为。
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


# 用例：新增与通告有关的记录时标记失效并给出新增原因。
# 参数：day 为包含客户端、项目和原通告快照的夹具；kind 为参数化测试的场景类型。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('kind', ['schedule', 'task', 'requirement'])
def test_new_relevant_record(day, kind):
    client, pid, snapshot = day
    scene = snapshot['schedule'][0]['data']['scene_ids'][0]
    apply(client, pid, [{'kind': kind, 'data': {
        'title': '新增记录', 'date': '2026-02-06', 'scene_ids': [scene]}}])
    assert status(day)['stale'] is True
    assert '新增' in status(day)['reasons'][0]


# 用例：删除通告引用的记录时标记失效并给出删除原因。
# 参数：day 为包含客户端、项目和原通告快照的夹具；kind 为参数化测试的场景类型。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('kind', ['schedule', 'task', 'requirement'])
def test_deleted_relevant_record(day, kind):
    client, pid, snapshot = day
    record = next(r for r in snapshot['records'] if r['kind'] == kind)
    apply(client, pid, [{'kind': kind, 'id': record['id'], 'delete': True}])
    assert status(day)['stale'] is True
    assert '删除' in status(day)['reasons'][0]


# 用例：单独删除场次不影响仅依赖相关业务记录的通告状态。
# 参数：day 为包含客户端、项目和原通告快照的夹具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_scene_deletion_alone_does_not_affect_status(day):
    from types import SimpleNamespace
    from backend.tools.notice import notice_status

    snapshot = day[2]
    records = [r for r in snapshot['records'] if r['kind'] != 'scene']
    # 接口禁止删除仍被引用的场次；纯函数单独覆盖通告的判定规则。
    assert notice_status(SimpleNamespace(date='2026-02-06', snapshot=snapshot), records) == {
        'stale': False, 'reasons': []}
