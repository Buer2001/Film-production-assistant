# 测试职责：验证V3人员资源接口、Schema边界、事件记录和增量迁移兼容性。
"""在临时数据库验证人员引用、版本和资源落实兼容契约。"""
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from backend.main import create_app


# 用例：可用日期区间的非法边界和值不能通过校验。
# 返回：无；使用断言或预期异常检查上述行为。
def test_period_validation():
    from backend.schemas.availability import UsagePeriod
    with pytest.raises(ValidationError):
        UsagePeriod(start_date='2026-11-03', end_date='2026-11-02')
    with pytest.raises(ValidationError):
        UsagePeriod(start_date='2026-11-03', end_date='2026-11-03', start_time='10:00')


# 用例：人员资料和资源筹备可共同使用，已引用人员受保护且跨项目引用被拒绝。
# 参数：tmp_path 为测试专用临时目录。
# 返回：无；使用断言或预期异常检查上述行为。
def test_people_resource_compatibility(tmp_path):
    with TestClient(create_app(f'sqlite:///{tmp_path / "v3.db"}')) as c:
        pid = c.post('/api/projects', json={'name': '筹备'}).json()['id']
        url = f'/api/projects/{pid}'
        result = c.post(url + '/people', json={'revision': 0, 'person': {'name': '摄影'}})
        assert result.status_code == 200, result.text
        person = result.json()['people'][0]
        prep = {'status': 'confirmed', 'contact_person_id': person['id']}
        result = c.post(url + '/resources', json={'revision': 1, 'resource': {'title': '摄影机', 'preparation': prep}})
        assert result.status_code == 200, result.text
        rid = result.json()['resources'][0]['id']
        result = c.put(url + f'/resources/{rid}', json={'revision': 2, 'resource': {'title': '改名'}})
        assert result.status_code == 200, result.text
        assert result.json()['resources'][0]['data']['preparation']['status'] == 'confirmed'
        assert c.delete(url + f'/people/{person["id"]}?revision=3').status_code == 422
        other = c.post('/api/projects', json={'name': '其他'}).json()['id']
        assert c.post(f'/api/projects/{other}/resources', json={'revision': 0, 'resource': {'title': '伪造', 'preparation': prep}}).status_code == 422

# 用例：人员引用和版本检查保护已关联资料，改名保持稳定ID。
# 参数：tmp_path 为测试专用临时目录；reference 为待验证的引用位置。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('reference', ['formal', 'planning_draft', 'resource_draft'])
def test_people_reference_guards_and_revision(tmp_path, reference):
    from backend.models.planning import ProjectPlan, ProjectTask
    from backend.models.change import Change
    with TestClient(create_app(f'sqlite:///{tmp_path / "guard.db"}')) as c:
        pid = c.post('/api/projects', json={'name': '引用保护'}).json()['id']
        url = f'/api/projects/{pid}'
        data = c.post(url + '/people', json={'revision': 0, 'person': {'name': '小王'}}).json()
        person_id = data['people'][0]['id']
        assert c.put(url + '/people/' + person_id, json={'revision': 0, 'person': {'name': '覆盖'}}).status_code == 409
        renamed = c.put(url + '/people/' + person_id, json={'revision': 1, 'person': {'name': '王老师'}})
        assert renamed.json()['people'][0]['id'] == person_id
        with c.app.state.sessions() as s:
            if reference == 'resource_draft':
                s.add(Change(project_id=pid, base_revision=2, reason='待确认联系人', operations=[{'kind': 'resource', 'data': {'title': '场地', 'preparation': {'contact_person_id': person_id}}}], before=[None]))
            else:
                plan = ProjectPlan(project_id=pid)
                s.add(plan); s.flush()
                if reference == 'formal':
                    s.add(ProjectTask(plan_id=plan.id, title='到场', details={'person_ids': [person_id]}))
                else:
                    plan.draft = {'status': 'pending', 'result': {'operations': [{'action': 'update', 'changes': {'details': {'person_ids': [person_id]}}}]}}
            s.commit()
        assert c.delete(url + f'/people/{person_id}?revision=2').status_code == 422
        assert c.get(url + '/people').json()['revision'] == 2
        assert c.get(url + '/people').json()['people'][0]['name'] == '王老师'


# 用例：资源专属筹备字段不扩散到其他记录类型。
# 返回：无；使用断言或预期异常检查上述行为。
def test_resource_schema_does_not_expand_other_record_kinds():
    from backend.schemas.record import Operation
    with pytest.raises(ValidationError):
        Operation(kind='scene', data={'title': '场次', 'preparation': {'status': 'confirmed'}})
    op = Operation(kind='resource', data={'title': '器材'})
    assert 'preparation' not in op.data.model_fields_set


