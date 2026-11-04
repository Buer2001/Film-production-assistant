// 按部门组织甘特图，支持日、周、月时间轴及任务选择。
import React, { useMemo, useState } from 'react';
import { personNames } from '../preparation/people';
import { categories, statuses } from './api';
import { makeAxis, taskPosition, departmentGroups, axisOffset } from './timeline';

const columns = [{ width: 244, left: 0 }, { width: 116, left: 244 }, { width: 88, left: 360 }, { width: 88, left: 448 }, { width: 94, left: 536 }];
const fixedWidth = 630;
const changeLabels = { add: '新增', update: '修改', cancel: '取消' };
const dueLabels = { overdue: '逾期', today: '今日到期', soon: '三天内到期' };
const dateText = value => value ? `${Number(value.slice(5, 7))}/${Number(value.slice(8, 10))}` : '待定';
const localToday = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

/**
 * 参数：rows 为任务投影行，settings 为里程碑，warnings 为提醒，people 为人员资料。
 * onSelect 接收选中行，selectedKey 标记当前行，label 为表格说明；返回甘特图 JSX。
 * 时间轴只作展示；无日期或异常跨度时显示提示，不补造任务安排。
 */
export default function GanttTable({ people = [], rows, settings = {}, warnings = [], onSelect, selectedKey, label }) {
  const [mode, setMode] = useState('week'), [collapsed, setCollapsed] = useState(new Set());
  const axis = useMemo(() => makeAxis(rows, mode, settings), [rows, mode, settings]);
  const groups = useMemo(() => departmentGroups(rows), [rows]);
  const warningCounts = useMemo(() => { const counts = new Map(); warnings.forEach(w => counts.set(w.task_id, (counts.get(w.task_id) || 0) + 1)); return counts; }, [warnings]);
  const markers = [['开拍', settings.shoot_start], ['杀青', settings.shoot_end], ['收尾', settings.close_date], ['今天', localToday()]]
    .map(([name, date]) => ({ name, date, left: axisOffset(date, axis) })).filter(m => m.left !== null);
  const style = index => ({ width: columns[index].width, minWidth: columns[index].width, maxWidth: columns[index].width, left: columns[index].left });
  function toggle(name) { setCollapsed(previous => { const next = new Set(previous); next.has(name) ? next.delete(name) : next.add(name); return next; }); }
  const guides = () => markers.map(m => <span key={m.name} className={`gantt-guide ${m.name === '今天' ? 'is-today' : ''}`} style={{ left: m.left }} aria-hidden="true"/>);
  return <div className="gantt-view">
    <div className="gantt-toolbar"><span className="plan-muted">{rows.length} 项任务 · {groups.length} 个部门 · 点击任务查看详情</span><div className="gantt-scale" aria-label="时间刻度">{[['day', '日'], ['week', '周'], ['month', '月']].map(([key, name]) => <button type="button" key={key} aria-pressed={mode === key} onClick={() => setMode(key)}>{name}</button>)}</div></div>
    {axis.warning && <p className="plan-muted" role="status">{axis.warning}</p>}
    <div className="gantt-scroll" tabIndex={0} role="region" aria-label={`${label}，可横向滚动`}>
      <table className="gantt-table" style={{ width: fixedWidth + Math.max(axis.width, 220) }}><caption className="gantt-sr-only">{label}，按主责部门分组</caption>
        <colgroup>{columns.map((c, i) => <col key={i} style={{ width: c.width }}/ >)}<col style={{ width: Math.max(axis.width, 220) }}/></colgroup>
        <thead><tr>{['任务名称', '计划实施人员', '开始', '完成', '状态'].map((name, i) => <th scope="col" className={`gantt-fixed ${i === 0 ? 'gantt-name' : ''}`} style={style(i)} key={name}>{name}</th>)}
          <th scope="col" className="gantt-calendar-head"><div className="gantt-calendar" style={{ width: Math.max(axis.width, 220) }}>{axis.columns.map(c => <div className={c.weekend ? 'is-weekend' : ''} key={c.start} style={{ width: axis.cellWidth }}><strong>{c.label}</strong><small>{c.sub}</small></div>)}</div>
          {markers.map(m => <span className={`gantt-marker ${m.name === '今天' ? 'is-today' : ''}`} style={{ left: m.left }} key={m.name} title={`${m.name} ${m.date}`}>{m.name}</span>)}</th>
        </tr></thead>
        <tbody>{groups.map(group => {
          const folded = collapsed.has(group.name), bars = group.rows.map(r => taskPosition(r.task, axis)).filter(Boolean);
          const first = bars.length ? Math.min(...bars.map(p => p.left)) : 0, last = bars.length ? Math.max(...bars.map(p => p.left + p.width)) : 0;
          return <React.Fragment key={group.name}>
            <tr className="gantt-group"><th colSpan={5} className="gantt-group-label" scope="rowgroup"><button type="button" aria-expanded={!folded} onClick={() => toggle(group.name)}>{folded ? '▸' : '▾'} {group.name}<span>{group.rows.length} 项</span></button></th><td className="gantt-chart-cell"><div className="gantt-track" style={{ width: Math.max(axis.width, 220), '--gantt-unit': `${axis.cellWidth || 112}px` }}>{bars.length > 0 && <span className="gantt-group-bar" style={{ left: first, width: last - first }}/ >}{guides()}</div></td></tr>
            {!folded && group.rows.map(row => {
              const t = row.task, position = taskPosition(t, axis), count = warningCounts.get(row.key) || 0;
              const selected = selectedKey === row.key;
              return <tr key={row.key} className={`gantt-task-row ${selected ? 'is-selected' : ''} ${row.change === 'cancel' ? 'is-cancelled' : ''}`}>
                <td className="gantt-fixed gantt-name" style={style(0)}><button type="button" className="gantt-task-link" onClick={() => onSelect(row)} title={t.title}>{row.change && <span className={`gantt-change change-${row.change}`}>{changeLabels[row.change]}</span>}{t.title}</button><div className="gantt-row-meta">{categories[t.category] || '其他'}{(t.details?.collaborating_departments || []).length > 0 && <span title={t.details.collaborating_departments.join('、')}> · 协作 {t.details.collaborating_departments.join('、')}</span>}</div></td>
                <td className="gantt-fixed" style={style(1)} title={personNames(t.details, people).join('、')}>{personNames(t.details, people).length ? personNames(t.details, people).join('、') : <span className="gantt-unassigned">待分配</span>}</td>
                <td className="gantt-fixed gantt-date" style={style(2)} title={t.planned_start || '开始日期待定'}>{dateText(t.planned_start)}</td><td className="gantt-fixed gantt-date" style={style(3)} title={t.planned_end || '完成日期待定'}>{dateText(t.planned_end)}</td>
                <td className="gantt-fixed" style={style(4)}><span className={`gantt-status status-${t.status}`}>{statuses[t.status] || '待办'}</span>{(t.due_state || t.blocked || count > 0) && <small className="gantt-row-warning">{[dueLabels[t.due_state], t.blocked ? '前置未完成' : '', count ? `${count}条提醒` : ''].filter(Boolean).join(' · ')}</small>}</td>
                <td className="gantt-chart-cell"><div className="gantt-track" style={{ width: Math.max(axis.width, 220), '--gantt-unit': `${axis.cellWidth || 112}px` }}>{guides()}{position ? <button type="button" className={`gantt-bar status-${t.status} ${row.change === 'cancel' ? 'is-cancelled' : ''}`} style={{ left: position.left + 2, width: Math.max(3, position.width - 4) }} onClick={() => onSelect(row)} aria-label={`${t.title}，${t.planned_start}至${t.planned_end}`} title={`${t.title}\n${t.planned_start} → ${t.planned_end}`}><span>{t.title}</span></button> : <span className="gantt-no-dates">{axis.warning ? '—' : '日期待定'}</span>}</div></td>
              </tr>;
            })}
          </React.Fragment>;
        })}</tbody>
      </table>
    </div>
    <p className="gantt-footnote">时间条包含开始和完成当天。协作部门以标签显示；未定日期不会被自动补齐。</p>
  </div>;
}
