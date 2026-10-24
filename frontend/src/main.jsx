import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from './api/client';
import { ScriptPanel, ImpactReport } from './AnalysisTools';
import './style.css';

const kinds = { scene: '场次', requirement: '导演要求', task: '筹备事项', resource: '资源', schedule: '拍摄安排', expense: '费用', decision: '决策' };
const tabs = ['项目概览', '剧本', '筹备', '拍摄安排', '费用', '通告', '影响分析', '变更记录'];
const visible = { 剧本: ['scene', 'requirement', 'decision'], 筹备: ['task', 'resource'], 拍摄安排: ['schedule'], 费用: ['expense'] };
const empty = { title: '', category: '', status: '待确认', owner: '', scene_ids: [], resources: [], date: null, start: null, minutes: 60, amount: '0', source: '', notes: '' };

function App() {
  const [projects, setProjects] = useState([]), [pid, setPid] = useState('');
  const [state, setState] = useState(null), [tab, setTab] = useState('项目概览');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [name, setName] = useState('');
  const [editing, setEditing] = useState(null), [filter, setFilter] = useState('');
  const [message, setMessage] = useState(''), [chats, setChats] = useState([]), [session, setSession] = useState(null);
  const [noticeDate, setNoticeDate] = useState(''), [noticeNotes, setNoticeNotes] = useState('');
  const [events, setEvents] = useState([]);
  const [impact, setImpact] = useState(null), [resourceQuery, setResourceQuery] = useState('');
  const activeProject = useRef(pid); activeProject.current = pid;
  async function load(id = pid) { if (id) { const result = await api(`/projects/${id}`); if (activeProject.current === id) setState(result); } }
  async function act(fn) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  useEffect(() => { api('/projects').then(p => { setProjects(p); if (p.length) setPid(p[0].id); }).catch(e => setError(e.message)); }, []);
  useEffect(() => { setState(null); setChats([]); setSession(null); setEditing(null); setFilter(''); setImpact(null); setResourceQuery(''); if (pid) act(() => load(pid)); }, [pid]);
  useEffect(() => { if (tab === '变更记录' && pid) api(`/projects/${pid}/events`).then(setEvents).catch(e => setError(e.message)); }, [tab, pid, state?.revision]);
  async function createProject(e) { e.preventDefault(); await act(async () => { const p = await api('/projects', { name }); setProjects([...projects, p]); setPid(p.id); setName(''); }); }
  async function saveRecord(e) {
    e.preventDefault();
    await act(async () => {
      const data = { ...editing.data, resources: editing.data.resources.map(x => x.trim()).filter(Boolean) };
      await api(`/projects/${pid}/changes`, { base_revision: state.revision, reason: '制片手动整理', operations: [{ kind: editing.kind, id: editing.id || null, data }] });
      setEditing(null); await load();
    });
  }
  async function handleChange(id, action) { await act(async () => { await api(`/projects/${pid}/changes/${id}/${action}`, {}); await load(); }); }
  async function analyze(target) { await act(async () => { const result = await api(`/projects/${pid}/impact`, { ...target, base_revision: state.revision }); setImpact(result); setTab('影响分析'); }); }
  async function remove(r) { await act(async () => { await api(`/projects/${pid}/changes`, { base_revision: state.revision, reason: '制片提出删除', operations: [{ kind: r.kind, id: r.id, delete: true }] }); await load(); }); }
  async function ask(e) {
    e.preventDefault(); const text = message; setMessage(''); setChats(c => [...c, { role: 'user', content: text }]);
    await act(async () => { try { const result = await api(`/projects/${pid}/agent`, { message: text, session_id: session }); setSession(result.session_id); setChats(c => [...c, { role: 'assistant', content: result.answer, tools: result.tools }]); } finally { await load(); } });
  }
  const records = state?.records || [], pending = state?.changes.filter(c => c.status === 'pending') || [];
  const shown = records.filter(r => (visible[tab] || []).includes(r.kind) && JSON.stringify(r.data).includes(filter)).sort((a, b) => `${a.data.date || ''}${a.data.start || ''}`.localeCompare(`${b.data.date || ''}${b.data.start || ''}`));
  function field(key, value) { setEditing(x => ({ ...x, data: { ...x.data, [key]: value } })); }
  return <div className="app">
    <aside className="sidebar"><div className="brand">片场<span>学生制片工作台</span></div>
      <label>当前项目<select disabled={busy} value={pid} onChange={e => setPid(e.target.value)}><option value="">选择项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <nav>{tabs.map(t => <button key={t} className={tab === t ? 'active' : ''} onClick={() => { setTab(t); setFilter(''); }}>{t}</button>)}</nav>
      <form onSubmit={createProject}><input aria-label="新项目名称" placeholder="新项目名称" value={name} onChange={e => setName(e.target.value)} required maxLength={200}/><button disabled={busy}>创建项目</button></form>
      <small>单制片维护 · 正式修改需确认</small>
    </aside>
    <main><header><div><small>PRODUCTION WORKSPACE</small><h1>{tab}</h1><p>{state ? `${state.name} · 数据版本 ${state.revision}` : '创建项目，开始整理你的拍摄。'}</p></div><button disabled={busy || !pid} onClick={() => act(() => load())}>刷新数据</button></header>
      {error && <div role="alert" className="error">{error}<button onClick={() => setError('')}>关闭</button></div>}
      {busy && <p role="status">处理中，请稍候…</p>}
      {state && <>
        {tab === '剧本' && <ScriptPanel key={pid} pid={pid} revision={state.revision} busy={busy} act={act} onDraft={() => load()}/>}
        {tab === '影响分析' && <><section><h2>按资源分析</h2><p>输入演员、场地或器材名称，多个名称用中文逗号分隔；也可从记录或待确认草稿发起分析。</p><form onSubmit={e => { e.preventDefault(); analyze({ resources: resourceQuery.split(/[,，、]/).map(x => x.trim()).filter(Boolean) }); }}><label>资源名称<input required value={resourceQuery} onChange={e => setResourceQuery(e.target.value)}/></label><button disabled={busy}>分析关联影响</button></form></section><ImpactReport result={impact} revision={state.revision}/></>}
        {pending.length > 0 && <section><h2>待确认修改 · {pending.length}</h2><p>请检查差异。确认会更新正式记录，并使现有通告提示待检查。</p>{pending.map(c => <details key={c.id}><summary>{c.reason} · 基于版本 {c.base_revision}{c.base_revision !== state.revision && ' · 已过期'}</summary>{c.operations.map((op, i) => <div className="diff" key={i}><strong>{kinds[op.kind]} · {op.delete ? '删除' : op.id ? '修改' : '新增'}</strong><div className="columns"><div>原记录<pre>{JSON.stringify(c.before[i]?.data || null, null, 2)}</pre></div><div>修改后<pre>{JSON.stringify(op.data, null, 2)}</pre></div></div></div>)}<button disabled={busy || c.base_revision !== state.revision} onClick={() => analyze({ change_id: c.id })}>分析影响</button> <button disabled={busy || c.base_revision !== state.revision} onClick={() => handleChange(c.id, 'confirm')}>确认保存</button> <button disabled={busy} onClick={() => handleChange(c.id, 'reject')}>取消草稿</button></details>)}</section>}
        {tab === '项目概览' && <><div className="stats">{[['场次', records.filter(r => r.kind === 'scene').length], ['筹备待落实', records.filter(r => r.kind === 'task' && !['已完成', '已确认'].includes(r.data.status)).length], ['排期提醒', state.checks.length], ['实际支出', `¥${state.totals['实际支出']}`]].map(([k, v]) => <section key={k}><small>{k}</small><h2>{v}</h2></section>)}</div><section><h2>当前需关注</h2><p>筹备可以平行推进，未确认的信息不会自动视为已落实。</p>{state.checks.length ? state.checks.map((c, i) => <p className="warning" key={i}>{c.message}</p>) : <p>已录入安排中暂无程序检测到的冲突。档期、天光等备注条件仍需制片核对。</p>}</section></>}
        {visible[tab] && <section><div className="toolbar"><input aria-label="筛选记录" placeholder="按名称、状态、负责人筛选" value={filter} onChange={e => setFilter(e.target.value)}/><div>{visible[tab].map(kind => <button key={kind} disabled={busy} onClick={() => setEditing({ kind, data: { ...empty, category: kind === 'expense' ? '预算' : '' } })}>新增{kinds[kind]}</button>)}</div></div>
          {tab === '拍摄安排' && <p>拍摄、布光、置景均可分别录入。时间重叠且共用资源名称时提示冲突；请统一填写资源名称。</p>}
          {!shown.length && <p className="empty">暂无记录。可以手动新增，也可以让 Agent 整理后提交草稿。</p>}
          {shown.map(r => <article className="record" key={r.id}><div><small>{kinds[r.kind]} · {r.data.category} · {r.id.slice(0, 8)}</small><h3>{r.data.title}</h3><p>{r.data.date} {r.data.start?.slice(0, 5)} {r.kind === 'schedule' && `${r.data.minutes}分钟`} · {r.data.status} {r.data.owner && `· ${r.data.owner}`}{r.kind === 'expense' && ` · ¥${r.data.amount}`}</p><p>{r.data.notes}</p>{r.data.resources.length > 0 && <p>资源：{r.data.resources.join('、')}</p>}{r.data.scene_ids.length > 0 && <p>场次：{r.data.scene_ids.map(id => records.find(x => x.id === id)?.data.title || id).join('、')}</p>}{r.data.source && <small>来源：{r.data.source}</small>}</div><div><button disabled={busy} onClick={() => analyze({ record_ids: [r.id] })}>分析影响</button><button disabled={busy} onClick={() => setEditing({ id: r.id, kind: r.kind, data: { ...r.data } })}>编辑</button><button disabled={busy} onClick={() => remove(r)}>提出删除</button></div></article>)}
        </section>}
        {tab === '费用' && <section className="stats">{Object.entries(state.totals).map(([k, v]) => <div key={k}><small>{k}</small><h3>¥{v}</h3></div>)}</section>}
        {tab === '通告' && <section><h2>发布当天通告</h2><p>发布后固定快照。任何正式数据变更都会保守提示旧通告待检查，确认无影响可继续使用原版。</p><form onSubmit={e => { e.preventDefault(); act(async () => { await api(`/projects/${pid}/notices`, { date: noticeDate, base_revision: state.revision, notes: noticeNotes }); await load(); }); }}><label>拍摄日期<input type="date" required value={noticeDate} onChange={e => setNoticeDate(e.target.value)}/></label><label>集合、交通、用餐及部门准备指令<textarea value={noticeNotes} onChange={e => setNoticeNotes(e.target.value)}/></label><button disabled={busy}>确认发布固定版本</button></form><hr/>{[...state.notices].reverse().map(n => <details key={n.id}><summary>{n.date} · V{n.version} · {n.stale ? '数据已变，待检查' : '当前数据版本'} · {new Date(n.created_at).toLocaleString()}</summary><pre>{n.snapshot.notes}</pre>{n.snapshot.schedule.map(r => <p key={r.id}>{r.data.start} · {r.data.title} · {r.data.minutes}分钟</p>)}<a href={`/api/projects/${pid}/notices/${n.id}/export`}>下载本版通告 TXT</a></details>)}</section>}
        {tab === '变更记录' && <section><h2>事件和操作来源</h2>{events.map(e => <details key={e.id}><summary>{e.type === 'chat' ? 'Agent 会话' : e.type === 'script_parse' ? '剧本解析' : '正式修改'} · {new Date(e.created_at).toLocaleString()}</summary><pre>{JSON.stringify(e.data, null, 2)}</pre></details>)}</section>}
      </>}
    </main>
    <aside className="assistant"><h2>制片 Agent</h2><p>查项目、整理沟通、检查排期。修改先生成草稿。</p><div className="chat">{chats.length === 0 && <p className="empty">试着问：检查明天的拍摄还缺什么。<br/>模型未配置时会明确提示。</p>}{chats.map((c, i) => <div key={i} className={`bubble ${c.role}`}><small>{c.role === 'user' ? '你' : 'Agent'}</small><div>{c.content}</div>{c.tools?.length > 0 && <details><summary>查看工具调用</summary><pre>{JSON.stringify(c.tools, null, 2)}</pre></details>}</div>)}</div><form onSubmit={ask}><textarea aria-label="向Agent提问" value={message} onChange={e => setMessage(e.target.value)} placeholder="粘贴沟通，或提出具体问题…" required/><button disabled={busy || !pid}>发送</button></form></aside>
    {editing && <div className="overlay"><section className="editor" role="dialog" aria-modal="true" aria-label="编辑记录"><h2>{editing.id ? '编辑' : '新增'}{kinds[editing.kind]}</h2><form onSubmit={saveRecord}>
      <label>名称<input autoFocus required value={editing.data.title} onChange={e => field('title', e.target.value)}/></label>
      <div className="columns"><label>分类{editing.kind === 'expense' ? <select value={editing.data.category} onChange={e => field('category', e.target.value)}>{['预算', '报价', '已确定', '实际支出'].map(x => <option key={x}>{x}</option>)}</select> : <input placeholder="场地 / 演员 / 器材…" value={editing.data.category} onChange={e => field('category', e.target.value)}/>}</label><label>状态<select value={editing.data.status} onChange={e => field('status', e.target.value)}>{['待确认', '进行中', '已确认', '已完成', '待补拍'].map(x => <option key={x}>{x}</option>)}</select></label></div>
      <label>对接人<input value={editing.data.owner} onChange={e => field('owner', e.target.value)}/></label>
      <label>关联场次<select multiple value={editing.data.scene_ids} onChange={e => field('scene_ids', [...e.target.selectedOptions].map(x => x.value))}>{records.filter(r => r.kind === 'scene' && r.id !== editing.id).map(r => <option key={r.id} value={r.id}>{r.data.title}</option>)}</select><small>按住 Ctrl / Command 可多选或取消选择</small></label>
      <label>占用资源（用英文逗号分隔，统一名称）<input value={editing.data.resources.join(',')} onChange={e => field('resources', e.target.value.split(',').map(x => x.trim()))}/></label>
      <div className="columns"><label>日期<input type="date" value={editing.data.date || ''} onChange={e => field('date', e.target.value || null)}/></label><label>开始时间<input type="time" value={editing.data.start?.slice(0, 5) || ''} onChange={e => field('start', e.target.value || null)}/></label><label>制片估时（分钟）<input type="number" min="1" max="1440" value={editing.data.minutes} onChange={e => field('minutes', Number(e.target.value))}/></label></div>
      {editing.kind === 'expense' && <label>金额（元）<input type="number" min="0" step="0.01" value={editing.data.amount} onChange={e => field('amount', e.target.value)}/></label>}
      <label>信息来源<input placeholder="谁在何时确认 / 文件页码" value={editing.data.source} onChange={e => field('source', e.target.value)}/></label><label>说明 / 原文<textarea value={editing.data.notes} onChange={e => field('notes', e.target.value)}/></label><button disabled={busy}>生成待确认修改</button> <button type="button" onClick={() => setEditing(null)}>取消</button>
    </form></section></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
