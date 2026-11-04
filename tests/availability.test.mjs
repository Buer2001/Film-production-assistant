// 纯前端档期规则：日期边界、真实占用、关联完整性和输入不可变性。
import test from 'node:test';
import assert from 'node:assert/strict';
import { todayKey, addDays, periodLabel, buildWeek } from '../frontend/src/features/preparation/availability.js';

const period = (start_date = '2026-11-02', end_date = start_date, start_time, end_time) => ({ start_date, end_date, ...(start_time ? { start_time, end_time } : {}) });
const person = availability => ({ id: 'p', name: '小王', department: '摄影', availability });
const task = (id, usage_period, extra = {}) => ({ id, status: 'todo', details: { person_ids: ['p'], usage_period, ...extra } });
const week = (availability = [], tasks = []) => buildWeek({ date: '2026-11-02', kind: 'people', people: [person(availability)], tasks });

// 已有稳定人员关联后，历史手填姓名仅作资料保留，不应永远要求重复关联。
test('已关联人员允许保留历史手填姓名，不产生无效待补提示', () => {
  const result = week([], [task('a', period(), { assignees: ['历史姓名'], person_ids: ['p'] })]);
  assert.deepEqual(result.incomplete, []);
});

test('日期工具和跨年周使用自然日，今天取本机日期', () => {
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(buildWeek({ date: '2027-01-01', kind: 'people' }).start, '2026-12-28');
  const now = new Date();
  assert.equal(todayKey(), `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`);
  const days = week().days;
  assert.equal(days.length, 7); assert.equal(days[0].weekday, '周一'); assert.equal(days[0].label, '11/2');
  assert.match(periodLabel(period()), /全天/);
});
test('全天包含末日，多日时刻在当日裁剪，完成保留取消跳过', () => {
  const all = task('a', period('2026-11-02', '2026-11-03'));
  const continuous = task('b', period('2026-11-02', '2026-11-04', '18:00', '09:00'));
  const done = { ...task('done', period()), status: 'completed' };
  const cancelled = { ...task('cancel', null), status: 'cancelled' };
  const result = week([], [all, continuous, done, cancelled]);
  assert.equal(result.rows[0].cells[1].allocations.length, 2);
  assert.match(result.rows[0].cells[1].allocations[1].label, /全天/);
  assert.match(result.rows[0].cells[2].allocations[0].label, /09:00/);
  assert.equal(result.rows[0].cells[3].allocations.length, 0);
  assert.equal(result.rows[0].cells[0].allocations.length, 3);
  assert.deepEqual(result.incomplete, []);
});
test('未知、部分可用、明确不可用优先，实际占用才做校验', () => {
  assert.equal(week().rows[0].cells[0].state, 'unknown');
  const morning = { ...period('2026-11-02', '2026-11-02', '09:00', '12:00'), state: 'available' };
  const result = week([morning], [task('a', period('2026-11-02', '2026-11-02', '10:00', '11:00'))]);
  assert.equal(result.rows[0].cells[0].label, '部分可用');
  assert.equal(result.rows[0].cells[0].allocations[0].availabilityIssue, '');
  const blocked = week([{ ...period(), state: 'available' }, { ...morning, state: 'unavailable' }], [task('a', morning)]);
  assert.equal(blocked.rows[0].cells[0].label, '部分不可用');
  assert.match(blocked.rows[0].cells[0].allocations[0].availabilityIssue, /不可用/);
  assert.equal(week([{ ...period(), state: 'unavailable' }]).rows[0].cells[0].state, 'unavailable');
});
test('可用相邻区间拼接覆盖全天，任务半开重叠不含相邻端点', () => {
  const spans = [period('2026-11-02', '2026-11-02', '00:00', '12:00'), period('2026-11-02', '2026-11-03', '12:00', '00:00')];
  const tasks = [task('a', period('2026-11-02','2026-11-02','09:00','11:00')), task('b',period('2026-11-02','2026-11-02','10:00','12:00')),task('c',period('2026-11-02','2026-11-02','12:00','13:00'))];
  const cell = week(spans.map(x => ({...x,state:'available'})), tasks).rows[0].cells[0];
  assert.equal(cell.state, 'available'); assert.deepEqual(cell.allocations[0].overlapIds, ['b']); assert.deepEqual(cell.allocations[2].overlapIds, []);
});
test('缺失时间和手填失效关联只进补资料，不能按计划时间画块', () => {
  const tasks = [task('missing', null, {person_ids:[],assignees:['小王']}), task('invalid', {...period(),end_date:'bad'}, { person_ids:['gone'],resource_refs:[{name:'手填'}] })];
  tasks[0].planned_start = '2026-11-02'; tasks[0].planned_end = '2026-11-03';
  const result = week([],tasks);
  assert.equal(result.incomplete.length,2); assert.ok(result.incomplete[0].reasons.includes('尚未关联人员或资源'));
  assert.equal(result.rows[0].cells[0].allocations.length,0);
  assert.match(result.incomplete[1].reasons.join(''), /核对/);
});
test('资源按record_id去重关联，保留原对象且不修改输入', () => {
  const resource = { id:'r',data:{title:'摄影机',category:'equipment',preparation:{availability:[{...period(),state:'available'}]}} };
  const tasks = [task('a',period(),{person_ids:[],resource_refs:[{record_id:'r'},{record_id:'r'}]})];
  const input={ date:'2026-11-02',kind:'resources',resources:[resource],tasks };
  const before=JSON.stringify(input); const result=buildWeek(input);
  assert.equal(JSON.stringify(input),before); assert.equal(result.rows[0].entity,resource); assert.equal(result.rows[0].name,'摄影机'); assert.equal(result.rows[0].subtitle,'器材');
  assert.equal(result.rows[0].cells[0].allocations.length,1); assert.equal(result.rows[0].cells[0].allocations[0].task,tasks[0]); assert.deepEqual(result.incomplete,[]);
});

test('非法日期、半个时刻、时区时刻和倒置区间均不画占用', () => {
  const invalid = [
    {...period(),start_date:'2026-02-30'},
    {...period(),start_time:'09:00'},
    {...period(),start_time:'09:00Z',end_time:'10:00Z'},
    {...period(),start_time:'24:00',end_time:'25:00'},
    {...period(),start_time:'11:00',end_time:'10:00'},
  ];
  const result=week([],invalid.map((p,i)=>task(String(i),p)));
  assert.equal(result.incomplete.length,invalid.length);
  assert.ok(result.rows[0].cells.every(cell=>cell.allocations.length===0));
  assert.equal(addDays('2026-02-30',1),'');
  assert.match(periodLabel(null),/待补充/);
});

test('多日占用只校验各日交集，未知和部分可用明确提示', () => {
  const tasks=[task('a',period('2026-11-02','2026-11-03','18:00','09:00'))];
  const allowed={...period('2026-11-02','2026-11-03','18:00','00:00'),state:'available'};
  const result=week([allowed],tasks).rows[0].cells;
  assert.equal(result[0].allocations[0].availabilityIssue,'');
  assert.equal(result[1].allocations[0].availabilityIssue,'可用情况未知');
  assert.equal(result[1].allocations[0].label,'00:00–09:00');
  const partial=week([{...period('2026-11-02','2026-11-02','18:00','19:00'),state:'available'}],tasks);
  assert.match(partial.rows[0].cells[0].allocations[0].availabilityIssue,/部分可用/);
});
