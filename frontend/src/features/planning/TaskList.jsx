// 筛选正式日程任务，展示详情并向父页面发送编辑、状态及依据查看请求。
import React, { useMemo, useState } from 'react';
import { personNames } from '../preparation/people';
import { periodText } from '../preparation/PeriodEditor';
import { phases, statuses } from './api';
import TaskDrawer from './TaskDrawer';
import GanttTable from './GanttTable';

/**
 * 参数：tasks/people/resources/settings/warnings 提供任务、人员、资源、安排和提醒，busy 控制交互。
 * onEdit 请求编辑，onStatus 请求更新状态，onEvidence 打开关联依据；返回任务列表和所选详情 JSX。
 * 本地筛选和选择仅影响展示；正式任务更新由父层回调处理。
 */
export default function TaskList({ resources = [], people = [], tasks, settings, warnings, busy, error = '', onEdit, onStatus, onEvidence }) {
  const [mode, setMode] = useState('list'), [department, setDepartment] = useState(''), [sort, setSort] = useState('planned_end'), [grouped, setGrouped] = useState(false);
  const [phase, setPhase] = useState(''), [status, setStatus] = useState(''), [query, setQuery] = useState(''), [selected, setSelected] = useState(null);
  // 人员引用只存 ID，展示和搜索始终取当前资料，历史手填姓名继续保留。
  const assignees = t => personNames(t.details, people);
  const rows = useMemo(() => tasks.filter(t => (!department || (t.details.department || '待分配部门') === department) && (!phase || t.phase === phase) && (!status || (['overdue', 'today', 'soon'].includes(status) ? t.due_state === status : status === 'pending' ? !['completed', 'cancelled'].includes(t.status) : t.status === status)) && `${t.title} ${t.description} ${t.details.department || ''} ${assignees(t).join(' ')}`.includes(query)).sort((a, b) => (grouped ? (a.details.department || '待分配部门').localeCompare(b.details.department || '待分配部门', 'zh') : 0) || (a[sort] || '9999').localeCompare(b[sort] || '9999')).map(t => ({ key: t.id, task: t })), [tasks, people, department, phase, status, query, sort, grouped]);
  const t = tasks.find(t => t.id === selected);
  return <section className="gantt-section"><div className="plan-toolbar"><h2>正式日程 <span className="gantt-count">{tasks.length}</span></h2><div className="plan-actions">{[['list', '任务清单'], ['gantt', '甘特图']].map(([key, label]) => <button type="button" aria-pressed={mode === key} key={key} onClick={() => setMode(key)}>{label}</button>)}</div></div>
    <div className="plan-grid gantt-filters"><label>搜索任务或实施人员<input value={query} onChange={e => setQuery(e.target.value)} placeholder="任务、部门、姓名"/></label><label>部门<select value={department} onChange={e => setDepartment(e.target.value)}><option value="">全部部门</option>{[...new Set(tasks.map(t => t.details.department || '待分配部门'))].map(d => <option key={d}>{d}</option>)}</select></label><label>阶段<select value={phase} onChange={e => setPhase(e.target.value)}><option value="">全部阶段</option>{Object.entries(phases).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label><label>状态<select value={status} onChange={e => setStatus(e.target.value)}><option value="">全部状态</option><option value="pending">待处理</option><option value="overdue">已逾期</option><option value="today">今日到期</option><option value="soon">三天内到期</option>{Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
    <div className="plan-actions task-quick-filters">{[['', '全部任务'], ['pending', '待处理'], ['soon', '即将到期'], ['overdue', '已逾期']].map(([key, label]) => <button type="button" key={key} aria-pressed={status === key} onClick={() => setStatus(key)}>{label}</button>)}
      {mode === 'list' && <><label>排序<select value={sort} onChange={e => setSort(e.target.value)}><option value="planned_end">完成日期</option><option value="planned_start">开始日期</option><option value="title">任务名称</option></select></label><label><input type="checkbox" checked={grouped} onChange={e => setGrouped(e.target.checked)}/>按部门分组</label></>}
    </div>
    {rows.length ? mode === 'gantt' ? <GanttTable people={people} rows={rows} settings={settings} warnings={warnings} selectedKey={selected} onSelect={row => setSelected(row.key)} label="正式日程"/> : <div className="task-table-wrap"><table className="task-table"><thead><tr>{['任务', '部门', '实施人员', '计划日期', '状态', '备注'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(({ task: item }, index) => <React.Fragment key={item.id}>
      {grouped && (index === 0 || item.details.department !== rows[index - 1].task.details.department) && <tr className="task-group"><th colSpan={6}>{item.details.department || '待分配部门'}</th></tr>}
      <tr><td><button type="button" className="task-name" disabled={busy} onClick={() => setSelected(item.id)}>{item.title}</button>{(item.due_state || item.blocked) && <small className="task-alert">{item.due_state === 'overdue' ? '已逾期' : item.due_state === 'today' ? '今日到期' : item.due_state === 'soon' ? '三天内到期' : ''}{item.blocked ? ' · 前置未完成' : ''}</small>}</td><td>{item.details.department || '待分配'}</td><td>{assignees(item).join('、') || '待分配'}</td><td>{item.planned_start || '待定'}<br/>{item.planned_end || '待定'}</td><td><select aria-label={`${item.title}的状态`} value={item.status} disabled={busy} onChange={e => onStatus(item, e.target.value)}>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></td><td><button type="button" className="task-note-preview" disabled={busy} onClick={() => setSelected(item.id)}>{item.details.result_notes || item.description || '暂无备注'}</button></td></tr>
    </React.Fragment>)}</tbody></table></div> : <p className="plan-muted">暂无符合条件的任务。可以人工添加，也可以先生成并确认日程建议。</p>}
    {t && <TaskDrawer title="任务详情" busy={busy} onClose={() => setSelected(null)}><div className="gantt-task-detail">{error && <p role="alert" className="error">{error}</p>}<div className="plan-toolbar"><h3>{t.title}</h3></div><p>{phases[t.phase]} · {t.details.department || '待分配部门'} · 实施人员：{assignees(t).join('、') || '待分配'}</p><p>{t.description || '暂无说明'}</p><p>{periodText(t.details.usage_period)} · {t.details.requires_people ? '需要落实人员' : '未要求人员'}</p><p>落实结果：{t.details.result_notes || '待填写'}</p><p>完成标准：{t.completion_criteria || '待补充'}</p><p>安排理由：{t.details.rationale || '未填写'}</p>
      <p>前置：{t.details.dependencies.map(d => tasks.find(x => x.id === d.task_id)?.title || '关联失效').join('、') || '无'}</p><p>资源：{t.details.resource_refs.map(r => resources.find(x => x.id === r.record_id)?.data.title || r.name).join('、') || '未关联'}</p>
      {t.details.constraints.map((c, i) => <p key={i}>{c.strength === 'hard' ? '硬限制' : '软要求'} · {c.confirmation === 'confirmed' ? '已确认' : '待确认'} · {c.date || `${c.milestone} ${c.offset_days}天`} · {c.source || '来源待补'}</p>)}
      {(warnings || []).filter(w => w.task_id === t.id).map((w, i) => <p className="warning" key={i}>{w.message}</p>)}
      <div className="plan-actions">{t.details.scene_refs.map(s => <button type="button" key={`${s.script_id}:${s.scene_id}`} disabled={busy} onClick={e => { setSelected(null); onEvidence(t, s, e.currentTarget); }}>回看第 {s.scene_number || '未编号'} 场 · {s.location || '场地待定'}</button>)}</div>
      <div className="plan-actions"><button disabled={busy} onClick={() => { setSelected(null); onEdit(t); }}>编辑安排</button>{!['completed', 'cancelled'].includes(t.status) && <button disabled={busy} onClick={() => onStatus(t, 'completed')}>标记完成</button>}{t.status === 'todo' && <button disabled={busy} onClick={() => onStatus(t, 'in_progress')}>开始处理</button>}{['completed', 'cancelled'].includes(t.status) && <button disabled={busy} onClick={() => onStatus(t, 'todo')}>重新打开</button>}</div>
    </div></TaskDrawer>}
  </section>;
}
