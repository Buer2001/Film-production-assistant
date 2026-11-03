import React, { useState } from 'react';
import { api } from '../../api/client';

const initial = { title: '', category: 'other', status: '待确认', owner: '', notes: '', source: '', scene_ids: [], resources: [], date: null, start: null, minutes: 60, amount: '0' };

// 资源独立于任务保存，使用项目revision；编辑期间由父页面统一禁止切页及其他写入。
export default function ResourcePanel({ pid, resources, revision, disabled, editing, onEditing, onBusy, onChanged }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function mutate(path, body, method) {
    setBusy(true); onBusy(true); setError('');
    try {
      await api(`/projects/${pid}/resources${path}`, body, { method });
      onEditing(null);
      await onChanged();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); onBusy(false); }
  }
  const field = (key, value) => onEditing({ ...editing, data: { ...editing.data, [key]: value } });
  return <section><details><summary>项目资源 · {resources.length}</summary>
    <p className="plan-muted">任务通过资源ID关联；尚未落实的需求可先在任务中填写名称。使用时间和联系人可暂记在备注。</p>
    {error && <p className="error" role="alert">{error}</p>}
    <button disabled={disabled || busy || !!editing} onClick={() => { setError(''); onEditing({ data: { ...initial } }); }}>新增资源</button>
    {resources.map(r => <article className="record" key={r.id}><div><h3>{r.data.title}</h3><p>{r.data.category} · {r.data.status} · {r.data.owner || '联系人待填'}</p><p>{r.data.notes}</p></div><div>
      <button disabled={disabled || busy || !!editing} onClick={() => onEditing({ id: r.id, data: structuredClone(r.data) })}>编辑资源</button>
      <button disabled={disabled || busy || !!editing} onClick={() => { if (window.confirm(`删除资源“${r.data.title}”？已被任务或草稿引用的资源不能删除。`)) mutate(`/${r.id}?revision=${revision}`, undefined, 'DELETE'); }}>删除资源</button>
    </div></article>)}
    {editing && <form onSubmit={e => { e.preventDefault(); mutate(editing.id ? `/${editing.id}` : '', { revision, resource: editing.data }, editing.id ? 'PUT' : 'POST'); }}><fieldset disabled={busy}>
      <label>资源名称<input required maxLength={200} value={editing.data.title} onChange={e => field('title', e.target.value)}/></label>
      <label>资源类型<select value={editing.data.category} onChange={e => field('category', e.target.value)}>{[['location', '场地'], ['equipment', '器材'], ['prop', '道具'], ['costume', '服装'], ['other', '其他'], ...(!['location', 'equipment', 'prop', 'costume', 'other'].includes(editing.data.category) ? [[editing.data.category, editing.data.category || '未分类']] : [])].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>确认情况<select value={editing.data.status} onChange={e => field('status', e.target.value)}>{['待确认', '进行中', '已确认', '已完成', '待补拍'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label>联系人或负责人<input value={editing.data.owner} onChange={e => field('owner', e.target.value)}/></label>
      <label>使用时间、联系方式及说明<textarea value={editing.data.notes} onChange={e => field('notes', e.target.value)}/></label>
      <label>来源<input value={editing.data.source} onChange={e => field('source', e.target.value)}/></label>
      <button>确认保存资源</button><button type="button" onClick={() => onEditing(null)}>取消编辑</button>
    </fieldset></form>}
  </details></section>;
}
