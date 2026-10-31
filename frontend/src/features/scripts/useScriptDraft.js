import { useEffect, useRef, useState } from 'react';
import { scriptApi } from './api';

export default function useScriptDraft(pid, onLockChange) {
  const [versions, setVersions] = useState([]), [doc, setDoc] = useState(null);
  const [selected, setSelected] = useState(null), [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [saveState, setSaveState] = useState('已保存'), [acceptMissing, setAcceptMissing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const current = useRef(null), epoch = useRef(0), generation = useRef(0);
  const saving = useRef(false), alive = useRef(true), blocked = useRef(false), changed = useRef(false);
  const timer = useRef(null), edits = useRef(new Map()), pendingEdits = useRef(new Map()), removed = useRef(new Set());
  const stream = useRef(null), reconnectTimer = useRef(null), streamGeneration = useRef(0);
  const [connection, setConnection] = useState('closed');
  // 用户修改按字段保留，后台逐场结果仍可更新未编辑的字段。
  function receive(value) {
    const local = current.current;
    if (!local || local.id !== value.id) return;
    if ((value.progress?.sequence || 0) < (local.progress?.sequence || 0)) return;
    const rows = value.scenes.filter(row => !removed.current.has(row.id)).map(row =>
      ({ ...row, ...edits.current.get(row.id) }));
    const ids = new Set(rows.map(row => row.id));
    rows.push(...local.scenes.filter(row => row.local_id && !ids.has(row.id)));
    if (changed.current) {
      const order = new Map(local.scenes.map((row, index) => [row.id || row.local_id, index]));
      rows.sort((a, b) => (order.get(a.id || a.local_id) ?? Infinity) - (order.get(b.id || b.local_id) ?? Infinity));
    }
    install({ ...value, revision: Math.max(value.revision, local.revision), scenes: rows,
      ...(changed.current ? { deleted_reviewed: local.deleted_reviewed } : {}) });
  }
  function connect() {
    stream.current?.close(); clearTimeout(reconnectTimer.current);
    const value = current.current, ticket = ++streamGeneration.current;
    if (!value || value.read_only || value.progress?.state !== 'running') { setConnection('closed'); return; }
    setConnection('connecting');
    const source = new EventSource(scriptApi.eventsUrl(pid, value.id, value.progress?.sequence || 0));
    stream.current = source;
    source.onopen = () => { if (ticket === streamGeneration.current) setConnection('connected'); };
    const handle = event => {
      if (ticket !== streamGeneration.current) return;
      try {
        const next = JSON.parse(event.data).document;
        if (!next || current.current?.id !== value.id) return;
        receive(next);
        if (next.progress?.state !== 'running') { source.close(); setConnection('closed'); }
      } catch { setError('进度消息读取失败，请重新连接。'); }
    };
    ['progress', 'scene', 'complete', 'interrupted', 'snapshot'].forEach(name => source.addEventListener(name, handle));
    source.onerror = () => {
      if (ticket !== streamGeneration.current) return;
      source.close(); setConnection('disconnected');
      reconnectTimer.current = setTimeout(connect, 3000);
    };
  }
  useEffect(() => {
    connect();
    return () => { ++streamGeneration.current; stream.current?.close(); clearTimeout(reconnectTimer.current); };
  }, [pid, doc?.id, doc?.progress?.state]);
  useEffect(() => {
    onLockChange?.(dirty || busy || saveState === '保存中');
  }, [dirty, busy, saveState, onLockChange]);
  // ref 保存最新草稿；自动保存串行执行，不让较慢响应覆盖后来输入。
  function install(value) {
    if (current.current?.id !== value.id) { edits.current.clear(); pendingEdits.current.clear(); removed.current.clear(); }
    current.current = value; setDoc(value);
  }
  useEffect(() => {
    alive.current = true;
    let active = true;
    scriptApi.list(pid).then(async items => {
      if (!active) return;
      setVersions(items);
      if (items.length) {
        const value = await scriptApi.get(pid, items[0].id);
        if (active) install(value);
      } else setImporting(true);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; alive.current = false; clearTimeout(timer.current); };
  }, [pid]);
  useEffect(() => {
    const warn = event => {
      if (changed.current || saving.current) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);

  function retrySave() { blocked.current = false; return persist(); }
  async function persist() {
    clearTimeout(timer.current);
    if (!changed.current || saving.current || blocked.current || !current.current) return false;
    saving.current = true; setSaveState('保存中');
    const snapshot = current.current, start = epoch.current;
    const sentEdits = new Map([...pendingEdits.current].map(([id, fields]) => [id, { ...fields }]));
    try {
      const scenes = snapshot.scenes.map(({ local_id, ...row }) => row);
      const result = await scriptApi.save(pid, snapshot.id, { revision: snapshot.revision,
        scenes, edited_fields: Object.fromEntries([...sentEdits].map(([id, fields]) => [id, Object.keys(fields)])), deleted_reviewed: snapshot.deleted_reviewed });
      if (!alive.current) return false;
      // 自动事件可能比保存响应更新；仅推进编辑版本，不退回进度或逐场结果。
      const latest = current.current;
      receive((latest.progress?.sequence || 0) > (result.progress?.sequence || 0)
        ? { ...latest, revision: result.revision } : result);
      if (start === epoch.current) {
        changed.current = false; setDirty(false); setSaveState('已保存');
      } else setSaveState('待保存');
      sentEdits.forEach((fields, id) => {
        const pending = pendingEdits.current.get(id);
        if (!pending) return;
        Object.entries(fields).forEach(([field, value]) => { if (JSON.stringify(pending[field]) === JSON.stringify(value)) delete pending[field]; });
        if (!Object.keys(pending).length) pendingEdits.current.delete(id);
      });
      setError('');
      return true;
    } catch (e) {
      if (alive.current) {
        blocked.current = true; setSaveState('保存失败'); setError(e.message + '；本地输入已保留，请重试或复制备份。');
      }
      return false;
    } finally {
      saving.current = false;
      if (alive.current && changed.current && !blocked.current) timer.current = setTimeout(persist, 600);
    }
  }
  function mutate(update) {
    if (!current.current || current.current.read_only) return;
    epoch.current++; changed.current = true; setDirty(true);
    setAcceptMissing(false);
    const before = current.current, next = update(before);
    const nextIds = new Set(next.scenes.map(row => row.id || row.local_id));
    before.scenes.forEach(row => { if (!nextIds.has(row.id || row.local_id)) removed.current.add(row.id || row.local_id); });
    next.scenes.forEach(row => {
      const previous = before.scenes.find(item => (item.id || item.local_id) === (row.id || row.local_id));
      if (!previous) return; // 新行携带完整内容，由服务端创建，不需要字段覆盖掩码。
      const fields = { ...edits.current.get(row.id || row.local_id) };
      Object.keys(row).forEach(key => { if (JSON.stringify(row[key]) !== JSON.stringify(previous[key])) fields[key] = row[key]; });
      const pending = { ...pendingEdits.current.get(row.id || row.local_id) };
      Object.keys(row).forEach(key => { if (JSON.stringify(row[key]) !== JSON.stringify(previous[key])) pending[key] = row[key]; });
      pendingEdits.current.set(row.id || row.local_id, pending);
      edits.current.set(row.id || row.local_id, fields);
    });
    install({ ...next, status: before.progress?.state === 'running' ? before.status : 'review', confirmed_at: null });
    // 失败后继续输入仍保留恢复入口，不能只改成“待保存”却停留在阻塞状态。
    setSaveState(blocked.current ? '保存失败' : '待保存');
    clearTimeout(timer.current);
    if (!blocked.current) timer.current = setTimeout(persist, 800);
  }
  function updateScene(index, field, value) {
    mutate(valueDoc => ({ ...valueDoc, scenes: valueDoc.scenes.map((s, i) =>
      i === index ? { ...s, [field]: value, ...(field === 'change_reviewed' ? {} : { change_reviewed: false }) } : s),
      ...(['previous_scene_id', 'match_status'].includes(field) ? { deleted_reviewed: false } : {}) }));
  }
  function backupDraft() {
    // 保存失败时可先下载本地内容，再决定是否重新加载；绝不直接丢弃输入。
    const blob = new Blob([JSON.stringify(current.current, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'breakdown-local-backup.json'; link.click(); URL.revokeObjectURL(url);
  }
  async function reloadSaved() {
    if (!window.confirm('重新加载会丢弃未保存的本地修改，建议先下载草稿备份。继续吗？')) return;
    await run(async () => {
      const result = await scriptApi.get(pid, current.current.id);
      edits.current.clear(); pendingEdits.current.clear(); removed.current.clear(); install(result); blocked.current = false; changed.current = false;
      setDirty(false); setSaveState('已保存'); setAcceptMissing(false);
    });
  }
  async function run(action) {
    setBusy(true); setError('');
    try { await action(); } catch (e) { if (alive.current) setError(e.message); }
    finally { if (alive.current) setBusy(false); }
  }
  async function switchVersion(sid) {
    if (changed.current || saving.current) { setError('请先保存当前修改，再切换版本。'); return; }
    const ticket = ++generation.current;
    await run(async () => {
      const value = await scriptApi.get(pid, sid);
      if (ticket === generation.current) {
        install(value); setSelected(null); setImporting(false); setAcceptMissing(false);
      }
    });
  }
  async function parse(value) {
    try {
      const result = await scriptApi.parse(pid, value.id, value.revision);
      if (alive.current) receive(result);
    } catch (e) {
      if (alive.current) receive(await scriptApi.get(pid, value.id));
      throw e;
    }
  }
  async function retryScene(sceneId) {
    if (changed.current || saving.current) { setError('请等待当前修改保存后重试。'); return; }
    await run(async () => receive(await scriptApi.retry(pid, current.current.id, sceneId, current.current.revision)));
  }
  return { connection, reconnect: connect, retryScene, versions, setVersions, doc, selected, setSelected, importing, setImporting, busy, error, setError, saveState, acceptMissing, setAcceptMissing, dirty, install, mutate, updateScene, backupDraft, reloadSaved, run, switchVersion, parse, retrySave };
}
