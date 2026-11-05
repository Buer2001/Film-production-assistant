// 测试职责：直接验证制片助手草稿的分组、差异、分级和漏排文案，不启动浏览器或后端。
// 执行方式：在项目目录运行 node --test tests/agent_draft.test.mjs。
import test from 'node:test';
import assert from 'node:assert/strict';
import { groupOperations, changedFields, operationTitle, groupIssues, uncoveredText }
  from '../frontend/src/features/agent/agentDraft.js';

// 检查任务与拍摄安排分开成组，未知类型不会从界面消失。
test('按对象类型分组，未知类型归入项目任务', () => {
  const groups = groupOperations([
    { op_id: 'op-1', entity: 'project_task' },
    { op_id: 'op-2', entity: 'shooting_item' },
    { op_id: 'op-3', entity: 'unknown' },
  ]);
  assert.deepEqual(groups.project_task.map(op => op.op_id), ['op-1', 'op-3']);
  assert.deepEqual(groups.shooting_item.map(op => op.op_id), ['op-2']);
  assert.deepEqual(groupOperations(), { project_task: [], shooting_item: [] });
});

// 只列出真正变化的字段，缺失原值时也算变化，便于展示新增内容。
test('差异字段只保留变化项，缺原值时显示为新值', () => {
  const fields = changedFields({
    action: 'update',
    patch: { title: '布光', start_at: '2026-11-10T10:00', notes: '' },
    before: { title: '布光', start_at: '2026-11-10T09:00', notes: '' },
  });
  assert.deepEqual(fields.map(field => field.key), ['start_at']);
  const added = changedFields({ action: 'add', patch: { title: '结清尾款' } });
  assert.deepEqual(added, [{ key: 'title', before: undefined, after: '结清尾款' }]);
});

// 标题优先取新值，其次原值，最后回落到编号，保证每行都能识别。
test('操作标题按新值、原值、编号顺序回落', () => {
  assert.equal(operationTitle({ patch: { title: '新标题' }, before: { title: '旧标题' } }), '新标题');
  assert.equal(operationTitle({ patch: {}, before: { title: '旧标题' } }), '旧标题');
  assert.equal(operationTitle({ action: 'cancel', target_id: 't-9' }), 't-9');
  assert.equal(operationTitle({ action: 'add', temp_id: 'tmp-1' }), 'tmp-1');
});

// 检查结果按级别分组；缺级别或未知级别按缺口处理，不当成通过。
test('检查结果按级别分组，未知级别记为缺口', () => {
  const groups = groupIssues({ issues: [
    { code: 'task_invalid', level: 'block', message: 'x' },
    { code: 'person_overlap', level: 'conflict', message: 'y' },
    { code: 'due_unknown' },
    { code: 'mystery', level: 'other', message: 'z' },
  ] });
  assert.equal(groups.block.length, 1);
  assert.equal(groups.conflict.length, 1);
  assert.deepEqual(groups.gap.map(issue => issue.code), ['due_unknown', 'mystery']);
  assert.deepEqual(groupIssues(null), { block: [], conflict: [], gap: [] });
});

// 未排场次拼成一行，带场地时补充在括号里。
test('未排场次生成可读文字', () => {
  assert.equal(uncoveredText([{ scene_number: '3', location: '教室' }, { scene_number: '7' }]),
    '场次 3（教室）、场次 7');
  assert.equal(uncoveredText([]), '');
});
