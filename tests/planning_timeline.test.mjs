// 测试职责：直接验证日历坐标、部门分组和草稿预览的纯函数，不启动浏览器或后端。
// 执行方式：在项目目录运行 node --test tests/planning_timeline.test.mjs。
import test from 'node:test';
import assert from 'node:assert/strict';
import { makeAxis, taskPosition, departmentGroups, previewOperations, departmentTargets } from '../frontend/src/features/planning/timeline.js';

// 参数：id 为任务键，start/end 为日期字符串或null，department 为主责部门。
// 返回：符合时间轴输入结构的行对象，用于构造跨日、跨月及无日期测试。
const row = (id, start, end, department = '') => ({ key: id, task: { id, title: id, planned_start: start, planned_end: end, details: { department } } });

// 检查日期轴包含闰日，任务跨度包含起止两天，避免毫秒换算导致日期偏移。
test('日历使用日期计算，包含闰日和末日，不受时区影响', () => {
  const rows = [row('a', '2024-02-28', '2024-03-01')];
  const axis = makeAxis(rows, 'day', {});
  assert.ok(axis.columns.some(c => c.start === '2024-02-29'));
  const p = taskPosition(rows[0].task, axis);
  assert.equal(p.span, 3);
  assert.equal(axis.columns[p.start].start, '2024-02-28');
});

// 检查周/月坐标按自然日期对齐；只有一端日期的任务不伪造完整区间。
test('周从周一开始，月跨年按自然月，不把未定日期画成一天', () => {
  const rows = [row('a', '2026-12-28', '2027-01-05')];
  const week = makeAxis(rows, 'week', {});
  assert.equal(week.columns[0].start, '2026-12-28');
  const month = makeAxis(rows, 'month', {});
  assert.deepEqual(month.columns.map(c => c.start), ['2026-12-01', '2027-01-01']);
  assert.equal(taskPosition(row('x', null, '2027-01-05').task, month), null);
});

// 检查主责部门决定分组，协作部门不复制任务，空部门进入待分配组。
test('部门分组不把工作类别当部门，不重复协作任务，组内日期有序', () => {
  const rows = [row('late', '2026-11-10', '2026-11-12', '摄影组'), row('unknown', null, null), row('early', '2026-11-02', '2026-11-03', '摄影组')];
  rows[0].task.details.collaborating_departments = ['灯光组'];
  const groups = departmentGroups(rows);
  assert.equal(groups.find(g => g.name === '摄影组').rows[0].key, 'early');
  assert.equal(groups.reduce((n, g) => n + g.rows.length, 0), 3);
  assert.ok(groups.some(g => g.name === '待分配部门'));
});

// 预览只合并建议变更；嵌套详情和原任务对象均需保留未修改内容。
test('草稿预览保留未修改字段，取消只显示建议，不改原任务', () => {
  const tasks = [row('a', '2026-11-02', '2026-11-03', '摄影组').task];
  tasks[0].details.assignees = ['张三'];
  const operations = [{ action: 'update', ref: 'a', changes: { details: { department: '制片组' } } }];
  const result = previewOperations(tasks, operations);
  assert.equal(result[0].task.details.department, '制片组');
  assert.deepEqual(result[0].task.details.assignees, ['张三']);
  assert.equal(tasks[0].details.department, '摄影组');
  assert.equal(previewOperations(tasks, [{ action: 'cancel', ref: 'a' }])[0].task.status, 'cancelled');
});

// 超长跨度应返回警告和空轴，避免大量列拖垮界面或静默截断数据。
test('异常日期跨度不创建无界列，也不悄悄截掉后续任务', () => {
  const axis = makeAxis([row('a', '1900-01-01', '2100-12-31')], 'day', {});
  assert.equal(axis.columns.length, 0);
  assert.ok(axis.warning);
});


// 先应用草稿预览，再选择空部门任务，因此人工清空、新增和取消均按预览状态判断。
test('部门补全只选择当前草稿空白任务，排除人工部门及取消项', () => {
  const tasks = [row('assigned', null, null, '人工部门').task, row('empty', null, null).task];
  tasks.forEach(t => { t.status = 'todo'; });
  assert.deepEqual(departmentTargets(tasks).map(r => r.key), ['empty']);
  const operations = [
    { action: 'update', ref: 'assigned', changes: { details: { department: '' } } },
    { action: 'cancel', ref: 'empty' },
    { action: 'add', ref: 'new', task: { title: '器材核对', status: 'todo', details: {} } },
  ];
  assert.deepEqual(departmentTargets(tasks, operations).map(r => r.key), ['new']);
});
