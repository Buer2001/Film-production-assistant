// 纯日期和展示投影：不改正式任务，不以假日期填补未知安排。
const DAY = 86400000;
export const dayNumber = value => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null;
  const ms = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === value ? ms / DAY : null;
};
const iso = day => new Date(day * DAY).toISOString().slice(0, 10);
const stamp = day => `${Number(iso(day).slice(5, 7))}/${Number(iso(day).slice(8, 10))}`;

export function makeAxis(rows, mode, settings = {}) {
  const dates = rows.flatMap(r => [r.task.planned_start, r.task.planned_end]);
  dates.push(settings.shoot_start, settings.shoot_end, settings.close_date);
  const days = dates.map(dayNumber).filter(x => x !== null);
  if (!days.length) return { columns: [], width: 0, warning: '日期尚未确定，填写日期后显示时间条。' };
  let start = Math.min(...days), last = Math.max(...days);
  if (mode === 'week') start -= (new Date(start * DAY).getUTCDay() + 6) % 7;
  if (mode === 'month') start = dayNumber(iso(start).slice(0, 8) + '01');
  const columns = [], cellWidth = mode === 'day' ? 56 : 112;
  let cursor = start;
  while (cursor <= last) {
    if (columns.length >= 600) return { columns: [], width: 0, warning: '当前日期跨度过大，请切换月视图、筛选任务或核对异常日期。' };
    let next = cursor + (mode === 'day' ? 1 : 7);
    if (mode === 'month') {
      const d = new Date(cursor * DAY);
      d.setUTCMonth(d.getUTCMonth() + 1);
      next = d.getTime() / DAY;
    }
    columns.push({ start: iso(cursor), end: iso(next - 1), day: cursor, next,
      label: mode === 'month' ? `${iso(cursor).slice(0, 4)}年${Number(iso(cursor).slice(5, 7))}月` : stamp(cursor),
      sub: mode === 'week' ? `— ${stamp(next - 1)}` : mode === 'day' ? ['日', '一', '二', '三', '四', '五', '六'][new Date(cursor * DAY).getUTCDay()] : '自然月',
      weekend: mode === 'day' && [0, 6].includes(new Date(cursor * DAY).getUTCDay()) });
    cursor = next;
  }
  return { columns, cellWidth, width: columns.length * cellWidth, start, end: cursor, warning: '' };
}

export function axisOffset(value, axis) {
  const day = dayNumber(value);
  if (day === null) return null;
  const i = axis.columns.findIndex(c => day >= c.day && day < c.next);
  if (i < 0) return null;
  const c = axis.columns[i];
  return (i + (day - c.day) / (c.next - c.day)) * axis.cellWidth;
}

export function taskPosition(task, axis) {
  const a = dayNumber(task.planned_start), b = dayNumber(task.planned_end);
  if (a === null || b === null || b < a || !axis.columns.length) return null;
  const left = axisOffset(task.planned_start, axis);
  const endColumn = axis.columns.findIndex(c => b >= c.day && b < c.next);
  if (left === null || endColumn < 0) return null;
  const c = axis.columns[endColumn];
  const right = (endColumn + (b + 1 - c.day) / (c.next - c.day)) * axis.cellWidth;
  return { left, width: right - left, start: axis.columns.findIndex(c => a >= c.day && a < c.next), span: b - a + 1 };
}

const order = ['制片组', '导演组', '摄影组', '灯光组', '录音组', '美术组', '服化组', '后勤组'];
export function departmentGroups(rows) {
  const groups = new Map();
  for (const row of rows) {
    const name = row.task.details?.department?.trim() || '待分配部门';
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(row);
  }
  return [...groups].map(([name, tasks]) => ({ name, rows: [...tasks].sort((a, b) => (a.task.planned_start || '9999').localeCompare(b.task.planned_start || '9999') || a.task.title.localeCompare(b.task.title, 'zh-CN')) }))
    .sort((a, b) => (a.name === '待分配部门' ? 999 : order.includes(a.name) ? order.indexOf(a.name) : 99) - (b.name === '待分配部门' ? 999 : order.includes(b.name) ? order.indexOf(b.name) : 99) || a.name.localeCompare(b.name, 'zh-CN'));
}

export function previewOperations(tasks, operations) {
  const current = new Map(tasks.map(t => [t.id, t]));
  return operations.map(op => {
    const before = current.get(op.ref);
    const task = op.action === 'add' ? { ...op.task, id: op.ref } : { ...before, ...op.changes,
      details: { ...before?.details, ...op.changes?.details }, ...(op.action === 'cancel' ? { status: 'cancelled' } : {}) };
    return { key: op.ref, task, change: op.action, previous: before };
  });
}


export function departmentTargets(tasks, operations = null) {
  const current = new Map(tasks.map(t => [t.id, t]));
  const rows = operations === null ? tasks.map(task => ({ key: task.id, task })) : previewOperations(tasks, operations);
  return rows.filter(row => row.change !== 'cancel' && ['todo', 'in_progress'].includes(row.task.status)
    && !row.task.details?.department?.trim()
    && (row.change !== 'update' || !current.get(row.key)?.details?.department?.trim()));
}
