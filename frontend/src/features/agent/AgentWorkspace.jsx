// 制片助手：发起编排、补充信息、审阅联合草稿并确认执行。
import React, { useCallback, useEffect, useState } from 'react';
import { agentApi } from './api';
import { api } from '../../api/client';
import { fieldLabel } from '../../workspace';
import DraftEditor from './DraftEditor';
import { actionLabels, changedFields, entityLabels, groupIssues, groupOperations,
  levelLabels, operationTitle, statusLabels, uncoveredText } from './agentDraft';

const phaseLabels = { all: '全部阶段', preparation: '筹备', shooting: '拍摄', closing: '收尾' };
const reflectLabels = { ok: '模型复核通过', fixable: '模型复核要求修正', need_user: '模型复核需要制片决定',
  skipped_manual: '制片直接提交，未做模型复核' };
const stepLabels = { understand: '理解要求', load: '读取资料', impact: '分析影响', propose: '生成候选',
  validate: '程序检查', reflect: '模型复核', revise: '修正方案', save_draft: '保存草稿',
  review: '等待审阅', preflight: '执行前复核', apply: '执行', report: '汇总结果', feedback: '记录反馈' };

/**
 * 参数：value 为字段值。返回：适合直接显示的短文本，未知值一律显示待定。
 */
function formatValue(value, references = {}) {
  if (value === null || value === undefined || value === '') return '待定';
  if (Array.isArray(value)) return value.length ? value.map(item => formatValue(item, references)).join('、') : '无';
  if (typeof value === 'object') return Object.entries(value).map(([key,item]) => `${fieldLabel(key)}：${formatValue(item,references)}`).join('；');
  const names = {todo:'待办',in_progress:'进行中',completed:'已完成',cancelled:'已取消',planned:'已安排',
    preparation:'筹备',shooting:'拍摄',closing:'收尾',shoot:'场次拍摄',meal:'用餐',transfer:'转场',makeup:'妆造',lighting:'布光',set:'置景',other:'其他'};
  return references[value] || names[value] || (typeof value === 'boolean' ? (value ? '是' : '否') : String(value));
}

/**
 * 参数：run 为运行详情，busy 控制操作，其余为补充输入和回调。
 * 返回：当前工作的阶段、问题、待审草稿和执行结果；等待补充与等待审阅的操作分开呈现。
 */
