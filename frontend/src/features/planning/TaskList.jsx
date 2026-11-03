import React, { useEffect, useMemo, useRef, useState } from 'react';
import { phases, statuses } from './api';
import GanttTable from './GanttTable';

export default function TaskList({ resources = [], tasks, settings, warnings, busy, onEdit, onStatus, onEvidence }) {
  const [phase, setPhase] = useState(''), [status, setStatus] = useState(''), [query, setQuery] = useState(''), [selected, setSelected] = useState(null);
  const rows = useMemo(() => tasks.filter(t => (!phase || t.phase === phase) && (!status || (['overdue', 'today', 'soon'].includes(status) ? t.due_state === status : t.status === status)) && `${t.title} ${t.description} ${t.details.department || ''} ${(t.details.assignees || []).join(' ')}`.includes(query)).map(t => ({ key: t.id, task: t })), [tasks, phase, status, query]);
  const detailRef = useRef(null);
  useEffect(() => { if (selected) detailRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, [selected]);
  const t = tasks.find(t => t.id === selected);
  return <section className="gantt-section"><div className="plan-toolbar"><h2>正式日程 <span className="gantt-count">{tasks.length}</span></h2><span className="plan-muted">按主责部门查看任务安排</span></div>
    <div className="plan-grid gantt-filters"><label>搜索任务或实施人员<input value={query} onChange={e => setQuery(e.target.value)} placeholder="任务、部门、姓名"/></label><label>阶段<select value={phase} onChange={e => setPhase(e.target.value)}><option value="">全部阶段</option>{Object.entries(phases).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label><label>状态<select value={status} onChange={e => setStatus(e.target.value)}><option value="">全部状态</option><option value="overdue">已逾期</option><option value="today">今日到期</option><option value="soon">三天内到期</option>{Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
    {rows.length ? <GanttTable rows={rows} settings={settings} warnings={warnings} selectedKey={selected} onSelect={row => setSelected(row.key)} label="正式日程"/> : <p className="plan-muted">暂无符合条件的任务。可以人工添加，也可以先生成并确认日程建议。</p>}
    {t && <div className="gantt-task-detail" ref={detailRef}><div className="plan-toolbar"><h3>{t.title}</h3><button type="button" onClick={() => setSelected(null)}>收起详情</button></div><p>{phases[t.phase]} · {t.details.department || '待分配部门'} · 实施人员：{t.details.assignees?.join('、') || '待分配'}</p><p>{t.description || '暂无说明'}</p><p>完成标准：{t.completion_criteria || '待补充'}</p><p>安排理由：{t.details.rationale || '未填写'}</p>
      <p>前置：{t.details.dependencies.map(d => tasks.find(x => x.id === d.task_id)?.title || '关联失效').join('、') || '无'}</p><p>资源：{t.details.resource_refs.map(r => resources.find(x => x.id === r.record_id)?.data.title || r.name).join('、') || '未关联'}</p>
      {t.details.constraints.map((c, i) => <p key={i}>{c.strength === 'hard' ? '硬限制' : '软要求'} · {c.confirmation === 'confirmed' ? '已确认' : '待确认'} · {c.date || `${c.milestone} ${c.offset_days}天`} · {c.source || '来源待补'}</p>)}
      {(warnings || []).filter(w => w.task_id === t.id).map((w, i) => <p className="warning" key={i}>{w.message}</p>)}
      <div className="plan-actions">{t.details.scene_refs.map(s => <button type="button" key={`${s.script_id}:${s.scene_id}`} disabled={busy} onClick={e => onEvidence(t, s, e.currentTarget)}>回看第 {s.scene_number || '未编号'} 场 · {s.location || '场地待定'}</button>)}</div>
      <div className="plan-actions"><button disabled={busy} onClick={() => onEdit(t)}>编辑安排</button>{!['completed', 'cancelled'].includes(t.status) && <button disabled={busy} onClick={() => onStatus(t, 'completed')}>标记完成</button>}{t.status === 'todo' && <button disabled={busy} onClick={() => onStatus(t, 'in_progress')}>开始处理</button>}{['completed', 'cancelled'].includes(t.status) && <button disabled={busy} onClick={() => onStatus(t, 'todo')}>重新打开</button>}</div>
    </div>}
  </section>;
}
