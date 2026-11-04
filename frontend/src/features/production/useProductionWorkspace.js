// 集中管理制片页面快照、记录变更草稿、影响分析和 Agent 会话。
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { visible } from './constants';

/**
 * 参数：pid 为项目 ID，tab 为当前页面，setTab 切换页面。返回页面状态、编辑入口及异步操作函数。
 * 切换项目时重置会话和编辑状态；项目概览及变更记录按相应依赖重读，项目引用阻止旧快照回写。
 */
export default function useProductionWorkspace(pid, tab, setTab) {
  const [state, setState] = useState(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null), [filter, setFilter] = useState('');
  const [message, setMessage] = useState(''), [chats, setChats] = useState([]), [session, setSession] = useState(null);
  const [noticeDate, setNoticeDate] = useState(''), [noticeNotes, setNoticeNotes] = useState('');
  const [events, setEvents] = useState([]);
  const [modelNotice, setModelNotice] = useState(false);
  const [impact, setImpact] = useState(null), [resourceQuery, setResourceQuery] = useState('');
  const activeProject = useRef(pid); activeProject.current = pid;
  /**
   * 参数 id 默认为当前项目；读取项目快照，仅当响应仍属于当前项目时安装；返回异步完成状态。
   */
  async function load(id = pid) { if (id) { const result = await api(`/projects/${id}`); if (activeProject.current === id) setState(result); } }
  /**
   * 参数 fn 为异步操作；统一设置 busy/error，并在 finally 中解除忙碌状态。
   */
  async function act(fn) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  useEffect(() => { api('/health').then(h => setModelNotice(h.agent_configured === false)).catch(e => setError(e.message)); }, []);
  useEffect(() => { setState(null); setChats([]); setSession(null); setEditing(null); setFilter(''); setImpact(null); setResourceQuery(''); if (pid) act(() => load(pid)); }, [pid]);
  // 从日程返回概览时重读后端统计，不能沿用进入日程前的快照。
  useEffect(() => { if (tab === '项目概览' && pid) act(() => load(pid)); }, [tab, pid]);
  useEffect(() => { if (tab === '变更记录' && pid) api(`/projects/${pid}/events`).then(setEvents).catch(e => setError(e.message)); }, [tab, pid, state?.revision]);
  /**
   * 参数 e 为表单事件；清理资源名称后按 base_revision 提交变更草稿，成功后关闭编辑并刷新项目。
   */
  async function saveRecord(e) {
    e.preventDefault();
    await act(async () => {
      const data = { ...editing.data, resources: editing.data.resources.map(x => x.trim()).filter(Boolean) };
      await api(`/projects/${pid}/changes`, { base_revision: state.revision, reason: '制片手动整理', operations: [{ kind: editing.kind, id: editing.id || null, data }] });
      setEditing(null); await load();
    });
  }
  /**
   * 参数 id/action 为变更 ID 和处理动作；请求确认或拒绝后刷新快照。
   */
  async function handleChange(id, action) { await act(async () => { await api(`/projects/${pid}/changes/${id}/${action}`, {}); await load(); }); }
  /**
   * 参数 target 为记录、资源或变更目标；附当前版本进行只读影响分析，成功后展示分析页面。
   */
  async function analyze(target) { await act(async () => { const result = await api(`/projects/${pid}/impact`, { ...target, base_revision: state.revision }); setImpact(result); setTab('影响分析'); }); }
  /**
   * 参数 r 为记录；提出带当前基准版本的删除草稿，并刷新快照，正式删除仍需确认。
   */
  async function remove(r) { await act(async () => { await api(`/projects/${pid}/changes`, { base_revision: state.revision, reason: '制片提出删除', operations: [{ kind: r.kind, id: r.id, delete: true }] }); await load(); }); }
  /**
   * 参数 e 为提交事件；追加用户消息并调用当前 Agent 会话，无论调用成功与否均刷新项目数据。
   */
  async function ask(e) {
    e.preventDefault(); const text = message; setMessage(''); setChats(c => [...c, { role: 'user', content: text }]);
    await act(async () => { try { const result = await api(`/projects/${pid}/agent`, { message: text, session_id: session }); setSession(result.session_id); setChats(c => [...c, { role: 'assistant', content: result.answer, tools: result.tools }]); } finally { await load(); } });
  }
  const records = state?.records || [], pending = state?.changes.filter(c => c.status === 'pending') || [];
  const shown = records.filter(r => (visible[tab] || []).includes(r.kind) && JSON.stringify(r.data).includes(filter)).sort((a, b) => `${a.data.date || ''}${a.data.start || ''}`.localeCompare(`${b.data.date || ''}${b.data.start || ''}`));
  /**
   * 参数 key/value 为编辑字段及新值；仅替换本地 editing.data 中的目标字段。
   */
  function field(key, value) { setEditing(x => ({ ...x, data: { ...x.data, [key]: value } })); }
  return { state, tab, pid, setTab, error, setError, busy, act, load, editing, setEditing, filter, setFilter, message, setMessage, chats, noticeDate, setNoticeDate, noticeNotes, setNoticeNotes, events, modelNotice, setModelNotice, impact, resourceQuery, setResourceQuery, saveRecord, handleChange, analyze, remove, ask, records, pending, shown, field };
}