function RunPanel({ run, busy, answer, setAnswer, acceptUncovered, setAcceptUncovered,
  editing, setEditing, onResume, onDiscardRun, onConfirm, onDiscardDraft, onSaveDraft, references = {} }) {
  const draft = run.draft;
  const validation = draft ? draft.validation : run.validation;
  const issues = groupIssues(validation);
  const groups = groupOperations(draft ? draft.operations : []);
  const uncovered = (validation && validation.uncovered) || [];
  const waitingInput = run.status === 'waiting_input';
  const waitingReview = run.status === 'waiting_review';
  return <div>
    <h2>{run.mode === 'reschedule' ? '调整方案' : '计划草稿'}</h2><p className="request-brief">{run.message || '本次工作'}</p>
    <p>状态：{statusLabels[run.status] || run.status} · 当前步骤：{stepLabels[run.current_step] || run.current_step}
      {run.mode === 'reschedule' ? ' · 条件变化后重排' : ' · 协助编排'}</p>
    {run.scope && <p>范围：{phaseLabels[run.scope.phase] || run.scope.phase}
      {run.scope.start_date && run.scope.end_date ? ` · ${run.scope.start_date} 至 ${run.scope.end_date}` : ' · 未指定日期'}</p>}

    {waitingInput && <div>
      <h3>需要你补充</h3>
      {run.questions.length > 0 && <ul>{run.questions.map((question, index) =>
        <li key={index}>{question}</li>)}</ul>}
      <label>补充说明<textarea rows={3} maxLength={4000} value={answer}
        onChange={event => setAnswer(event.target.value)}/></label>
      <div className="plan-actions">
        <button disabled={busy || !answer.trim()} onClick={() => onResume('provide_input')}>提交补充并继续</button>
        <button disabled={busy} onClick={() => onResume('discard')}>放弃这次工作</button>
      </div>
    </div>}

    {waitingReview && draft && <div>
      <h3>待确认的联合草稿</h3>
      <p>以下内容尚未写入正式数据。修改或取消会保留原有记录，确认后才统一执行。</p>
      {draft.rationale?.summary && <p>{draft.rationale.summary}</p>}
      {draft.rationale?.assumptions?.length > 0 && <details><summary>方案假设 · {draft.rationale.assumptions.length} 项</summary><ul>{draft.rationale.assumptions.map((text,index) => <li key={index}>{text}</li>)}</ul></details>}
      {run.impact && <p>本次分析涉及 {run.impact.task_ids?.length || 0} 项任务、{run.impact.item_ids?.length || 0} 条拍摄安排。具体修改如下。</p>}
      {run.reflect_status && <p>{reflectLabels[run.reflect_status] || run.reflect_status}</p>}
      {validation && validation.counts && <p>共 {validation.counts.task} 项任务调整、{validation.counts.shooting} 项拍摄安排调整。</p>}
      {['project_task', 'shooting_item'].map(entity => groups[entity].length > 0 && <details key={entity} open>
        <summary>{entityLabels[entity]} · {groups[entity].length} 项</summary>
        {groups[entity].map(op => <div className="record" key={op.op_id}>
          <div><strong>{actionLabels[op.action] || op.action} · {operationTitle(op)}</strong>
            {op.reason && <p>{op.reason}</p>}
            {changedFields(op).map(field => <p key={field.key}>
              {fieldLabel(field.key)}：{formatValue(field.before, references)} → {formatValue(field.after, references)}</p>)}
          </div>

        </div>)}
      </details>)}
      {['block', 'conflict', 'gap'].map(level => issues[level].length > 0 && <details key={level} open={level === 'block'}>
        <summary>{levelLabels[level]} · {issues[level].length}</summary>
        {issues[level].map((issue, index) => <p key={index} className={level === 'block' ? 'warning' : ''}>
          {issue.message}</p>)}
      </details>)}
      {uncovered.length > 0 && <div className="warning">
        <p>仍有场次没有安排拍摄：{uncoveredText(uncovered)}</p>
        <label><input type="checkbox" checked={acceptUncovered}
          onChange={event => setAcceptUncovered(event.target.checked)}/> 我已知情并同意先保留这些场次</label>
      </div>}
      <div className="plan-actions">
        <button className="primary" disabled={busy || Boolean(editing) || (uncovered.length > 0 && !acceptUncovered)} onClick={onConfirm}>
          确认执行这份草稿</button>
        <button disabled={busy || Boolean(editing)} onClick={onDiscardDraft}>放弃草稿</button>
      </div>
      {editing ? <DraftEditor operations={editing} busy={busy} onChange={setEditing} onSave={onSaveDraft} onCancel={() => setEditing(null)}/> : <button disabled={busy} onClick={() => setEditing(structuredClone(draft.operations))}>修改这份草稿</button>}

    </div>}

    {run.execution && <div>
      <h3>执行结果</h3>
      <p>已写入 {Object.keys(run.execution.task_ids || {}).length} 项任务、
        {Object.keys(run.execution.item_ids || {}).length} 项拍摄安排。</p>
      {run.execution.diff && run.execution.diff.edited && <p>
        相比建议稿，最终稿改动了 {run.execution.diff.changes.length} 项，已记入执行记录。</p>}
      {run.execution.notices && run.execution.notices.length > 0 && <div className="warning">
        <p>以下已发布通告受影响，请复核后重新发布：</p>
        <ul>{run.execution.notices.map(notice => <li key={notice.notice_id}>
          {notice.date} 通告 V{notice.version}：{(notice.reasons || []).join('；')}</li>)}</ul>
      </div>}
      {run.execution.uncovered && run.execution.uncovered.length > 0 && <p>
        知情保留、本次未安排的场次：{uncoveredText(run.execution.uncovered)}</p>}
    </div>}

    {run.status === 'running' && <p>正在处理，请稍候。</p>}
    {run.status === 'abandoned' && <p>这次工作已放弃，没有修改正式数据。</p>}
    {!waitingReview && !waitingInput && run.draft && run.status !== 'completed' && <p>
      草稿状态：{run.draft.status}</p>}
  </div>;
}

/**
 * 参数：pid 为项目 ID，onLockChange 通知父层锁定切换，onChanged 在写入后刷新项目概览。
 * 返回：制片助手界面；发起、补充、审阅、确认都在这里完成。
 */
