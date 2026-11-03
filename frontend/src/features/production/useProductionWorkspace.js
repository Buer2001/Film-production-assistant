import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { visible } from './constants';

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
  async function load(id = pid) { if (id) { const result = await api(`/projects/${id}`); if (activeProject.current === id) setState(result); } }
  async function act(fn) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  useEffect(() => { api('/health').then(h => setModelNotice(h.agent_configured === false)).catch(e => setError(e.message)); }, []);
  useEffect(() => { setState(null); setChats([]); setSession(null); setEditing(null); setFilter(''); setImpact(null); setResourceQuery(''); if (pid) act(() => load(pid)); }, [pid]);
  // 从日程返回概览时重读后端统计，不能沿用进入日程前的快照。
  useEffect(() => { if (tab === '项目概览' && pid) act(() => load(pid)); }, [tab, pid]);
  useEffect(() => { if (tab === '变更记录' && pid) api(`/projects/${pid}/events`).then(setEvents).catch(e => setError(e.message)); }, [tab, pid, state?.revision]);
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
  return { state, tab, pid, setTab, error, setError, busy, act, load, editing, setEditing, filter, setFilter, message, setMessage, chats, noticeDate, setNoticeDate, noticeNotes, setNoticeNotes, events, modelNotice, setModelNotice, impact, resourceQuery, setResourceQuery, saveRecord, handleChange, analyze, remove, ask, records, pending, shown, field };
}
