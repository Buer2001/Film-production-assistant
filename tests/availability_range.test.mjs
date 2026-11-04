import test from 'node:test';
import assert from 'node:assert/strict';
import { buildWeek } from '../frontend/src/features/preparation/availability.js';

test('双周覆盖次周任务，人员资源通过相同任务ID关联', () => {
  const tasks = [{ id: 't1', status: 'todo', details: { person_ids: ['p1'], resource_refs: [{ record_id: 'r1' }], usage_period: { start_date: '2026-11-12', end_date: '2026-11-12' } } }];
  for (const kind of ['people', 'resources']) {
    const board = buildWeek({ date: '2026-11-04', range: 'fortnight', kind, people: [{ id: 'p1' }], resources: [{ id: 'r1', data: {} }], tasks });
    assert.equal(board.days.length, 14);
    assert.equal(board.rows[0].cells.find(c => c.date === '2026-11-12').allocations[0].task.id, 't1');
  }
});
test('月视图覆盖完整自然月，正确处理闰年和周几', () => {
  const board = buildWeek({ date: '2028-02-29', range: 'month', kind: 'people' });
  assert.equal(board.start, '2028-02-01');
  assert.equal(board.days.length, 29);
  assert.equal(board.days[0].weekday, '周二');
  assert.equal(board.days.at(-1).date, '2028-02-29');
});
