import React, { useEffect, useState } from 'react';
import TaskEditor from './TaskEditor';
import { emptyTask } from './api';

const coverageLabels = { addressed: '已安排任务', done: '已落实', not_applicable: '不适用', unknown: '待确认' };
const clean = t => { const { id, completed_at, created_at, updated_at, overdue, blocked, due_state, ...rest } = t; return rest; };

export default function PlanReview({ data, busy, onSave, onConfirm, onDiscard, onDirty }) {
  const draft = data.draft;
  const [result, setResult] = useState(() => structuredClone(draft.result));
  const [editing, setEditing] = useState(null);
  useEffect(() => { setResult(structuredClone(draft.result)); setEditing(null); }, [draft.id, draft.base_revision]);
  const dirty = JSON.stringify(result) !== JSON.stringify(draft.result) || editing !== null;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  const current = new Map(data.tasks.map(t => [t.id, t]));
  const effective = op => op.action === 'add' ? { id: op.ref, ...op.task } : { ...current.get(op.ref), ...op.changes, details: { ...(current.get(op.ref)?.details || {}), ...(op.changes?.details || {}) } };
  const available = [...data.tasks];
  result.operations.filter(op => op.action === 'add').forEach(op => available.push({ id: op.ref, ...op.task }));
  const checklist = new Map(data.checklist.map(c => [c.id, c.name]));
  function saveTask(value) {
    const operations = [...result.operations];
    if (editing.index === -1) operations.push({ action: 'add', ref: `new-${crypto.randomUUID()}`, task: clean(value), changes: {} });
    else {
      const op = operations[editing.index];
      operations[editing.index] = op.action === 'add' ? { ...op, task: clean(value) } : { ...op, changes: clean(value) };
    }
    setResult({ ...result, operations }); setEditing(null);
  }
  function remove(index) {
    const ref = result.operations[index].ref;
    const operations = result.operations.filter((_, i) => i !== index).map(op => {
      if (op.action === 'add') return { ...op, task: { ...op.task, details: { ...op.task.details, dependencies: (op.task.details?.dependencies || []).filter(d => d.task_id !== ref) } } };
      if (op.changes?.details?.dependencies) return { ...op, changes: { ...op.changes, details: { ...op.changes.details, dependencies: op.changes.details.dependencies.filter(d => d.task_id !== ref) } } };
      return op;
    });
    const coverage = result.coverage.map(c => {
      const task_refs = c.task_refs.filter(t => t !== ref);
      return { ...c, task_refs, status: c.status === 'addressed' && !task_refs.length ? 'unknown' : c.status };
    });
    setResult({ ...result, operations, coverage });
  }
  return <section className="plan-review"><h2>待确认日程建议</h2><p>以下内容尚未写入正式任务。请核对日期、遗漏和外部期限；保存草稿后再确认执行。</p>
    {data.draft_stale && <p className="warning">日程或剧本依据已变化，这份草稿暂不能确认。请保留需要的内容后重新生成，或放弃草稿。</p>}
    {draft.warnings.length > 0 && <details open><summary>安排提醒 · {draft.warnings.length}</summary>{draft.warnings.map((w, i) => <p className="warning" key={i}>{effective(result.operations.find(o => o.ref === w.task_id) || { ref: w.task_id, changes: {} })?.title || w.task_id}：{w.message}</p>)}</details>}
    <label>待确认问题（每行一项）<textarea disabled={busy || data.draft_stale} rows={Math.min(8, Math.max(2, result.questions.length))} value={result.questions.join('\n')} onChange={e => setResult({ ...result, questions: e.target.value.split('\n') })}/></label>
    {result.operations.map((op, i) => { const t = effective(op); return <article className="plan-task" key={op.ref}><h3>{op.action === 'add' ? '新增' : op.action === 'cancel' ? '取消' : '修改'} · {t.title}</h3>
      {op.action === 'update' && <p>原安排：{current.get(op.ref)?.planned_start || '待定'} → {current.get(op.ref)?.planned_end || '待定'}</p>}
      <p>建议：{t.planned_start || '开始待定'} → {t.planned_end || '完成待定'}</p><p>完成标准：{t.completion_criteria || '待补充'}</p>
      <details><summary>完整变更内容</summary><pre>{JSON.stringify(op, null, 2)}</pre></details>
      <div className="plan-actions">{op.action !== 'cancel' && <button disabled={busy || data.draft_stale} onClick={() => setEditing({ index: i, value: t })}>调整建议</button>}<button disabled={busy || data.draft_stale} onClick={() => remove(i)}>移除此项建议</button></div>
    </article>; })}
    <button disabled={busy || data.draft_stale} onClick={() => setEditing({ index: -1, value: emptyTask() })}>补充草稿任务</button>
    {editing && <TaskEditor key={editing.index} initial={editing.value} tasks={available} scenes={data.scene_options} busy={busy} draft isNew={editing.index === -1 || result.operations[editing.index]?.action === 'add'} onSave={saveTask} onCancel={() => setEditing(null)}/>}
    <details><summary>工作框架查漏 · {result.coverage.length} 项</summary><p>逐项处理不代表模型判断正确，请检查“不适用”和“已落实”的依据。</p>{result.coverage.map((c, i) => <div className="plan-constraint" key={c.check_id}><strong>{checklist.get(c.check_id) || c.check_id}</strong>
      <label>检查结果<select disabled={busy || data.draft_stale} value={c.status} onChange={e => setResult({ ...result, coverage: result.coverage.map((x, n) => n === i ? { ...x, status: e.target.value } : x) })}>{Object.entries(coverageLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>判断依据<input disabled={busy || data.draft_stale} maxLength={1000} value={c.reason} onChange={e => setResult({ ...result, coverage: result.coverage.map((x, n) => n === i ? { ...x, reason: e.target.value } : x) })}/></label>
      <label>关联任务<select multiple size={3} disabled={busy || data.draft_stale} value={c.task_refs} onChange={e => { const task_refs = [...e.target.selectedOptions].map(o => o.value); setResult({ ...result, coverage: result.coverage.map((x, n) => n === i ? { ...x, task_refs } : x) }); }}>{available.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
    </div>)}</details>
    <div className="plan-actions"><button disabled={busy || !dirty || editing !== null || data.draft_stale} onClick={() => onSave(result)}>保存草稿修改</button><button disabled={busy || dirty || data.draft_stale} onClick={onConfirm}>确认应用 {result.operations.length} 项建议</button><button disabled={busy} onClick={onDiscard}>放弃这份草稿</button></div>
  </section>;
}
