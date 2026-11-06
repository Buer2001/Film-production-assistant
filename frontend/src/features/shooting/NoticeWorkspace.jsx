// 文件职责：编辑当天执行信息、显式保存草稿、预览并发布冻结版本；历史展示只读取快照。
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { emptyDetails, kinds, today, sceneLabel, timeLabel } from './shooting';
import './shooting.css';

const detailLabels = { assembly: '集合安排', makeup: '交妆时间', transport: '交通和入场', meals: '用餐安排', notes: '注意事项' };

// source 可来自当前预览或历史快照；组件不查询当前资料，保证历史版本的显示可追溯。
function NoticePreview({ source, details }) {
  return <div className="shoot-notice-preview"><div className="shoot-notice-title"><small>DAILY CALL SHEET</small><h2>{source.project} · 每日通告</h2><p>{source.date}</p></div><div className="shoot-notice-details">{Object.entries(detailLabels).map(([key, label]) => <div key={key}><small>{label}</small><p>{details[key] || '待补充'}</p></div>)}</div><div className="shoot-notice-slots">{source.items.map(row => {
    const d = row.data, scene = source.scenes.find(s => s.id === d.scene_id);
    return <article key={row.id}><div className="shoot-heading"><strong>{timeLabel(d.start_at)} — {timeLabel(d.end_at)}</strong><span className="shoot-badge">{kinds[d.kind]}</span></div><h3>{d.title}</h3>{scene && <p>{sceneLabel(scene)} · {scene.atmosphere} {scene.interior_exterior}<br/>{scene.summary}</p>}<p>{d.location || scene?.location || '地点待定'}</p><p>人员：{d.person_ids.map(id => source.people.find(p => p.id === id)?.name || '资料缺失').join('、') || '待补充'}<br/>资源：{d.resource_ids.map(id => source.resources.find(r => r.id === id)?.data.title || '资料缺失').join('、') || '待补充'}</p>{d.notes && <p className="shoot-note">{d.notes}</p>}</article>;
  })}{!source.items.length && <p className="shoot-muted">当天没有正式安排，请先到拍摄安排维护。</p>}</div></div>;
}

