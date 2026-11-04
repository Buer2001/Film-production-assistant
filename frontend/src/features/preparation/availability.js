// 周档期纯计算：UTC仅作为当地墙上时间的数轴，不做时区换算、不修改传入记录。
const DAY = 86400000;
const pad = value => String(value).padStart(2, '0');
const dateKey = value => new Date(value).toISOString().slice(0, 10);

/** 本机今天日期，避免用UTC日期导致午夜附近挪天。 */
export function todayKey() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

// 严格校验ISO日期；不把日期字符串交给本地时区解析。
function dayValue(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return NaN;
  const stamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(stamp) && dateKey(stamp) === value ? stamp : NaN;
}

/** ISO日期增加自然日，非法日期返回空字符串。 */
export function addDays(date, delta) {
  const value = dayValue(date);
  return Number.isFinite(value) ? dateKey(value + delta * DAY) : '';
}

/** 参数 value 为不带时区的本地时刻；返回距午夜的毫秒数，格式或范围非法时返回 NaN。 */
function timeValue(value) {
  const match = /^(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$/.exec(value || '');
  if (!match || +match[1] > 23 || +match[2] > 59 || +(match[3] || 0) > 59) return NaN;
  return (+match[1] * 3600 + +match[2] * 60 + +(match[3] || 0) + Number(`0.${match[4] || 0}`)) * 1000;
}

// 全天含末日；含时刻采用连续半开区间，缺失任一时刻不产生占用。
function interval(period) {
  if (!period) return null;
  const start = dayValue(period.start_date), end = dayValue(period.end_date);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  if (period.start_time == null && period.end_time == null) return [start, end + DAY];
  const a = start + timeValue(period.start_time), b = end + timeValue(period.end_time);
  return Number.isFinite(a) && Number.isFinite(b) && b > a ? [a, b] : null;
}

/** 详情使用完整时段；不合法或缺失时给出明确占位。 */
export function periodLabel(period) {
  if (!interval(period)) return '实际使用时间待补充';
  if (period.start_time == null) return `${period.start_date} 至 ${period.end_date} 全天`;
  return `${period.start_date} ${period.start_time} 至 ${period.end_date} ${period.end_time}`;
}

const intersects = (a, b) => a[0] < b[1] && b[0] < a[1];

// 合并相邻或相交的可用区间，计算目标窗口中覆盖的毫秒数。
function coverage(spans, window) {
  const parts = spans.filter(span => intersects(span, window)).map(span => [Math.max(span[0], window[0]), Math.min(span[1], window[1])]).sort((a, b) => a[0] - b[0]);
  let total = 0, end = window[0];
  for (const [a, b] of parts) { total += Math.max(0, b - Math.max(a, end)); end = Math.max(end, b); }
  return total;
}

/**
 * 参数为可用/不可用区间数组及待检查窗口，边界均为墙上时间数轴上的毫秒数。
 * 返回状态和中文标签；明确不可用优先，只有覆盖整个窗口才认定完全可用。
 */
function availabilityState(available, unavailable, window) {
  const blocked = coverage(unavailable, window), usable = coverage(available, window);
  if (blocked >= window[1] - window[0]) return { state: 'unavailable', label: '不可用' };
  if (blocked > 0) return { state: 'partial', label: '部分不可用' };
  if (usable >= window[1] - window[0]) return { state: 'available', label: '可用' };
  if (usable > 0) return { state: 'partial', label: '部分可用' };
  return { state: 'unknown', label: '未知' };
}

/** 把已裁剪到单日的占用窗口转成时间说明；整日显示“全天”，次日零点显示为24:00。 */
function allocationLabel(window, day) {
  const clock = value => value === day + DAY ? '24:00' : new Date(value).toISOString().slice(11, 16);
  return window[0] === day && window[1] === day + DAY ? '全天' : `${clock(window[0])}–${clock(window[1])}`;
}

/**
 * 根据稳定ID生成周、双周或自然月档期，默认周视图兼容现有调用。只读取usage_period作为占用来源；
 * incomplete是全局补资料清单，不混入时间冲突。返回记录及任务保持原对象引用。
 */
export function buildWeek({ date = todayKey(), range = 'week', kind, people = [], resources = [], tasks = [] }) {
  const anchor = Number.isFinite(dayValue(date)) ? dayValue(date) : dayValue(todayKey());
  // 周/双周按周一对齐；月视图按自然月，计算仍复用同一套占用规则。
  const start = range === 'month' ? dateKey(anchor).slice(0, 8) + '01' : dateKey(anchor - ((new Date(anchor).getUTCDay() + 6) % 7) * DAY);
  const length = range === 'month' ? new Date(Date.UTC(new Date(anchor).getUTCFullYear(), new Date(anchor).getUTCMonth() + 1, 0)).getUTCDate() : range === 'fortnight' ? 14 : 7;
  const days = Array.from({ length }, (_, i) => {
    const key = addDays(start, i);
    return { date: key, weekday: ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(dayValue(key)).getUTCDay()], label: `${+key.slice(5, 7)}/${+key.slice(8, 10)}`, isToday: key === todayKey() };
  });
  const peopleIds = new Set(people.map(x => x.id)), resourceIds = new Set(resources.map(x => x.id));
  const incomplete = [];
  const active = tasks.filter(task => task.status !== 'cancelled').map(task => {
    const detail = task.details || {}, span = interval(detail.usage_period);
    const personIds = [...new Set(detail.person_ids || [])], refs = detail.resource_refs || [];
    const resourceIdsForTask = [...new Set(refs.map(x => x.record_id).filter(Boolean))];
    const reasons = [];
    if (!span) reasons.push('尚未填写有效的实际使用时间');
    if (!personIds.length && !resourceIdsForTask.length) reasons.push('尚未关联人员或资源');
    // 手填姓名允许作为历史资料保留；有稳定人员引用后不再要求重复关联。
    if (((detail.assignees || []).length && !personIds.length) || personIds.some(id => !peopleIds.has(id)) || refs.some(ref => !ref.record_id || !resourceIds.has(ref.record_id))) reasons.push('手填或失效关联需核对');
    if (reasons.length) incomplete.push({ task, reasons });
    return { task, span, ids: kind === 'people' ? personIds : resourceIdsForTask };
  });
  const categories = { location: '场地', equipment: '器材', prop: '道具', costume: '服装', other: '其他' };
  const rows = (kind === 'people' ? people : resources).map(entity => {
    const availability = (kind === 'people' ? entity.availability : entity.data?.preparation?.availability) || [];
    const available = [], unavailable = [];
    for (const entry of availability) {
      const span = interval(entry);
      if (span && entry.state === 'available') available.push(span);
      if (span && entry.state === 'unavailable') unavailable.push(span);
    }
    const allocations = active.filter(entry => entry.span && entry.ids.includes(entity.id));
    const cells = days.map(day => {
      const value = dayValue(day.date), window = [value, value + DAY];
      return { date: day.date, ...availabilityState(available, unavailable, window), allocations: allocations.filter(entry => intersects(entry.span, window)).map(entry => {
        const actual = [Math.max(window[0], entry.span[0]), Math.min(window[1], entry.span[1])];
        const state = availabilityState(available, unavailable, actual);
        return { task: entry.task, period: entry.task.details.usage_period, label: allocationLabel(actual, value),
          overlapIds: [...new Set(allocations.filter(other => other !== entry && other.task.id !== entry.task.id && intersects(other.span, actual)).map(other => other.task.id))],
          availabilityIssue: state.state === 'available' ? '' : state.state === 'unknown' ? '可用情况未知' : state.label === '部分可用' ? '实际使用时段仅部分可用' : '实际使用时段存在不可用时间' };
      }) };
    });
    return { id: entity.id, name: kind === 'people' ? entity.name : entity.data?.title || '', subtitle: kind === 'people' ? entity.department || '' : categories[entity.data?.category] || entity.data?.category || '其他', entity, cells };
  });
  return { start, days, rows, incomplete };
}