export default function AgentWorkspace({ pid, onLockChange, onChanged, initialIntent = '', initialRunId = '' }) {
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(null);
  const [message, setMessage] = useState(initialIntent ? '根据已确认剧本和项目条件，生成拍摄大计划草稿。保留已有安排，只补充遗漏并提出必要调整，列出待确认估时及准备缺口。' : '');
  const [mode, setMode] = useState('compose');
  const [target, setTarget] = useState(initialIntent ? 'shooting' : 'both');
  const [context, setContext] = useState(null);
  const [scope, setScope] = useState({ phase: 'all', start_date: '', end_date: '' });
  const [answer, setAnswer] = useState('');
  const [acceptUncovered, setAcceptUncovered] = useState(false);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // 未保存的要求、补充及草稿编辑均锁定导航；处理期间也禁止切换，避免迟到结果归属混乱。
  useEffect(() => { if (onLockChange) onLockChange(Boolean(editing) || busy || Boolean(message.trim()) || Boolean(answer.trim())); }, [editing, busy, message, answer, onLockChange]);
  useEffect(() => { const guard = e => { if (editing || message.trim() || answer.trim() || busy) { e.preventDefault(); e.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [editing, message, answer, busy]);

  const act = useCallback(async task => {
    setBusy(true);
    setError('');
    try {
      return await task();
    } catch (caught) {
      setError(caught.message);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    const list = await agentApi(pid, '/runs', undefined, 'GET');
    setRuns(list);
    return list;
  }, [pid]);

  const open = useCallback(async id => {
    const detail = await agentApi(pid, `/runs/${id}`, undefined, 'GET');
    setRun(detail);
    setAnswer('');
    setAcceptUncovered(false);
    setEditing(null);
    return detail;
  }, [pid]);

  useEffect(() => {
    if (!pid) return undefined;
    setRun(null);
    act(async () => {
      const list = await refresh();
      if (initialRunId) await open(initialRunId); else if (list.length && !initialIntent) await open(list[0].id);
      const [plan, shooting] = await Promise.all([api(`/projects/${pid}/planning`), api(`/projects/${pid}/shooting`)]);
      setContext({plan, shooting});
      setScope(x => ({...x, start_date: plan.settings.shoot_start || '', end_date: plan.settings.shoot_end || plan.settings.shoot_start || ''}));
    });
    return () => { if (onLockChange) onLockChange(false); };
  }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 参数：event 为表单事件。按说明发起一次工作，范围留空时由助手自行判断。
   */
  async function startWork(event) {
    event.preventDefault();
    const targetText = target === 'shooting' ? '本次只调整拍摄安排，不修改项目任务。' : target === 'tasks' ? '本次只调整项目任务，不修改拍摄安排。' : '本次允许联合调整项目任务和拍摄安排。';
    const body = { message: `${message}\n${targetText}`, mode };
    if (scope.start_date && scope.end_date) {
      body.scope = { phase: scope.phase, start_date: scope.start_date, end_date: scope.end_date, include_tasks: target !== 'shooting', include_shooting: target !== 'tasks' };
    }
    await act(async () => {
      const created = await agentApi(pid, '/runs', body);
      setRun(created);
      setMessage('');
      await refresh();
    });
  }

  /**
   * 参数：decision 为 provide_input 或 discard。补充后重新读取正式资料继续推进。
   */
  async function resume(decision) {
    const body = { expected_version: run.version, decision };
    if (decision === 'provide_input' && answer.trim()) body.message = answer;
    await act(async () => {
      await agentApi(pid, `/runs/${run.id}/resume`, body);
      await open(run.id);
      setAnswer('');
      await refresh();
    });
  }

  async function confirmDraft() {
    await act(async () => {
      await agentApi(pid, `/drafts/${run.draft.id}/confirm`,
        { revision: run.draft.revision, accept_uncovered: acceptUncovered });
      await open(run.id);
      await refresh();
      if (onChanged) onChanged();
    });
  }

  async function discardDraft() {
    await act(async () => {
      await agentApi(pid, `/drafts/${run.draft.id}`, { revision: run.draft.revision }, 'DELETE');
      await open(run.id);
      await refresh();
    });
  }

  /**
   * 保存表单编辑后的操作列表；沿用草稿版本检查，失败保留本地编辑。
   */
  async function saveDraft() {
    const operations = editing;
    if (!Array.isArray(operations)) return;
    await act(async () => {
      await agentApi(pid, `/runs/${run.id}/draft`,
        { revision: run.draft.revision, candidate: { origin: 'manual', operations, summary: run.draft.rationale?.summary || '', assumptions: run.draft.rationale?.assumptions || [], questions: run.draft.rationale?.questions || [] } }, 'PUT');
      await open(run.id);
    });
  }

  if (!pid) return <section><p>先选择或创建一个项目。</p></section>;
  const dirty = Boolean(editing) || Boolean(message.trim()) || Boolean(answer.trim());
  function newWork() { setRun(null); setAnswer(''); setAcceptUncovered(false); }
  return <div className="agent-layout">
    <aside className="agent-history"><button className="primary" disabled={busy || dirty} onClick={newWork}>＋ 新建工作</button><div className="section-heading"><h2>最近工作</h2><button disabled={busy || dirty} onClick={() => act(refresh)}>刷新</button></div>
      {!runs.length && <p>生成的计划和调整记录会保存在这里。</p>}
      {runs.map(item => <button className={`work-item ${run?.id === item.id ? 'selected' : ''}`} disabled={busy || dirty} key={item.id} onClick={() => act(() => open(item.id))}><strong>{item.message?.split('\n')[0] || '计划调整'}</strong><span>{statusLabels[item.status] || item.status}</span></button>)}
    </aside>
    <div className="agent-content">
      {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>关闭</button></div>}
      {busy && <p className="processing" role="status">正在读取资料、生成或检查方案，请稍候。完成后会在这里显示结果。</p>}
      {run && <ol className="work-progress" aria-label="处理阶段">{[['理解要求',['understand','load','impact','clarify']],['生成检查',['propose','validate','reflect','revise','save_draft']],['审阅确认',['review','preflight']],['执行完成',['apply','report','feedback']]].map(([label,steps]) => <li key={label} aria-current={steps.includes(run.current_step) ? 'step' : undefined}>{label}</li>)}</ol>}
      {!run ? <section className="agent-compose"><h2>这次需要做什么？</h2><p>说明目标，助手生成草稿；你审阅确认后再应用。</p>
        <div className="mode-options" role="group" aria-label="助手工作模式"><button type="button" disabled={busy} aria-pressed={mode === 'compose'} onClick={() => setMode('compose')}><strong>生成计划</strong><span>从现有资料编排任务和拍摄安排</span></button><button type="button" disabled={busy} aria-pressed={mode === 'reschedule'} onClick={() => setMode('reschedule')}><strong>调整已有计划</strong><span>分析条件变化，尽量保留无关安排</span></button></div>
        {context && <div className="context-strip"><strong>本次可参考的项目资料</strong><span>{context.shooting.scenes.length} 场正式剧本 · {context.plan.tasks.length} 项任务 · {context.shooting.items.filter(i => i.data.status !== 'cancelled').length} 条安排</span><span>开拍 {context.plan.settings.shoot_start || '待设置'} · 杀青 {context.plan.settings.shoot_end || '待设置'}</span></div>}
        <form onSubmit={startWork}>
          <label>处理内容<select disabled={busy} value={target} onChange={e => setTarget(e.target.value)}><option value="both">项目任务和拍摄安排</option><option value="shooting">拍摄大计划</option><option value="tasks">项目日程任务</option></select></label>
          <label>你的要求<textarea rows={4} disabled={busy} maxLength={4000} value={message} placeholder={mode === 'compose' ? '希望拍哪些场次？有哪些固定时间或优先要求？' : '什么条件变了？哪些安排必须保留？'} onChange={e => setMessage(e.target.value)}/></label>
          <div className="example-prompts"><small>试试：</small>{(mode === 'compose' ? ['按同场地集中拍摄，生成拍摄大计划', '检查筹备缺口，补充开拍前任务'] : ['教室当天不能用，分析影响并提出改期方案', '开拍提前，检查受影响任务和拍摄安排']).map(text => <button type="button" disabled={busy} key={text} onClick={() => setMessage(text)}>{text}</button>)}</div>
          <div className="columns"><label>开始日期<input type="date" required={Boolean(scope.end_date)} disabled={busy} value={scope.start_date} onChange={e => setScope({...scope,start_date:e.target.value})}/></label><label>结束日期<input type="date" required={Boolean(scope.start_date)} disabled={busy} min={scope.start_date || undefined} value={scope.end_date} onChange={e => setScope({...scope,end_date:e.target.value})}/></label></div>
          <details><summary>更多范围设置</summary><label>任务阶段<select disabled={busy} value={scope.phase} onChange={e => setScope({...scope,phase:e.target.value})}>{Object.entries(phaseLabels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label><p>日期已按项目节点建议填写，可以修改。留空时助手需判断范围；有明确限制请写入要求。</p></details>
          <div className="form-actions"><button className="primary" disabled={busy || !message.trim()}> {mode === 'compose' ? '生成计划草稿' : '分析影响并生成调整草稿'}</button>{message && <button type="button" disabled={busy} onClick={() => setMessage('')}>清空要求</button>}</div>
        </form>
      </section> : <section className="agent-result"><RunPanel run={run} busy={busy} answer={answer} setAnswer={setAnswer} acceptUncovered={acceptUncovered} setAcceptUncovered={setAcceptUncovered} editing={editing} setEditing={setEditing} onResume={resume} onDiscardRun={() => resume('discard')} onConfirm={confirmDraft} onDiscardDraft={discardDraft} onSaveDraft={saveDraft} references={Object.fromEntries([
        ...(context?.shooting.people || []).map(p => [p.id,p.name]),
        ...(context?.shooting.resources || []).map(r => [r.id,r.data.title]),
        ...(context?.shooting.scenes || []).map(scene => [scene.id,`第${scene.scene_number}场 · ${scene.location}`]),
        ...(context?.plan.tasks || []).map(task => [task.id,task.title]),
      ])}/></section>}
    </div>
  </div>;
}