export default function NoticeWorkspace({ pid, onLockChange, onChanged, initialDay, onDayChange, published = [] }) {
  const [day, setDay] = useState(initialDay || today), [data, setData] = useState(null), [details, setDetails] = useState({ ...emptyDetails });
  const [baseline, setBaseline] = useState(JSON.stringify(emptyDetails)), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const pending = useRef(false), requestId = useRef(0), alive = useRef(true);
  const dirty = JSON.stringify(details) !== baseline;
  useEffect(() => { alive.current = true; return () => { alive.current = false; requestId.current++; }; }, []);
  useEffect(() => { onLockChange?.(busy || dirty); return () => onLockChange?.(false); }, [busy, dirty, onLockChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = e => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  // 日期变化恢复该日草稿；手动刷新只更新来源和版本，不能覆盖尚未保存的执行信息。
  const load = useCallback(async (restore = false) => {
    if (pending.current) return;
    const id = ++requestId.current;
    pending.current = true; setBusy(true); setError('');
    try {
      const result = await api(`/projects/${pid}/shooting/days/${day}`);
      if (!alive.current || id !== requestId.current) return;
      setData(result);
      if (restore) {
        const value = { ...emptyDetails, ...result.draft?.details };
        setDetails(value); setBaseline(JSON.stringify(value));
      }
    } catch (e) { if (alive.current && id === requestId.current) setError(e.message); }
    finally { pending.current = false; if (alive.current && id === requestId.current) setBusy(false); }
  }, [pid, day]);
  useEffect(() => { setData(null); setMessage(''); load(true); }, [load]);
  // 保存和发布串行化；只有请求成功才更新基准，失败保留输入，避免迟到响应清空人工内容。
  async function submit(publish) {
    if (pending.current || !data) return;
    pending.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const result = await api(`/projects/${pid}/shooting/days/${day}/${publish ? 'publish' : 'draft'}`,
        { revision: data.revision, details, ...(publish ? { fingerprint: data.fingerprint } : {}) }, { method: publish ? 'POST' : 'PUT' });
      if (!alive.current) return;
      setData(publish ? { ...data, revision: result.project_revision, draft: { details, revision: result.project_revision },
        notices: [{ ...result, stale: false, reasons: [] }, ...data.notices] } : result);
      setBaseline(JSON.stringify(details));
      setMessage(publish ? `已发布 V${result.version}，本版内容已冻结。` : '草稿已保存，刷新后可继续编辑。');
      onChanged?.().catch(() => {});
    } catch (e) { if (alive.current) setError(e.message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  const notices = [...new Map([...published, ...(data?.notices || [])].map(n => [n.id, n])).values()].sort((a, b) => b.date.localeCompare(a.date) || b.version - a.version);
  return <div className="shoot-workspace"><div className="shoot-topline"><div><span className="shoot-eyebrow">CALL SHEET / 每日通告</span><p>检查当天安排，补充执行信息，再发布固定版本。</p></div><label className="shoot-date-input">拍摄日期<input type="date" required disabled={busy || dirty} value={day} onChange={e => { if (e.target.value) { setDay(e.target.value); onDayChange?.(e.target.value); } }}/></label></div>
    {error && <div className="error" role="alert">{error}<button disabled={busy} onClick={() => load(!data)}>刷新来源，保留输入</button></div>}
    {message && <p className="shoot-success" role="status">{message}</p>}
    {!data ? <section><p role="status">{busy ? '正在读取当天安排…' : '请重试读取当天安排。'}</p></section> : <>
      <div className="shoot-call-layout"><section className="shoot-call-editor"><div className="shoot-heading"><h2>执行信息</h2><span className={`shoot-badge ${dirty ? 'amber' : ''}`}>{dirty ? '有未保存修改' : data.draft ? '草稿已保存' : '尚未保存草稿'}</span></div><form onSubmit={e => { e.preventDefault(); submit(false); }}><fieldset disabled={busy} className="shoot-fields">{Object.entries(detailLabels).map(([key, label]) => <label key={key}>{label}<textarea value={details[key]} maxLength={key === 'notes' ? 10000 : 5000} onChange={e => setDetails(d => ({ ...d, [key]: e.target.value }))} placeholder={key === 'assembly' ? '集合时间、地点；个别人员到场安排' : key === 'makeup' ? '各演员交妆时间' : key === 'transport' ? '出发、车辆、定位及入场要求' : key === 'meals' ? '早中晚餐时间、地点' : '天气备用、携带物品、部门注意事项'}/></label>)}</fieldset><div className="shoot-actions"><button disabled={busy}>保存草稿</button><button type="button" disabled={busy || !dirty} onClick={() => { setDetails(JSON.parse(baseline)); setError(''); }}>恢复已保存内容</button></div></form><p className="shoot-muted">草稿不会出现在已发布列表。页面提示未保存时，请先保存再离开。</p></section>
      <section className="shoot-call-preview"><div className="shoot-heading"><h2>发布预览</h2><button disabled={busy} onClick={() => load(false)}>刷新来源</button></div>{data.issues.length > 0 && <details className="shoot-issues"><summary>{data.issues.length} 项需核实，发布前请检查</summary>{data.issues.map((i, n) => <p key={n}>{i.message}</p>)}</details>}<NoticePreview source={data.source} details={details}/><div className="shoot-publish"><p className="shoot-muted">发布会保存当前预览快照。后续调整需另发新版本。</p><button type="button" className="shoot-primary" disabled={busy || !data.source.items.length} onClick={() => submit(true)}>确认发布固定版本</button></div></section></div>
    </>}
    <section className="shoot-history"><div className="shoot-heading"><h2>已发布通告</h2><small>{notices.length} 个版本</small></div>{notices.length ? notices.map(n => <details key={n.id}><summary>{n.date} · V{n.version} · {n.stale ? '需复核' : '来源未变'}{n.snapshot.format !== 'shooting_v4' ? ' · 历史通告' : ''}</summary>{n.stale && <div className="shoot-issues">{n.reasons.map((reason, i) => <p key={i}>{reason}</p>)}</div>}{n.snapshot.format === 'shooting_v4' ? <NoticePreview source={n.snapshot.source} details={n.snapshot.details}/> : <><p className="shoot-note">{n.snapshot.notes}</p>{(n.snapshot.schedule || []).map(r => <p key={r.id}>{r.data.start || '时间待定'} · {r.data.title}</p>)}</>}<a className="shoot-download" href={`/api/projects/${pid}/notices/${n.id}/export`}>下载本版通告 TXT ↗</a></details>) : <p className="shoot-muted">尚无已发布通告。</p>}</section>
  </div>;
}
