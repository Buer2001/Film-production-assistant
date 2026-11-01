import pytest
from backend.common.errors import BusinessError
from backend.schemas.planning import TaskData, Settings
from backend.tools.planning import check_tasks, check_coverage


def entry(key, **values):
    return {'id': key, **TaskData(title=key, **values).model_dump(mode='json')}


def test_cycle_missing_and_duplicate_dependencies():
    for tasks in [
        [entry('a', details={'dependencies': [{'task_id': 'x'}]})],
        [entry('a', details={'dependencies': [{'task_id': 'a'}]})],
        [entry('a', details={'dependencies': [{'task_id': 'b'}]}), entry('b', details={'dependencies': [{'task_id': 'a'}]})],
        [entry('a'), entry('b', details={'dependencies': [{'task_id': 'a'}, {'task_id': 'a'}]})]]:
        with pytest.raises(BusinessError):
            check_tasks(tasks, {})


def test_constraint_warnings_and_completed_overdue():
    t = entry('a', planned_end='2026-11-06', details={'constraints': [
        {'kind': 'relative_to_milestone', 'milestone': 'shoot_start', 'offset_days': -1,
         'strength': 'hard', 'confirmation': 'confirmed', 'source': '制片确认'}]})
    warnings = check_tasks([t], {'shoot_start': '2026-11-05'})
    assert any('硬期限' in w['message'] for w in warnings)
    done = entry('b', planned_end='2000-01-01', status='completed')
    assert check_tasks([done], {}) == []


def test_coverage_requires_all_checks_and_real_tasks():
    framework = [{'id': 'returns'}]
    for coverage in [[], [{'check_id': 'returns', 'status': 'addressed', 'task_refs': []}],
                     [{'check_id': 'returns', 'status': 'unknown', 'task_refs': ['foreign']}]]:
        with pytest.raises(BusinessError):
            check_coverage({'coverage': coverage}, framework, {'a'})


def test_invalid_schema_dates_and_constraints():
    with pytest.raises(ValueError):
        Settings(shoot_start='2026-11-10', shoot_end='2026-11-01')
    with pytest.raises(ValueError):
        TaskData(title='x', planned_start='2026-11-10', planned_end='2026-11-01')
    with pytest.raises(ValueError):
        TaskData(title='x', details={'constraints': [{'kind': 'finish_by', 'date': '2026-11-05', 'confirmation': 'confirmed'}]})


def test_dependency_due_before_predecessor_and_unknown_anchor_warn():
    tasks = [entry('a', planned_end='2026-11-09'), entry('b', planned_end='2026-11-08', details={
        'dependencies': [{'task_id': 'a'}],
        'constraints': [{'kind': 'relative_to_milestone', 'milestone': 'close_date'}]})]
    messages = [w['message'] for w in check_tasks(tasks, {})]
    assert any('完成日期早于前置' in m for m in messages)
    assert any('节点日期未确定' in m for m in messages)