# 用例：未引用人员允许删除，并记录包含原资料的变更事件。
# 参数：tmp_path 为测试专用临时目录。
# 返回：无；使用断言或预期异常检查上述行为。
def test_unreferenced_person_delete_and_event(tmp_path):
    from sqlalchemy import select
    from backend.models.event import Event
    with TestClient(create_app(f'sqlite:///{tmp_path / "delete.db"}')) as c:
        pid = c.post('/api/projects', json={'name': '删除'}).json()['id']
        url = f'/api/projects/{pid}/people'
        person_id = c.post(url, json={'revision': 0, 'person': {'name': '小李'}}).json()['people'][0]['id']
        result = c.delete(url + f'/{person_id}?revision=1')
        assert result.json() == {'revision': 2, 'people': []}
        with c.app.state.sessions() as s:
            events = s.scalars(select(Event).where(Event.project_id == pid, Event.type == 'person')).all()
            assert len(events) == 2
            assert events[-1].data['before']['id'] == person_id

# 用例：通用变更保留资源筹备事实，拒绝伪造联系人引用。
# 参数：tmp_path 为测试专用临时目录。
# 返回：无；使用断言或预期异常检查上述行为。
def test_generic_change_preserves_resource_preparation_and_rejects_forged_contact(tmp_path):
    with TestClient(create_app(f'sqlite:///{tmp_path / "generic.db"}')) as c:
        pid = c.post('/api/projects', json={'name': '兼容'}).json()['id']
        root = f'/api/projects/{pid}'
        resource = c.post(root + '/resources', json={'revision': 0, 'resource': {'title': '设备', 'preparation': {'status': 'confirmed', 'cost_status': 'free'}}}).json()['resources'][0]
        change = {'base_revision': 1, 'reason': '旧调用保存', 'operations': [{'kind': 'resource', 'id': resource['id'], 'data': {'title': '设备改名'}}]}
        draft = c.post(root + '/changes', json=change)
        assert draft.status_code == 200, draft.text
        assert c.post(root + '/changes/' + draft.json()['id'] + '/confirm').status_code == 200
        saved = c.get(root + '/resources').json()['resources'][0]
        assert saved['data']['preparation']['status'] == 'confirmed'
        assert saved['data']['preparation']['cost_status'] == 'free'
        change['base_revision'] = 2
        change['operations'][0]['data']['preparation'] = {'contact_person_id': 'forged'}
        assert c.post(root + '/changes', json=change).status_code == 422


# 用例：筹备表迁移可重复执行，并保留既有项目数据。
# 参数：tmp_path 为测试专用临时目录。
# 返回：无；使用断言或预期异常检查上述行为。
def test_preparation_migration_is_incremental_and_repeatable(tmp_path):
    from backend.common.database.store import database
    from backend.common.database.migrations.preparation_v3 import upgrade
    from backend.models.project import Project
    engine, sessions = database(f'sqlite:///{tmp_path / "migration.db"}')
    try:
        with sessions() as s:
            p = Project(name='保留旧库'); s.add(p); s.commit(); pid = p.id
        upgrade(engine); upgrade(engine)
        with sessions() as s:
            assert s.get(Project, pid).name == '保留旧库'
    finally:
        engine.dispose()

# 用例：含糊费用状态和超出上限的筹备数据无法通过校验。
# 参数：preparation 为待校验的筹备字段。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('preparation', [
    {'cost_status': 'free', 'cost_amount': '1'},
    {'cost_status': 'unknown', 'cost_amount': '0'},
    {'cost_status': 'quoted'},
    {'cost_status': 'confirmed'},
    {'contact_name': '名' * 201},
    {'availability': [{'start_date': '2030-01-01', 'end_date': '2030-01-01', 'state': 'available'}] * 101},
])
def test_preparation_rejects_ambiguous_cost_and_oversized_data(preparation):
    from backend.schemas.record import Preparation
    with pytest.raises(ValidationError):
        Preparation(**preparation)


# 用例：明确填写的费用事实可以通过筹备Schema校验。
# 参数：preparation 为待校验的筹备字段。
# 返回：无；使用断言或预期异常检查上述行为。
@pytest.mark.parametrize('preparation', [
    {'cost_status': 'unknown'}, {'cost_status': 'free'},
    {'cost_status': 'free', 'cost_amount': '0'},
    {'cost_status': 'quoted', 'cost_amount': '0'},
    {'cost_status': 'confirmed', 'cost_amount': '120.50'},
])
def test_preparation_accepts_explicit_cost_facts(preparation):
    from backend.schemas.record import Preparation
    assert Preparation(**preparation).cost_status == preparation['cost_status']
