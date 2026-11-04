// 档期只负责浏览和选择；真实时段计算由 availability 提供，编辑和保存由父页面负责。
import React, { useMemo, useState } from 'react';
import { addDays, buildWeek, todayKey } from './availability';
import './availability.css';

const EMPTY = [];
const STATES = { available: '可用', unavailable: '不可用', partial: '部分时段已登记', unknown: '未知' };

/**
 * people/resources/tasks 为项目真实资料；kind 决定展示人员或资源。
 * onSelect 接收实体、日期及可选任务 ID；传 null 清除详情，children 为父页面管理的详情或编辑侧栏。
 * busy 时暂停浏览及选择，避免保存期间切换实体导致草稿归属变化；组件不写入任何业务资料。
 */
export default function AvailabilityBoard({ kind, people = EMPTY, resources = EMPTY, tasks = EMPTY, busy = false,
  onSelect, selected, onAdd, onIncomplete, children }) {
  const [date, setDate] = useState(todayKey);
  const [range, setRange] = useState('month');
  // 两类资料分别保存筛选条件，切换页签不把姓名当成资源搜索；周日期仍保持一致。
  const [filters, setFilters] = useState({ people: { search: '', category: '' }, resources: { search: '', category: '' } });
  const { search, category } = filters[kind];
  const filter = patch => setFilters(current => ({ ...current, [kind]: { ...current[kind], ...patch } }));
  const isPeople = kind === 'people';
  const noun = isPeople ? '人员' : '资源';
  const week = useMemo(() => buildWeek({ date, range, kind, people, resources, tasks }), [date, range, kind, people, resources, tasks]);
  const categories = [...new Set(week.rows.map(row => row.subtitle).filter(Boolean))];
  const query = search.trim().toLocaleLowerCase();
  // 切换人员/资源或删除分类后，失效的筛选值按“全部”处理，避免出现看似空白的周表。
  const currentCategory = categories.includes(category) ? category : '';
  const rows = week.rows.filter(row => (!query || row.name.toLocaleLowerCase().includes(query)) && (!currentCategory || row.subtitle === currentCategory));
  // ID 统一转成字符串比较，兼容父页面从表单取得的字符串 ID 和接口数字 ID。
  const active = (row, cellDate, taskId = null) => selected?.kind === kind
    && String(selected.entityId) === String(row.id) && selected.date === cellDate
    && (taskId == null ? selected.taskId == null : String(selected.taskId) === String(taskId));
  const select = (row, cellDate, taskId = null) => onSelect?.({ kind, entityId: row.id, date: cellDate, taskId });
  // 翻周后关闭旧日期详情，避免侧栏仍显示上周安排；编辑期间日期控件已禁用。
  const changeDate = value => { setDate(value); onSelect?.(null); };

  const moveRange = delta => {
    if (range !== 'month') return changeDate(addDays(week.start, delta * week.days.length));
    const target = new Date(`${week.start}T00:00:00Z`);
    target.setUTCMonth(target.getUTCMonth() + delta);
    changeDate(target.toISOString().slice(0, 10));
  };
  return <section className="availability-board" aria-label={`${noun}档期`}>
    <div className="availability-toolbar">
      <div className="availability-week-nav">
        <button type="button" disabled={busy} aria-label="上一时段" onClick={() => moveRange(-1)}>‹</button>
        <h2>档期表</h2>
        <span>{week.start} 至 {week.days.at(-1)?.date}</span>
        <button type="button" disabled={busy} aria-label="下一时段" onClick={() => moveRange(1)}>›</button>
      </div>
      <div className="availability-toolbar-actions">
        <label className="availability-date-label">范围<select value={range} disabled={busy} onChange={e => { setRange(e.target.value); onSelect?.(null); }}><option value="week">周</option><option value="fortnight">双周</option><option value="month">月</option></select></label>
        <button type="button" className="availability-today" disabled={busy} onClick={() => changeDate(todayKey())}>今天</button>
        <label className="availability-date-label">选择日期
          <input type="date" value={date} disabled={busy} onChange={event => { if (event.target.value) changeDate(event.target.value); }}/>
        </label>
        {onAdd ? <button type="button" className="availability-primary" disabled={busy} onClick={onAdd}>新增{noun}</button> : null}
      </div>
    </div>
    <div className="availability-filters">
      <label>搜索{noun}<input type="search" placeholder={isPeople ? '输入姓名' : '输入资源名称'} value={search} disabled={busy} onChange={event => filter({ search: event.target.value })}/></label>
      <label>{isPeople ? '部门' : '资源类型'}<select value={currentCategory} disabled={busy} onChange={event => filter({ category: event.target.value })}>
        <option value="">全部</option>
        {categories.map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <span className="availability-count">{rows.length} {isPeople ? '位人员' : '项资源'}</span>
    </div>
    <div className={`availability-layout${children ? ' availability-has-detail' : ''}`}>
      <div className="availability-table-wrap" tabIndex={0} role="region" aria-label="可横向滚动的档期表">
        <table className="availability-table" style={{ minWidth: 210 + week.days.length * (range === 'month' ? 44 : 64) }}>
          <caption className="availability-sr-only">{noun}档期，{week.start}开始的档期</caption>
          <thead><tr><th scope="col">{isPeople ? '人员 / 职务' : '资源 / 类型'}</th>
            {week.days.map(day => <th scope="col" key={day.date} className={day.isToday ? 'availability-current-day' : ''} aria-current={day.isToday ? 'date' : undefined}>
              <span>{day.weekday}</span><small>{day.label}</small>{day.isToday ? <em>今天</em> : null}
            </th>)}
          </tr></thead>
          <tbody>{rows.map(row => <tr key={row.id}>
            <th scope="row"><button type="button" className="availability-entity" disabled={busy || !onSelect} onClick={() => select(row, week.start)}>
              <strong>{row.name}</strong><small>{row.subtitle || (isPeople ? '部门待填' : '类型待填')}{isPeople && row.entity.roles?.length ? ` · ${row.entity.roles.join('、')}` : ''}</small>
            </button><p className="availability-note-preview">{(isPeople ? row.entity.notes : row.entity.data.preparation?.notes) || '暂无备注'}</p><details className="availability-row-note"><summary>完整备注</summary><p>{(isPeople ? row.entity.notes : row.entity.data.preparation?.notes) || '暂无备注'}</p></details></th>
            {row.cells.map(cell => <td key={cell.date} className={`availability-cell availability-state-${cell.state}`}>
              <button type="button" className={`availability-cell-status${active(row, cell.date) ? ' is-active' : ''}`} disabled={busy || !onSelect}
                aria-pressed={active(row, cell.date)} aria-label={`${row.name}，${cell.date}，${cell.label || STATES[cell.state]}`} onClick={() => select(row, cell.date)}>
                {cell.label || STATES[cell.state]}
              </button>
              {cell.allocations.map((allocation, index) => <button type="button" key={`${allocation.task.id}-${index}`}
                className={`availability-allocation${allocation.overlapIds?.length ? ' has-overlap' : ''}${active(row, cell.date, allocation.task.id) ? ' is-active' : ''}`}
                disabled={busy || !onSelect} aria-pressed={active(row, cell.date, allocation.task.id)} onClick={() => select(row, cell.date, allocation.task.id)}>
                <span>{allocation.label}</span><strong>{allocation.task.title || allocation.task.name || '未命名任务'}</strong>
                {allocation.overlapIds?.length ? <small className="availability-warning">重叠待核对</small> : null}
                {allocation.availabilityIssue ? <small className="availability-warning">档期待核对</small> : null}
              </button>)}
            </td>)}
          </tr>)}</tbody>
        </table>
        {!rows.length ? <div className="availability-empty">{week.rows.length ? '未找到符合筛选条件的记录，请调整搜索或筛选。' : `还没有${noun}资料，请先新增${noun}并登记可用时段。`}</div> : null}
      </div>
      {children ? <aside className="availability-detail" aria-label="档期详情">{children}</aside> : null}
    </div>
    <ul className="availability-legend" aria-label="档期图例">
      {Object.entries(STATES).map(([state, label]) => <li key={state}><i className={`availability-state-${state}`}/>{label}</li>)}
      <li><i className="availability-legend-task"/>已安排任务（计划使用时段）</li>
      <li><i className="availability-legend-overlap"/>重叠待核对</li>
    </ul>
    <p className="availability-note">任务期限不等于使用时间；空白档期不代表可用，部分可用需查看具体时段。</p>
    {week.incomplete.length ? <details className="availability-incomplete">
      <summary>{week.incomplete.length} 项任务档期资料待补充</summary>
      <ul>{week.incomplete.map(({ task, reasons }) => <li key={task.id}><div><strong>{task.title || task.name || '未命名任务'}</strong><p>{reasons.join('；')}</p></div>
        {onIncomplete ? <button type="button" disabled={busy} onClick={() => onIncomplete(task)}>查看任务</button> : null}</li>)}</ul>
    </details> : null}
  </section>;
}
