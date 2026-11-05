// 制片助手：发起编排、补充信息、审阅联合草稿并确认执行。
import React, { useCallback, useEffect, useState } from 'react';
import { agentApi } from './api';
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
function formatValue(value) {
  if (value === null || value === undefined || value === '') return '待定';
  if (Array.isArray(value)) return value.length ? value.join('、') : '无';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

/**
 * 参数：run 为运行详情，busy 控制操作，其余为补充输入和回调。
 * 返回：当前工作的阶段、问题、待审草稿和执行结果；等待补充与等待审阅的操作分开呈现。
 */
function RunPanel({ run, busy, answer, setAnswer, acceptUncovered, setAcceptUncovered,
  editing, setEditing, onResume, onDiscardRun, onConfirm, onDiscardDraft, onSaveDraft }) {
  const draft = run.draft;
  const validation = draft ? draft.validation : run.validation;
  const issues = groupIssues(validation);
  const groups = groupOperations(draft ? draft.operations : []);
  const uncovered = (validation && validation.uncovered) || [];
  const waitingInput = run.status === 'waiting_input';
  const waitingReview = run.status === 'waiting_review';
  return <div>
    <h2>{run.message || '本次工作'}</h2>
    <p>状态：{statusLabels[run.status] || run.status} · 当前步骤：{stepLabels[run.current_step] || run.current_step}
      · 版本 {run.version}{run.mode === 'reschedule' ? ' · 条件变化后重排' : ' · 协助编排'}</p>
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
      {run.reflect_status && <p>{reflectLabels[run.reflect_status] || run.reflect_status}</p>}
      {validation && validation.counts && <p>共 {validation.counts.task} 项任务调整、{validation.counts.shooting} 项拍摄安排调整。</p>}
      {['project_task', 'shooting_item'].map(entity => groups[entity].length > 0 && <details key={entity} open>
        <summary>{entityLabels[entity]} · {groups[entity].length} 项</summary>
        {groups[entity].map(op => <div className="record" key={op.op_id}>
          <div><strong>{actionLabels[op.action] || op.action} · {operationTitle(op)}</strong>
            {op.reason && <p>{op.reason}</p>}
            {changedFields(op).map(field => <p key={field.key}>
              {field.key}：{formatValue(field.before)} → {formatValue(field.after)}</p>)}
          </div>
          <small>{op.op_id}</small>
        </div>)}
      </details>)}
      {['block', 'conflict', 'gap'].map(level => issues[level].length > 0 && <details key={level} open={level === 'block'}>
        <summary>{levelLabels[level]} · {issues[level].length}</summary>
        {issues[level].map((issue, index) => <p key={index} className={level === 'block' ? 'warning' : ''}>
          {issue.message}{issue.code ? `（${issue.code}）` : ''}</p>)}
      </details>)}
      {uncovered.length > 0 && <div className="warning">
        <p>仍有场次没有安排拍摄：{uncoveredText(uncovered)}</p>
        <label><input type="checkbox" checked={acceptUncovered}
          onChange={event => setAcceptUncovered(event.target.checked)}/> 我已知情并同意先保留这些场次</label>
      </div>}
      <div className="plan-actions">
        <button disabled={busy || (uncovered.length > 0 && !acceptUncovered)} onClick={onConfirm}>
          确认执行这份草稿</button>
        <button disabled={busy} onClick={onDiscardDraft}>放弃草稿</button>
      </div>
      <details><summary>直接编辑草稿（高级）</summary>
        <p>按后端契约修改操作列表；保存后草稿版本递增，旧确认作废并重新检查。</p>
        <textarea rows={10} value={editing} onChange={event => setEditing(event.target.value)}
          spellCheck={false} aria-label="草稿操作 JSON"/>
        <div className="plan-actions">
          <button disabled={busy || !editing.trim()} onClick={onSaveDraft}>保存草稿修改</button>
          <button disabled={busy} onClick={() => setEditing('')}>放弃修改</button>
        </div>
      </details>
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
export default function AgentWorkspace({ pid, onLockChange, onChanged }) {
  const [runs, setRuns] = useState([]);
  const [run, setRun] = useState(null);
  const [message, setMessage] = useState('');
  const [scope, setScope] = useState({ phase: 'all', start_date: '', end_date: '' });
  const [answer, setAnswer] = useState('');
  const [acceptUncovered, setAcceptUncovered] = useState(false);
  const [editing, setEditing] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // 未保存的草稿编辑锁定项目切换和导航，避免输入丢失。
  useEffect(() => { if (onLockChange) onLockChange(Boolean(editing)); }, [editing, onLockChange]);

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
    setEditing('');
    return detail;
  }, [pid]);

  useEffect(() => {
    if (!pid) return undefined;
    setRun(null);
    act(async () => {
      const list = await refresh();
      if (list.length) await open(list[0].id);
    });
    return () => { if (onLockChange) onLockChange(false); };
  }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * 参数：event 为表单事件。按说明发起一次工作，范围留空时由助手自行判断。
   */
  async function startWork(event) {
    event.preventDefault();
    const body = { message };
    if (scope.start_date && scope.end_date) {
      body.scope = { phase: scope.phase, start_date: scope.start_date, end_date: scope.end_date };
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
   * 解析手工编辑的操作列表并保存；JSON 不合法时给出提示，不发请求。
   */
  async function saveDraft() {
    let operations;
    try {
      operations = JSON.parse(editing);
      if (!Array.isArray(operations)) throw new Error('操作列表必须是数组');
    } catch (caught) {
      setError(`草稿操作不是合法 JSON：${caught.message}`);
      return;
    }
    await act(async () => {
      await agentApi(pid, `/runs/${run.id}/draft`,
        { revision: run.draft.revision, candidate: { origin: 'manual', operations } }, 'PUT');
      await open(run.id);
    });
  }

  if (!pid) return <section><h2>制片助手</h2><p>先选择或创建一个项目。</p></section>;
  return <section>
    <h2>制片助手</h2>
    <p>用一段话说明要编排或调整什么。助手读取正式场次、准备结果和人员资源档期，提出任务与拍摄安排的联合草稿；
      只有你确认后才会写入正式数据，写入使用同一个事务。</p>
    <form onSubmit={startWork}>
      <label>要做什么<textarea rows={3} maxLength={4000} value={message}
        placeholder="例如：把开拍第一周的场次排出来，第 3 场必须安排在上午"
        onChange={event => setMessage(event.target.value)}/></label>
      <div className="columns">
        <label>阶段<select value={scope.phase}
          onChange={event => setScope({ ...scope, phase: event.target.value })}>
          {Object.entries(phaseLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>开始日期<input type="date" value={scope.start_date}
          onChange={event => setScope({ ...scope, start_date: event.target.value })}/></label>
        <label>结束日期<input type="date" value={scope.end_date}
          onChange={event => setScope({ ...scope, end_date: event.target.value })}/></label>
      </div>
      <p><small>不填日期时由助手按开拍日期推断范围，并在草稿里标注为假设。</small></p>
      <button disabled={busy || !message.trim()}>发起编排</button>
    </form>
    {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>关闭</button></div>}
    {busy && <p role="status">处理中，请稍候…</p>}
    {runs.length > 0 && <details><summary>最近工作 · {runs.length}</summary>
      {runs.map(item => <div className="record" key={item.id}>
        <div><strong>{item.message || '未填说明'}</strong>
          <p>{statusLabels[item.status] || item.status} · {stepLabels[item.current_step] || item.current_step}</p></div>
        <button disabled={busy} onClick={() => act(() => open(item.id))}>查看</button>
      </div>)}
    </details>}
    {run && <RunPanel run={run} busy={busy} answer={answer} setAnswer={setAnswer}
      acceptUncovered={acceptUncovered} setAcceptUncovered={setAcceptUncovered}
      editing={editing} setEditing={setEditing}
      onResume={resume} onDiscardRun={() => resume('discard')}
      onConfirm={confirmDraft} onDiscardDraft={discardDraft} onSaveDraft={saveDraft}/>}
  </section>;
}
