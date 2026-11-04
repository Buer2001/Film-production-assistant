// 在本地预览并调整日程建议，保存草稿后才能确认写入正式任务。
import React, { useEffect, useRef, useState } from 'react';
import TaskEditor from './TaskEditor';
import GanttTable from './GanttTable';
import { previewOperations } from './timeline';
import { emptyTask } from './api';

const coverageLabels = { addressed: '已安排任务', done: '已落实', not_applicable: '不适用', unknown: '待确认' };
const clean = t => { const { id, completed_at, created_at, updated_at, overdue, blocked, due_state, ...rest } = t; return rest; };

/**
 * 参数：data 含正式任务及草稿，people/peopleUnavailable 为人员资料，busy 控制操作。
 * onSave/onConfirm/onDiscard 分别保存、确认和放弃，onDirty 通知父层未保存状态；返回草稿审核 JSX。
 * 使用草稿副本编辑；草稿 ID 或基准版本变化时重置本地编辑，过期草稿禁用保存和确认。
 */
export default function PlanReview({ peopleUnavailable = false, people = [], data, busy, onSave, onConfirm, onDiscard, onDirty }) {
  const draft = data.draft;
  const [result, setResult] = useState(() => structuredClone(draft.result));
  const [editing, setEditing] = useState(null), [selected, setSelected] = useState(null);
  useEffect(() => { setResult(structuredClone(draft.result)); setEditing(null); }, [draft.id, draft.base_revision]);
  const dirty = JSON.stringify(result) !== JSON.stringify(draft.result) || editing !== null;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  const detailRef = useRef(null);
  useEffect(() => { if (selected) detailRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, [selected]);
  const current = new Map(data.tasks.map(t => [t.id, t]));
  const rows = previewOperations(data.tasks, result.operations);
  const selectedIndex = result.operations.findIndex(op => op.ref === selected);
  const selectedOp = result.operations[selectedIndex];
  const selectedTask = rows.find(row => row.key === selected)?.task;
  const effective = op => op.action === 'add' ? { id: op.ref, ...op.task } : { ...current.get(op.ref), ...op.changes, details: { ...(current.get(op.ref)?.details || {}), ...(op.changes?.details || {}) } };
  const available = [...data.tasks];
  result.operations.filter(op => op.action === 'add').forEach(op => available.push({ id: op.ref, ...op.task }));
  const checklist = new Map(data.checklist.map(c => [c.id, c.name]));
  /**
   * 参数 value 为任务表单结果；新增任务分配临时引用，更新项保留操作类型，仅修改本地建议。
   */
  function saveTask(value) {
    const operations = [...result.operations];
    if (editing.index === -1) operations.push({ action: 'add', ref: `new-${crypto.randomUUID()}`, task: clean(value), changes: {} });
    else {
      const op = operations[editing.index];
      operations[editing.index] = op.action === 'add' ? { ...op, task: clean(value) } : { ...op, changes: clean(value) };
    }
    setResult({ ...result, operations }); setEditing(null);
  }
  /**
   * 参数 index 为建议下标；删除新增项时一并清理依赖和覆盖引用，避免留下悬空任务引用。
   */
  function remove(index) {
    const ref = result.operations[index].ref;
    if (result.operations[index].action !== 'add') {
      setResult({ ...result, operations: result.operations.filter((_, i) => i !== index) });
      if (selected === ref) setSelected(null);
      return;
    }
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
    {draft.warnings.length > 0 && <details className="plan-notices"><summary>安排提醒 · {draft.warnings.length}</summary>{draft.warnings.map((w, i) => <p className="warning" key={i}>{effective(result.operations.find(o => o.ref === w.task_id) || { ref: w.task_id, changes: {} })?.title || w.task_id}：{w.message}</p>)}</details>}
    <details className="plan-notices"><summary>待确认问题 · {result.questions.length}</summary><label>待确认问题（每行一项）<textarea disabled={busy || data.draft_stale} rows={Math.min(8, Math.max(2, result.questions.length))} value={result.questions.join('\n')} onChange={e => setResult({ ...result, questions: e.target.value.split('\n') })}/></label></details>
    {draft.department_assignment && <p className="plan-muted" role="status">本次为 {draft.department_assignment.target_count} 项任务判断部门，已建议 {draft.department_assignment.assigned_count} 项，其余保留待确认。已有任务内容和时间安排保留。{draft.department_assignment.remaining_count > 0 && `另有 ${draft.department_assignment.remaining_count} 项尚未处理，确认本次草稿后可继续补全。`}</p>}
    {draft.department_assignment && <details className="plan-notices"><summary>部门判断明细</summary>{draft.department_assignment.suggestions.map(s => <p key={s.ref}><strong>{rows.find(r => r.key === s.ref)?.task.title || current.get(s.ref)?.title || '待确认任务'}</strong> · {s.department || '部门待确认'}：{s.reason}</p>)}</details>}
    <GanttTable people={people} rows={rows} settings={data.settings} warnings={draft.warnings} selectedKey={selected} onSelect={row => { if (editing === null) setSelected(row.key); }} label="待确认日程"/>
    {selectedOp && selectedTask && <div className="gantt-task-detail" ref={detailRef}><div className="plan-toolbar"><h3>{selectedTask.title}</h3><button type="button" onClick={() => setSelected(null)}>收起详情</button></div>
      {draft.department_assignment?.suggestions.find(s => s.ref === selected)?.reason && <p>部门判断：{draft.department_assignment.suggestions.find(s => s.ref === selected).reason}</p>}
      <p>{selectedTask.description || '暂无说明'}</p><p>完成标准：{selectedTask.completion_criteria || '待补充'}</p><p>实施人员：{selectedTask.details?.assignees?.join('、') || '待分配'}</p>
      {selectedOp.action === 'update' && <p>原安排：{current.get(selected)?.planned_start || '待定'} → {current.get(selected)?.planned_end || '待定'} · 原部门：{current.get(selected)?.details?.department || '待分配部门'}</p>}
      <p>建议安排：{selectedTask.planned_start || '待定'} → {selectedTask.planned_end || '待定'} · {selectedTask.details?.department || '待分配部门'}</p>
      {draft.warnings.filter(w => w.task_id === selected).map((w, i) => <p className="warning" key={i}>{w.message}</p>)}
      <details><summary>完整变更内容</summary><pre>{JSON.stringify(selectedOp, null, 2)}</pre></details>
      <div className="plan-actions">{selectedOp.action !== 'cancel' && <button disabled={busy || data.draft_stale || editing !== null} onClick={() => setEditing({ index: selectedIndex, value: selectedTask })}>调整建议</button>}<button disabled={busy || data.draft_stale || editing !== null} onClick={() => remove(selectedIndex)}>移除此项建议</button></div>
    </div>}
    <button disabled={busy || data.draft_stale || editing !== null} onClick={() => setEditing({ index: -1, value: emptyTask() })}>补充草稿任务</button>
    {editing && <TaskEditor peopleUnavailable={peopleUnavailable} people={people} resources={data.resource_options || []} key={editing.index} initial={editing.value} tasks={available} scenes={data.scene_options} busy={busy} draft isNew={editing.index === -1 || result.operations[editing.index]?.action === 'add'} onSave={saveTask} onCancel={() => setEditing(null)}/>}
    <details><summary>工作框架查漏 · {result.coverage.length} 项</summary><p>逐项处理不代表模型判断正确，请检查“不适用”和“已落实”的依据。</p>{result.coverage.map((c, i) => <div className="plan-constraint" key={c.check_id}><strong>{checklist.get(c.check_id) || c.check_id}</strong>
      <label>检查结果<select disabled={busy || data.draft_stale} value={c.status} onChange={e => setResult({ ...result, coverage: result.coverage.map((x, n) => n === i ? { ...x, status: e.target.value } : x) })}>{Object.entries(coverageLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label>判断依据<input disabled={busy || data.draft_stale} maxLength={1000} value={c.reason} onChange={e => setResult({ ...result, coverage: result.coverage.map((x, n) => n === i ? { ...x, reason: e.target.value } : x) })}/></label>
      <label>关联任务<select multiple size={3} disabled={busy || data.draft_stale} value={c.task_refs} onChange={e => { const task_refs = [...e.target.selectedOptions].map(o => o.value); setResult({ ...result, coverage: result.coverage.map((x, n) => n === i ? { ...x, task_refs } : x) }); }}>{available.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
    </div>)}</details>
    <div className="plan-actions"><button disabled={busy || !dirty || editing !== null || data.draft_stale} onClick={() => onSave(result)}>保存草稿修改</button><button disabled={busy || dirty || data.draft_stale} onClick={onConfirm}>确认应用 {result.operations.length} 项建议</button><button disabled={busy} onClick={onDiscard}>放弃这份草稿</button></div>
  </section>;
}
