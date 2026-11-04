// 组织项目日程、人员资源资料、正式任务和待确认建议的编辑流程。
import React, { useCallback, useEffect, useState } from 'react';
import usePlanning from './usePlanning';
import PlanSettings from './PlanSettings';
import TaskList from './TaskList';
import TaskEvidence from './TaskEvidence';
import TaskDrawer from './TaskDrawer';
import TaskEditor from './TaskEditor';
import PlanReview from './PlanReview';
import { emptyTask } from './api';
import { departmentTargets } from './timeline';
import './planning.css';
import { api } from '../../api/client';
import PeoplePanel, { createPersonDraft } from '../preparation/PeoplePanel';
import ResourcePanel, { createResourceDraft } from '../resources/ResourcePanel';
import AvailabilityBoard from '../preparation/AvailabilityBoard';
import { buildWeek, periodLabel, todayKey } from '../preparation/availability';

/**
 * 参数：pid 为项目 ID，onLockChange 接收是否禁止切换页面。返回日程工作区 JSX。
 * 人员和资源随日程快照重读；任一表单未保存或资料正在写入时锁定导航，并注册离页提示。
 */
export default function PlanningWorkspace({ pid, onLockChange }) {
  const { data, busy, error, setError, run } = usePlanning(pid);
  const [settings, setSettings] = useState(null), [editing, setEditing] = useState(null), [reviewDirty, setReviewDirty] = useState(false), [instruction, setInstruction] = useState('');
  const [evidence, setEvidence] = useState(null);
  const [panel, setPanel] = useState(null);
  const [view, setView] = useState('tasks'), [selection, setSelection] = useState(null);
  const [resourceEditing, setResourceEditing] = useState(null), [resourceBusy, setResourceBusy] = useState(false);
  const [peopleEditing, setPeopleEditing] = useState(null), [peopleBusy, setPeopleBusy] = useState(false);
  const [support, setSupport] = useState({ people: [], revision: null, preparation: null, error: '', loading: true });
  // 检查刷新期间保留缓存供状态管理，但不展示为当前结果，避免失败时沿用旧的无缺口结论。
  // 人员与资源共享项目版本；每次日程刷新都重新读取，取消标记防止旧项目响应覆盖新项目。
  useEffect(() => {
    let cancelled = false;
    setSupport(x => ({ ...x, loading: true, error: '' }));
    Promise.all([api(`/projects/${pid}/people`), api(`/projects/${pid}/preparation`)])
      .then(([people, preparation]) => { if (!cancelled) setSupport({ people: people.people, revision: people.revision, preparation, error: '', loading: false }); })
      .catch(e => { if (!cancelled) setSupport(x => ({ ...x, loading: false, error: e.message })); });
    return () => { cancelled = true; };
  }, [pid, data]);
  const materialsBusy = resourceBusy || peopleBusy || support.loading;
  const materialsEditing = resourceEditing !== null || peopleEditing !== null;
  const settingsDirty = !!settings && !!data && JSON.stringify(settings) !== JSON.stringify(data.settings);
  const dirty = settingsDirty || editing !== null || reviewDirty || materialsEditing;
  const reviewChange = useCallback(value => setReviewDirty(value), []);
  useEffect(() => { if (data) setSettings(data.settings); }, [data]);
  useEffect(() => { onLockChange?.(busy || materialsBusy || dirty); return () => onLockChange?.(false); }, [busy, materialsBusy, dirty, onLockChange]);
  useEffect(() => { const guard = e => { if (dirty || busy || materialsBusy) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty, busy, materialsBusy]);
  if (!data || !settings) return <section><p role="status">{busy ? '读取项目日程…' : '尚未读取日程'}</p>{error && <p role="alert" className="error">{error}</p>}<button disabled={busy} onClick={() => run()}>重试读取</button></section>;
  const revision = data.revision;
  const draft = data.draft?.status === 'pending' ? data.draft : null;
  const unavailable = busy || materialsBusy || dirty || !!support.error;
  const missingDepartments = departmentTargets(data.tasks, draft ? draft.result.operations : null).length;
  const resources = data.resource_options || [];
  // 详情始终从最新快照派生，保存后不沿用选中时的旧对象或旧档期结论。
  const selectedWeek = selection ? buildWeek({ date: selection.date, kind: selection.kind, people: support.people, resources, tasks: data.tasks }) : null;
  const selectedRow = selectedWeek?.rows.find(row => row.id === selection.entityId);
  const selectedCell = selectedRow?.cells.find(cell => cell.date === selection.date);
  const selectedAllocation = selectedCell?.allocations.find(item => item.task.id === selection.taskId);
  const selectedTask = selectedAllocation?.task;

  /** 切换只读视图；已有编辑或请求时由按钮禁用保护，不丢弃未保存资料。 */
  function changeView(next) {
    if (unavailable) return;
    setView(next); setSelection(null);
  }
  /** 打开独立人员/资源副本；addPeriod 时按用户选中的日期预填待保存时段。 */
  function editMaterial(addPeriod = false) {
    if (unavailable || !selectedRow) return;
    const period = { start_date: selection.date, end_date: selection.date, start_time: null, end_time: null, state: 'available' };
    if (view === 'people') {
      const value = createPersonDraft(selectedRow.entity);
      if (addPeriod) value.availability = [...(value.availability || []), period];
      setPeopleEditing(value);
    } else {
      const value = structuredClone(selectedRow.entity);
      if (addPeriod) value.data.preparation = { ...(value.data.preparation || {}), availability: [...(value.data.preparation?.availability || []), period] };
      setResourceEditing(value);
    }
  }
  /** 新建资料默认不声明任何可用时间；用户在侧栏明确录入后才保存。 */
  function addMaterial() {
    if (unavailable) return;
    setSelection(null);
    if (view === 'people') setPeopleEditing(createPersonDraft());
    else setResourceEditing(createResourceDraft());
  }
  /** 从档期或补资料提示进入原任务编辑器，保留既有任务字段及日程版本校验。 */
  function openTask(task) {
    if (unavailable) return;
    setView('tasks'); setSelection(null); setEditing(structuredClone(task));
  }
  /** 筹备提示直接定位到相应档期对象；缺失的对象仍明确提示，不猜测替代记录。 */
  function inspectMaterial(kind, id) {
    setView(kind); setSelection({ kind, entityId: id, date: todayKey(), taskId: null });
  }
  /**
   * 参数 value 为编辑后的任务；剔除服务端派生字段，以当前 revision 新增或更新，成功后关闭编辑器。
   */
  async function saveTask(value) {
    const { id, completed_at, created_at, updated_at, overdue, blocked, due_state, ...task } = value;
    const result = id ? await run(`/tasks/${id}`, { revision, changes: task }, 'PATCH') : await run('/tasks', { revision, task });
    if (result) setEditing(null);
  }
  /**
   * 按当前版本和补充要求生成草稿；覆盖已有待确认建议前询问用户，正式任务仍由后续确认应用。
   */
  async function generate() {
    if (draft && !window.confirm('重新生成会替换这份待确认草稿，正式任务保留。继续吗？')) return;
    await run('/generate', { revision, instruction });
  }
  return <div className="planning-workspace">
    <nav className="planning-view-tabs" aria-label="项目日程视图">
      {[['tasks', '任务日程'], ['people', '人员档期'], ['resources', '资源档期']].map(([key, label]) => <button key={key} type="button" aria-pressed={view === key} disabled={unavailable} onClick={() => changeView(key)}>{label}</button>)}
    </nav>
    {support.error && <p className="error" role="alert">人员或筹备检查读取失败：{support.error}。当前人员资料可能已过期，已暂停新增关联；请重新读取。<button disabled={busy || dirty} onClick={() => run()}>重新读取</button></p>}
    {error && !editing && <p className="error" role="alert">{error}<button disabled={dirty || busy} onClick={() => run()}>重新读取</button></p>}
    {view !== 'tasks' && (support.loading || support.error ? <p role="status">档期资料尚不可用，请等待或重新读取。</p> : <AvailabilityBoard kind={view} people={support.people} resources={resources} tasks={data.tasks} busy={unavailable} selected={selection} onSelect={setSelection} onAdd={addMaterial} onIncomplete={openTask}>
      {(selection || materialsEditing) && <div className="availability-inspector">
        <header><h3>{peopleEditing || resourceEditing ? '编辑资料及档期' : selectedTask?.title || selectedRow?.name || '档期详情'}</h3>{selection && <button type="button" disabled={materialsEditing || materialsBusy} onClick={() => setSelection(null)}>关闭详情</button>}</header>
        {peopleEditing ? <PeoplePanel editorOnly pid={pid} people={support.people} revision={support.revision} disabled={false} editing={peopleEditing} onEditing={setPeopleEditing} onBusy={setPeopleBusy} onChanged={() => run()}/> : resourceEditing ? <ResourcePanel editorOnly pid={pid} people={support.people} resources={resources} revision={data.resource_revision} disabled={false} editing={resourceEditing} onEditing={setResourceEditing} onBusy={setResourceBusy} onChanged={() => run()}/> : selectedRow ? <>
          <p>{selectedRow.subtitle} · {selectedRow.name}</p>
          <h4>备注</h4><p className="preserve-lines">{(view === 'people' ? selectedRow.entity.notes : selectedRow.entity.data.preparation?.notes) || '暂无备注'}</p>
          {view === 'resources' && selectedRow.entity.data.notes && <><h4>原有资源说明</h4><p className="preserve-lines">{selectedRow.entity.data.notes}</p></>}
          <p className="plan-muted">所选日期：{selection.date} · {selectedCell?.label}</p>
          {selectedTask ? <>
            <h4>计划使用时段</h4><p>{periodLabel(selectedAllocation.period)}</p>
            {selectedAllocation.overlapIds.length > 0 && <div className="warning"><strong>重叠待核对</strong><p>同一人员或资源在这些任务中存在时间重叠，不等同于已经确认冲突。</p><ul>{selectedAllocation.overlapIds.map(id => <li key={id}>{data.tasks.find(task => task.id === id)?.title || '关联任务已变化'}</li>)}</ul></div>}
            {selectedAllocation.availabilityIssue && <p className="warning">{selectedAllocation.availabilityIssue}</p>}
            <h4>任务备注 / 落实结果</h4><p className="preserve-lines">{selectedTask.details?.result_notes || selectedTask.description || '暂无备注'}</p>
            <h4>关联人员</h4><p>{(selectedTask.details?.person_ids || []).map(id => support.people.find(person => person.id === id)?.name || '人员资料不可用').join('、') || '尚未关联人员'}</p>
            <h4>关联资源</h4><p>{(selectedTask.details?.resource_refs || []).map(ref => resources.find(resource => resource.id === ref.record_id)?.data.title || ref.name || '资源资料不可用').join('、') || '尚未关联资源'}</p>
            <button type="button" disabled={unavailable} onClick={() => openTask(selectedTask)}>查看 / 编辑任务</button>
          </> : <>
            <h4>已登记可用情况</h4>
            {(view === 'people' ? selectedRow.entity.availability : selectedRow.entity.data.preparation?.availability)?.length ? <ul>{(view === 'people' ? selectedRow.entity.availability : selectedRow.entity.data.preparation.availability).map((period, i) => <li key={i}>{period.state === 'available' ? '可用' : '不可用'}：{periodLabel(period)}</li>)}</ul> : <p>尚未登记可用时间，不代表全天可用。</p>}
            <h4>当天安排</h4>{selectedCell?.allocations.length ? <ul>{selectedCell.allocations.map(item => <li key={item.task.id}><button type="button" disabled={unavailable} onClick={() => setSelection({ ...selection, taskId: item.task.id })}>{item.label} · {item.task.title}</button></li>)}</ul> : <p>没有已关联且填写了计划使用时段的安排。</p>}
          </>}
          <h4>关联任务</h4>{data.tasks.filter(task => task.status !== 'cancelled' && (view === 'people' ? (task.details.person_ids || []).includes(selectedRow.id) : (task.details.resource_refs || []).some(ref => ref.record_id === selectedRow.id))).map(task => <p key={task.id}><button type="button" disabled={unavailable} onClick={() => openTask(task)}>{task.title}</button></p>)}
          <button type="button" disabled={unavailable} onClick={() => { const task = emptyTask(); task.details.usage_period = { start_date: selection.date, end_date: selection.date }; if (view === 'people') { task.details.person_ids = [selectedRow.id]; task.details.requires_people = true; } else task.details.resource_refs = [{ record_id: selectedRow.id, name: selectedRow.name }]; changeView('tasks'); setEditing(task); }}>新建关联任务</button>
          <div className="plan-actions"><button type="button" disabled={unavailable} onClick={() => editMaterial(true)}>添加档期</button><button type="button" disabled={unavailable} onClick={() => editMaterial()}>编辑资料</button></div>
        </> : <p className="plan-muted">{selection ? '资料已变化或已删除，请刷新后重新选择。' : '点击姓名、资源名称或日期格查看档期；点击深绿安排查看关联任务。'}</p>}
      </div>}
    </AvailabilityBoard>)}
    {view === 'tasks' && <>
    <div className="plan-toolbar task-main-actions"><p className="plan-muted">{data.tasks.length} 项任务 · {data.settings.shoot_start ? `${data.settings.shoot_start} 开拍` : '开拍日期待定'}</p><div className="plan-actions">
      <button disabled={unavailable} onClick={() => setEditing(emptyTask())}>新建任务</button>
      <button disabled={unavailable} aria-pressed={panel === 'ai'} onClick={() => setPanel(panel === 'ai' ? null : 'ai')}>AI 建议{draft ? ' · 待确认' : ''}</button>
      <button disabled={unavailable} aria-pressed={panel === 'settings'} onClick={() => setPanel(panel === 'settings' ? null : 'settings')}>项目设置</button>
      <button disabled={unavailable} onClick={() => run()}>刷新</button>
    </div></div>
    {panel === 'settings' && <section className="task-settings"><h2>项目设置</h2>
    <PlanSettings value={settings} onChange={setSettings} busy={busy || materialsBusy || materialsEditing || editing !== null || reviewDirty} dirty={settingsDirty} onSave={() => run('/settings', { revision, settings }, 'PUT')}/>
    {settingsDirty && <button disabled={busy} onClick={() => setSettings(data.settings)}>放弃项目条件修改</button>}
    </section>}
    {panel === 'ai' && <section><h2>AI 日程建议</h2><button disabled={unavailable || data.draft_stale || missingDepartments === 0} onClick={() => run('/departments', { revision })}>补全空白部门 · {missingDepartments}</button><p className="plan-muted">只为空白部门提出建议，已有安排保留；确认后才应用。</p>
    <section><h2>生成任务安排</h2><p>结合剧本和制片检查框架生成建议，覆盖筹备、拍摄、器材道具归还及结款。模型不会直接修改正式任务。</p>
      <label>这次希望如何安排或调整<textarea maxLength={4000} rows={2} disabled={busy} value={instruction} placeholder="例如：场地还没定，请优先安排；开拍提前两天，请检查已有任务。" onChange={e => setInstruction(e.target.value)}/></label>
      <div className="plan-actions"><button disabled={unavailable || !data.settings.shoot_start} onClick={generate}>{data.tasks.length ? '生成调整建议' : '生成日程建议'}</button></div>
      {!data.settings.shoot_start && <p className="plan-muted">先保存开拍日期，即可生成建议。</p>}
    </section>
    </section>}
    {support.loading && <p role="status">筹备检查更新中…</p>}
    {support.preparation && !support.loading && !support.error && <section className="task-check-summary"><details><summary>筹备检查 · 已检查 {support.preparation.checked_tasks} 项任务 · {support.preparation.issues.length} 条提示</summary><p className="plan-muted">基于当前已关联的人员、资源和使用时段检查；未关联或尚未填写时段的任务不能据此认定档期无问题。</p>{support.preparation.issues.length === 0 && <p>已关联资料未发现筹备缺口。<button type="button" disabled={unavailable} onClick={() => changeView('people')}>查看档期及待补资料</button></p>}{support.preparation.issues.map((issue, i) => <p className="warning" key={i}>{data.tasks.find(t => t.id === issue.task_id)?.title || '项目'}：{issue.message} <button type="button" disabled={unavailable} onClick={() => {
      if (issue.resource_id || issue.person_id) {
        inspectMaterial(issue.resource_id ? 'resources' : 'people', issue.resource_id || issue.person_id);
      } else { const task = data.tasks.find(t => t.id === issue.task_id); if (task) setEditing(task); }
    }}>查看{issue.resource_id ? '资源' : issue.person_id ? '人员' : '任务'}</button></p>)}</details></section>}
    {data.warnings.length > 0 && <section className="task-check-summary"><details><summary>正式日程提醒 · {data.warnings.length}</summary>{data.warnings.map((w, i) => <p key={i} className="warning">{data.tasks.find(t => t.id === w.task_id)?.title || '项目'}：{w.message}</p>)}</details></section>}
    {draft && <PlanReview peopleUnavailable={support.loading || !!support.error} people={support.people} key={draft.id} data={data} busy={busy || materialsBusy || materialsEditing || settingsDirty || editing !== null} onDirty={reviewChange} onSave={result => run('/draft', { revision, draft_id: draft.id, result }, 'PUT')} onConfirm={() => run('/draft/confirm', { revision, draft_id: draft.id })} onDiscard={() => { if (window.confirm('放弃待确认草稿？正式任务保留。')) run('/draft', { revision, draft_id: draft.id }, 'DELETE'); }}/ >}
    {editing && <TaskDrawer title={editing.id ? '编辑任务' : '新建任务'} busy={busy} onClose={() => setEditing(null)}>{error && <p className="error" role="alert">{error}</p>}<TaskEditor peopleUnavailable={support.loading || !!support.error} people={support.people} resources={data.resource_options || []} key={editing.id || 'new'} initial={editing} tasks={data.tasks} scenes={[...data.scene_options, ...(editing.details?.scene_refs || []).filter(s => !data.scene_options.some(x => x.scene_id === s.scene_id))]} busy={busy} onSave={saveTask} onCancel={() => setEditing(null)}/></TaskDrawer>}
    <TaskList error={error} people={support.people} resources={data.resource_options || []} tasks={data.tasks} settings={data.settings} warnings={data.warnings} busy={unavailable} onEvidence={(task, sceneRef, trigger) => setEvidence({ task, sceneRef, trigger })} onEdit={setEditing} onStatus={(t, status) => run(`/tasks/${t.id}`, { revision, changes: { status } }, 'PATCH')}/>
    {evidence && <TaskEvidence key={`${pid}:${evidence.task.id}:${evidence.sceneRef.script_id}:${evidence.sceneRef.scene_id}`} pid={pid} {...evidence} onClose={() => setEvidence(null)}/>}
    </>}
    {dirty && <p className="plan-muted" role="status">有未保存的编辑，已暂时禁止切换项目和页面。</p>}
  </div>;
}
