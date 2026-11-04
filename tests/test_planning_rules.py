# 测试职责：直接验证任务依赖、日期约束和检查项覆盖等纯规则，不依赖HTTP或模型。
import pytest
from backend.common.errors import BusinessError
from backend.schemas.planning import TaskData, Settings
from backend.tools.planning import check_tasks, check_coverage


# 用途：通过TaskData补全任务默认值，便于直接测试纯业务规则。
# 参数：key 同时作为任务ID和默认标题，values 为其他字段；返回JSON形式任务字典。
def entry(key, **values):
    return {'id': key, **TaskData(title=key, **values).model_dump(mode='json')}


# 用例：任务依赖缺失、自依赖、循环或重复时拒绝通过检查。
# 返回：无；使用断言或预期异常检查上述行为。
def test_cycle_missing_and_duplicate_dependencies():
    for tasks in [
        [entry('a', details={'dependencies': [{'task_id': 'x'}]})],
        [entry('a', details={'dependencies': [{'task_id': 'a'}]})],
        [entry('a', details={'dependencies': [{'task_id': 'b'}]}), entry('b', details={'dependencies': [{'task_id': 'a'}]})],
        [entry('a'), entry('b', details={'dependencies': [{'task_id': 'a'}, {'task_id': 'a'}]})]]:
        with pytest.raises(BusinessError):
            check_tasks(tasks, {})


# 用例：硬期限不满足时给出警告，已完成任务不再报逾期。
# 返回：无；使用断言或预期异常检查上述行为。
def test_constraint_warnings_and_completed_overdue():
    t = entry('a', planned_end='2026-11-06', details={'constraints': [
        {'kind': 'relative_to_milestone', 'milestone': 'shoot_start', 'offset_days': -1,
         'strength': 'hard', 'confirmation': 'confirmed', 'source': '制片确认'}]})
    warnings = check_tasks([t], {'shoot_start': '2026-11-05'})
    assert any('硬期限' in w['message'] for w in warnings)
    done = entry('b', planned_end='2000-01-01', status='completed')
    assert check_tasks([done], {}) == []


# 用例：覆盖结果必须包含全部检查项，且任务引用真实有效。
# 返回：无；使用断言或预期异常检查上述行为。
def test_coverage_requires_all_checks_and_real_tasks():
    framework = [{'id': 'returns'}]
    for coverage in [[], [{'check_id': 'returns', 'status': 'addressed', 'task_refs': []}],
                     [{'check_id': 'returns', 'status': 'unknown', 'task_refs': ['foreign']}]]:
        with pytest.raises(BusinessError):
            check_coverage({'coverage': coverage}, framework, {'a'})


# 用例：日期倒置及缺乏确认依据的约束无法通过Schema校验。
# 返回：无；使用断言或预期异常检查上述行为。
def test_invalid_schema_dates_and_constraints():
    with pytest.raises(ValueError):
        Settings(shoot_start='2026-11-10', shoot_end='2026-11-01')
    with pytest.raises(ValueError):
        TaskData(title='x', planned_start='2026-11-10', planned_end='2026-11-01')
    with pytest.raises(ValueError):
        TaskData(title='x', details={'constraints': [{'kind': 'finish_by', 'date': '2026-11-05', 'confirmation': 'confirmed'}]})


# 用例：后续任务早于前置任务完成或里程碑未确定时给出警告。
# 返回：无；使用断言或预期异常检查上述行为。
def test_dependency_due_before_predecessor_and_unknown_anchor_warn():
    tasks = [entry('a', planned_end='2026-11-09'), entry('b', planned_end='2026-11-08', details={
        'dependencies': [{'task_id': 'a'}],
        'constraints': [{'kind': 'relative_to_milestone', 'milestone': 'close_date'}]})]
    messages = [w['message'] for w in check_tasks(tasks, {})]
    assert any('完成日期早于前置' in m for m in messages)
    assert any('节点日期未确定' in m for m in messages)
