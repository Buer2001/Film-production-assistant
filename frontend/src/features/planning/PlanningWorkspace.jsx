import React, { useCallback, useEffect, useState } from 'react';
import usePlanning from './usePlanning';
import PlanSettings from './PlanSettings';
import TaskList from './TaskList';
import TaskEvidence from './TaskEvidence';
import TaskEditor from './TaskEditor';
import PlanReview from './PlanReview';
import { emptyTask } from './api';
import './planning.css';

export default function PlanningWorkspace({ pid, onLockChange }) {
  const { data, busy, error, setError, run } = usePlanning(pid);
  const [settings, setSettings] = useState(null), [editing, setEditing] = useState(null), [reviewDirty, setReviewDirty] = useState(false), [instruction, setInstruction] = useState('');
  const [evidence, setEvidence] = useState(null);
  const settingsDirty = !!settings && !!data && JSON.stringify(settings) !== JSON.stringify(data.settings);
  const dirty = settingsDirty || editing !== null || reviewDirty;
  const reviewChange = useCallback(value => setReviewDirty(value), []);
  useEffect(() => { if (data) setSettings(data.settings); }, [data]);
  useEffect(() => { onLockChange?.(busy || dirty); return () => onLockChange?.(false); }, [busy, dirty, onLockChange]);
  useEffect(() => { const guard = e => { if (dirty || busy) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty, busy]);
  if (!data || !settings) return <section><p role="status">{busy ? '读取项目日程…' : '尚未读取日程'}</p>{error && <p role="alert" className="error">{error}</p>}<button disabled={busy} onClick={() => run()}>重试读取</button></section>;
  const revision = data.revision;
  const draft = data.draft?.status === 'pending' ? data.draft : null;
  const unavailable = busy || dirty;
  async function saveTask(value) {
    const { id, completed_at, created_at, updated_at, overdue, blocked, due_state, ...task } = value;
    const result = id ? await run(`/tasks/${id}`, { revision, changes: task }, 'PATCH') : await run('/tasks', { revision, task });
    if (result) setEditing(null);
  }
  async function generate() {
    if (draft && !window.confirm('重新生成会替换这份待确认草稿，正式任务保留。继续吗？')) return;
    await run('/generate', { revision, instruction });
  }
  return <div className="planning-workspace">
    <div className="plan-toolbar"><p>安排依据：{data.source ? `已确认剧本第 ${data.source.version_number} 版` : '尚无已确认剧本，可先填写项目情况'} · 日程版本 {revision}</p><button disabled={unavailable} onClick={() => run()}>刷新日程</button></div>
    {error && <div className="error" role="alert">{error}<button onClick={() => setError('')}>关闭</button><p>输入已保留。版本冲突时请先备份输入，再刷新核对。</p></div>}
    {busy && <p role="status">处理中；模型生成可能需要约一分钟，请勿重复提交。</p>}
    <PlanSettings value={settings} onChange={setSettings} busy={busy || editing !== null || reviewDirty} dirty={settingsDirty} onSave={() => run('/settings', { revision, settings }, 'PUT')}/>
    {settingsDirty && <button disabled={busy} onClick={() => setSettings(data.settings)}>放弃项目条件修改</button>}
    <section><h2>生成任务安排</h2><p>结合剧本和制片检查框架生成建议，覆盖筹备、拍摄、器材道具归还及结款。模型不会直接修改正式任务。</p>
      <label>这次希望如何安排或调整<textarea maxLength={4000} rows={2} disabled={busy} value={instruction} placeholder="例如：场地还没定，请优先安排；开拍提前两天，请检查已有任务。" onChange={e => setInstruction(e.target.value)}/></label>
      <div className="plan-actions"><button disabled={unavailable || !data.settings.shoot_start} onClick={generate}>{data.tasks.length ? '生成调整建议' : '生成日程建议'}</button><button disabled={unavailable} onClick={() => setEditing(emptyTask())}>人工添加任务</button></div>
      {!data.settings.shoot_start && <p className="plan-muted">先保存开拍日期，即可生成建议。</p>}
    </section>
    {data.warnings.length > 0 && <section><details><summary>正式日程提醒 · {data.warnings.length}</summary>{data.warnings.map((w, i) => <p key={i} className="warning">{data.tasks.find(t => t.id === w.task_id)?.title || '项目'}：{w.message}</p>)}</details></section>}
    {draft && <PlanReview key={draft.id} data={data} busy={busy || settingsDirty || editing !== null} onDirty={reviewChange} onSave={result => run('/draft', { revision, draft_id: draft.id, result }, 'PUT')} onConfirm={() => run('/draft/confirm', { revision, draft_id: draft.id })} onDiscard={() => { if (window.confirm('放弃待确认草稿？正式任务保留。')) run('/draft', { revision, draft_id: draft.id }, 'DELETE'); }}/ >}
    {editing && <TaskEditor key={editing.id || 'new'} initial={editing} tasks={data.tasks} scenes={[...data.scene_options, ...(editing.details?.scene_refs || []).filter(s => !data.scene_options.some(x => x.scene_id === s.scene_id))]} busy={busy} onSave={saveTask} onCancel={() => setEditing(null)}/>}
    <TaskList tasks={data.tasks} busy={unavailable} onEvidence={(task, sceneRef, trigger) => setEvidence({ task, sceneRef, trigger })} onEdit={setEditing} onStatus={(t, status) => run(`/tasks/${t.id}`, { revision, changes: { status } }, 'PATCH')}/>
    {evidence && <TaskEvidence key={`${pid}:${evidence.task.id}:${evidence.sceneRef.script_id}:${evidence.sceneRef.scene_id}`} pid={pid} {...evidence} onClose={() => setEvidence(null)}/>}
    {dirty && <p className="plan-muted" role="status">有未保存的编辑，已暂时禁止切换项目和页面。</p>}
  </div>;
}
