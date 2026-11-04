// 文件职责：按天展示大计划、逐场日志和只读历史安排；表单失败保留输入，编辑时保护导航。
import React, { useEffect, useState } from 'react';
import useShooting from './useShooting';
import ShootingEditor from './ShootingEditor';
import { kinds, logStatuses, today, onDay, sceneLabel, timeLabel, newItem, newLog, itemPayload, logPayload } from './shooting';
import './shooting.css';

export default function ShootingWorkspace({ pid, onLockChange, onChanged, legacy = [] }) {
  const { data, busy, error, refresh, save, setError } = useShooting(pid, onChanged);
  const [view, setView] = useState('plan'), [day, setDay] = useState(today), [editor, setEditor] = useState(null), [cancelled, setCancelled] = useState(false);
  const locked = busy || !!editor;
  useEffect(() => { onLockChange?.(locked); return () => onLockChange?.(false); }, [locked, onLockChange]);
  useEffect(() => {
    if (!editor) return;
    const warn = e => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [!!editor]);
  if (!data) return <section className="shoot-workspace">{error ? <div className="error" role="alert">{error}<button onClick={refresh}>重试</button></div> : <p role="status">正在读取拍摄计划…</p>}</section>;
  const active = data.items.filter(r => r.data.status !== 'cancelled');
  const rows = data.items.filter(r => onDay(r, day) && (cancelled || r.data.status !== 'cancelled'));
  const dayLogs = data.logs.filter(r => r.data.date === day);
  const dates = [...new Set([day, today(), ...active.map(r => r.data.start_at.slice(0, 10)), ...data.logs.map(r => r.data.date)])].sort();
  const dayIds = new Set(rows.map(r => r.id)), issues = data.issues.filter(i => dayIds.has(i.item_id) || dayIds.has(i.other_item_id));
  const planned = new Set(active.filter(r => r.data.kind === 'shoot').map(r => r.data.scene_id));
  const newest = Math.max(0, ...data.scenes.map(s => s.script_version));
  const unplanned = data.scenes.filter(s => s.script_version === newest && !planned.has(s.id));
  function open(type, value = null) {
    setError('');
    setEditor({ type, id: value?.id || null, data: value ? { ...value.data } : type === 'items' ? newItem(day) : newLog(day) });
  }
  async function submit() {
    const ok = await save(editor.type, editor.id, editor.type === 'items' ? itemPayload(editor.data) : logPayload(editor.data));
    if (ok) setEditor(null);
  }
  function addLog(row) {
    setError('');
    setEditor({ type: 'logs', id: null, data: newLog(day, { scene_id: row.data.scene_id, item_id: row.id }) });
  }
  function reshoot(log) {
    const old = data.items.find(r => r.id === log.data.item_id)?.data;
    const scene = data.scenes.find(s => s.id === log.data.scene_id);
    setView('plan'); setError('');
    setEditor({ type: 'items', id: null, data: newItem(day, { title: `${scene?.scene_number || ''}场补拍`,
      scene_id: log.data.scene_id, reshoot_log_id: log.id, location: old?.location || scene?.location || '',
      person_ids: old?.person_ids || [], resource_ids: old?.resource_ids || [], notes: [log.data.remaining, log.data.reshoot_reason].filter(Boolean).join('\n') }) });
  }
  return <div className="shoot-workspace">
    <div className="shoot-topline"><div><span className="shoot-eyebrow">ON SET / 拍摄执行</span><p>把每天的计划，落实成可追溯的拍摄结果。</p></div><button disabled={locked} onClick={refresh}>刷新计划</button></div>
    <div className="shoot-metrics"><div><small>已排拍摄场次</small><strong>{planned.size}</strong></div><div><small>最新剧本未排场次</small><strong>{unplanned.length}</strong></div><div><small>当天安排</small><strong>{rows.filter(r => r.data.status !== 'cancelled').length}</strong></div><div><small>当天日志</small><strong>{dayLogs.length}</strong></div></div>
    {error && !editor && <div className="error" role="alert">{error}</div>}
    <div className="shoot-toolbar"><div className="shoot-tabs" role="group" aria-label="拍摄视图"><button aria-pressed={view === 'plan'} disabled={locked} onClick={() => setView('plan')}>拍摄大计划</button><button aria-pressed={view === 'logs'} disabled={locked} onClick={() => setView('logs')}>拍摄日志</button></div><button className="shoot-primary" disabled={locked} onClick={() => open(view === 'plan' ? 'items' : 'logs')}>＋ {view === 'plan' ? '新增安排' : '新增日志'}</button></div>
    <div className="shoot-layout"><aside className="shoot-days"><label>拍摄日期<input type="date" required disabled={locked} value={day} onChange={e => e.target.value && setDay(e.target.value)}/></label><div className="shoot-date-list">{dates.map(date => <button key={date} disabled={locked} className={date === day ? 'selected' : ''} onClick={() => setDay(date)}><span>{date.slice(5).replace('-', ' / ')}</span><small>{active.filter(r => onDay(r, date)).length} 项安排</small></button>)}</div></aside>
    <section className="shoot-day-content"><div className="shoot-heading"><div><small>{day}</small><h2>{view === 'plan' ? '当天拍摄安排' : '当天实际记录'}</h2></div>{view === 'plan' && <label className="shoot-inline"><input type="checkbox" checked={cancelled} onChange={e => setCancelled(e.target.checked)}/>显示已取消</label>}</div>
      {issues.length > 0 && <details className="shoot-issues"><summary>有 {issues.length} 项需核实</summary>{issues.map((issue, i) => <p key={i}>{issue.message}</p>)}</details>}
      {view === 'plan' ? rows.length ? <div className="shoot-timeline">{rows.map(row => {
        const value = row.data, scene = data.scenes.find(s => s.id === value.scene_id);
        return <article className={`shoot-card kind-${value.kind}${value.status === 'cancelled' ? ' cancelled' : ''}`} key={row.id}><div className="shoot-time"><strong>{value.start_at.slice(11, 16)}</strong><span>{value.end_at.slice(0, 10) === value.start_at.slice(0, 10) ? '' : value.end_at.slice(5, 10) + ' '}{value.end_at.slice(11, 16)}</span></div><div className="shoot-card-main"><div className="shoot-card-title"><span className="shoot-badge">{kinds[value.kind]}</span>{value.reshoot_log_id && <span className="shoot-badge amber">补拍</span>}{value.status === 'cancelled' && <span className="shoot-badge">已取消</span>}</div><h3>{value.title}</h3>{scene && <p className="shoot-muted">{sceneLabel(scene)}</p>}<p>{value.location || '地点待定'}{value.shots != null && ` · ${value.shots} 个镜头`}</p><div className="shoot-chips">{value.person_ids.map(id => <span key={id}>{data.people.find(p => p.id === id)?.name || '人员资料缺失'}</span>)}{value.resource_ids.map(id => <span key={id}>{data.resources.find(r => r.id === id)?.data.title || '资源资料缺失'}</span>)}</div>{value.notes && <p className="shoot-note">{value.notes}</p>}<div className="shoot-actions"><button disabled={locked} onClick={() => open('items', row)}>编辑安排</button>{value.kind === 'shoot' && <button disabled={locked} onClick={() => addLog(row)}>记录拍摄结果</button>}</div></div></article>;
      })}</div> : <div className="shoot-empty"><span>○</span><h3>这一天还没有安排</h3><p>从场次拍摄开始，也可以先安排转场、用餐或准备工作。</p><button disabled={locked} onClick={() => open('items')}>新增当天安排</button></div>
      : dayLogs.length ? dayLogs.map(log => <article className="shoot-log" key={log.id}><div className="shoot-heading"><h3>{sceneLabel(data.scenes.find(s => s.id === log.data.scene_id))}</h3><span className={`shoot-badge ${log.data.status !== 'completed' ? 'amber' : ''}`}>{logStatuses[log.data.status]}</span></div><p className="shoot-muted">{log.unplanned ? '临时加拍' : '关联正式安排'} · {timeLabel(log.data.actual_start)} — {timeLabel(log.data.actual_end)}</p>{log.data.remaining && <p><strong>剩余内容：</strong>{log.data.remaining}</p>}{log.data.reshoot_reason && <p><strong>原因：</strong>{log.data.reshoot_reason}</p>}{log.data.notes && <p className="shoot-note">{log.data.notes}</p>}<div className="shoot-actions"><button disabled={locked} onClick={() => open('logs', log)}>编辑日志</button><button disabled={locked} onClick={() => reshoot(log)}>安排补拍</button></div></article>) : <div className="shoot-empty"><span>▤</span><h3>尚无拍摄日志</h3><p>记录实际结果；临时加拍也可以直接关联场次填写。</p><button disabled={locked} onClick={() => open('logs')}>新增日志</button></div>}
    </section></div>
    {unplanned.length > 0 && <details className="shoot-unplanned"><summary>最新已确认剧本 · {unplanned.length} 场尚未安排</summary><div className="shoot-chips">{unplanned.map(scene => <button key={scene.id} disabled={locked} onClick={() => { setError(''); setEditor({ type: 'items', id: null, data: newItem(day, { title: `${scene.scene_number}场拍摄`, scene_id: scene.id, location: scene.location }) }); }}>{sceneLabel(scene)} ＋</button>)}</div></details>}
    {legacy.length > 0 && <details className="shoot-unplanned"><summary>历史拍摄安排 · {legacy.length} 项</summary><p className="shoot-muted">旧数据只读保留，不自动迁入新大计划。</p>{legacy.map(r => <p key={r.id}>{r.data.date || '日期待定'} {r.data.start || ''} · {r.data.title}</p>)}</details>}
    <p className="shoot-footnote">收尾事项继续在项目日程跟进 · 计划和日志均由制片维护</p>
    {editor && <ShootingEditor editor={editor} source={data} busy={busy} error={error} onChange={value => setEditor(e => ({ ...e, data: value }))} onSave={submit} onClose={() => { setEditor(null); setError(''); }} onRefresh={refresh}/>}
  </div>;
}
