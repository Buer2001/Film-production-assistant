import React, { useState } from 'react';
import { phases, categories, statuses } from './api';

export default function TaskList({ tasks, busy, onEdit, onStatus, onEvidence }) {
  const [phase, setPhase] = useState(''), [status, setStatus] = useState(''), [query, setQuery] = useState('');
  const shown = tasks.filter(t => (!phase || t.phase === phase) && (!status || (['overdue', 'today', 'soon'].includes(status) ? t.due_state === status : t.status === status)) && `${t.title} ${t.description}`.includes(query)).sort((a, b) => Number(b.overdue) - Number(a.overdue) || (a.planned_end || '9999').localeCompare(b.planned_end || '9999') || a.title.localeCompare(b.title));
  return <section><h2>正式任务 · {tasks.length}</h2><div className="plan-grid"><label>搜索任务<input value={query} onChange={e => setQuery(e.target.value)}/></label><label>阶段筛选<select value={phase} onChange={e => setPhase(e.target.value)}><option value="">全部阶段</option>{Object.entries(phases).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label><label>状态筛选<select value={status} onChange={e => setStatus(e.target.value)}><option value="">全部状态</option><option value="overdue">已逾期</option><option value="today">今日到期</option><option value="soon">三天内到期</option>{Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
    {!shown.length && <p className="plan-muted">暂无符合条件的任务。可以先人工添加，也可以保存项目安排后生成日程建议。</p>}
    <div className="plan-task-list">{shown.map(t => <article className="plan-task" key={t.id}>
      <div className="plan-task-heading"><h3>{t.title}</h3><span>{phases[t.phase]} · {categories[t.category]}</span></div>
      <p>{t.planned_start || '开始待定'} → {t.planned_end || '完成待定'} · {statuses[t.status]} {t.due_state && <strong className="plan-danger">{{ overdue: '逾期', today: '今日到期', soon: '三天内到期' }[t.due_state]}</strong>} {t.blocked && <strong className="plan-danger">前置未完成</strong>}</p>
      {t.completion_criteria && <p>完成标准：{t.completion_criteria}</p>}
      {t.details.scene_refs.length > 0 && <div className="plan-actions" aria-label="关联拆解依据">{t.details.scene_refs.map(s => <button type="button" key={`${s.script_id}:${s.scene_id}`} disabled={busy} onClick={e => onEvidence(t, s, e.currentTarget)}>回看第 {s.scene_number || '未编号'} 场 · {s.location || '场地待定'}</button>)}</div>}
      <details><summary>查看说明和安排依据</summary><p>{t.description || '暂无说明'}</p><p>{t.details.rationale}</p>
        <p>前置：{t.details.dependencies.map(d => tasks.find(x => x.id === d.task_id)?.title || '关联失效').join('、') || '无'}</p>
        <p>场次：{t.details.scene_refs.map(s => `${s.scene_number} ${s.location}`).join('、') || '未关联'}</p>
        <p>资源：{t.details.resource_refs.map(r => r.name).join('、') || '未关联'}</p>
        {t.details.constraints.map((c, i) => <p key={i}>{c.strength === 'hard' ? '硬限制' : '软要求'} · {c.confirmation === 'confirmed' ? '已确认' : '待确认'} · {c.date || `${c.milestone} ${c.offset_days}天`} · {c.source || '来源待补'}</p>)}
      </details>
      <div className="plan-actions"><button disabled={busy} onClick={() => onEdit(t)}>编辑安排</button>{t.status !== 'completed' && t.status !== 'cancelled' && <button disabled={busy} onClick={() => onStatus(t, 'completed')}>标记完成</button>}{t.status === 'todo' && <button disabled={busy} onClick={() => onStatus(t, 'in_progress')}>开始处理</button>}{['completed', 'cancelled'].includes(t.status) && <button disabled={busy} onClick={() => onStatus(t, 'todo')}>重新打开</button>}</div>
    </article>)}</div>
  </section>;
}
