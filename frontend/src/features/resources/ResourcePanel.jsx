// 维护资源基础记录和筹备落实资料，独立于日程任务保存。
import React, { useState } from 'react';
import { AvailabilityEditor, periodText } from '../preparation/PeriodEditor';
import { api } from '../../api/client';

const initial = { title: '', category: 'other', status: '待确认', owner: '', notes: '', source: '', scene_ids: [], resources: [], date: null, start: null, minutes: 60, amount: '0' };
/** 返回独立的空资源编辑副本；初始筹备资料仍由表单补齐，不把金额零推断为免费。 */
export const createResourceDraft = () => ({ data: structuredClone(initial) });

// 资源独立于任务保存，使用项目revision；编辑期间由父页面统一禁止切页及其他写入。
/**
 * 参数：pid/resources/people/revision 提供项目资料和版本；disabled 控制操作，editing/onEditing 由父层保存编辑副本。
 * onBusy 通知请求状态，onChanged 在成功后刷新；返回资源列表及编辑表单 JSX。
 * editorOnly 为 true 时仅显示侧栏表单，不重复显示资源列表；仍使用当前项目版本提交。
 * 历史记录和筹备资料分别保留，费用状态改变时由专用逻辑处理金额字段。
 */
export default function ResourcePanel({ pid, resources, people = [], revision, disabled, editing, onEditing, onBusy, onChanged, editorOnly = false }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  /**
   * 参数：path/body/method 为资源接口参数。写入成功后关闭编辑并刷新，写入请求失败时保留草稿；写入或刷新失败均显示错误，最终通知父层解除忙碌状态。
   */
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
  // 老资源没有落实资料时保持未知，不能把旧 amount=0 解释为免费。
  const prep = { status: 'pending', contact_person_id: null, contact_name: '', contact: '', availability: [], cost_status: 'unknown', cost_amount: null, notes: '', ...editing?.data.preparation };
  const preparation = (key, value) => field('preparation', { ...prep, [key]: value });
  const costStatus = status => field('preparation', { ...prep, cost_status: status, cost_amount: status === 'unknown' ? null : status === 'free' ? 0 : prep.cost_amount });
  // 日历侧栏复用原资源表单及保存流程，旧列表入口继续保持兼容。
  const content = <>
      {!editorOnly && <p className="plan-muted">任务通过资源ID关联；尚未落实的需求可先在任务中填写名称。可在下方记录落实情况、实际联系人、可用时段和费用。</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!editorOnly && <><button disabled={disabled || busy || !!editing} onClick={() => { setError(''); onEditing(createResourceDraft()); }}>新增资源</button>
      {resources.map(r => {
      const contact = people.find(p => p.id === r.data.preparation?.contact_person_id);
      return <article className="record" id={`resource-${r.id}`} key={r.id}>
        <div>
          <h3>{r.data.title}</h3>
          <p>{r.data.category} · 落实状态：{({ pending: '待落实', contacting: '联系中', confirmed: '已确认', unavailable: '不可用' })[r.data.preparation?.status] || '未知'}</p>
          <p>联系人：{contact?.name || r.data.preparation?.contact_name || (!r.data.preparation && r.data.owner ? `${r.data.owner}（历史联系人）` : '待填')} · {contact?.phone || contact?.contact || r.data.preparation?.contact || '联系方式待填'}</p>
          <p>{r.data.preparation?.notes}</p>
          <p>{r.data.preparation?.availability?.map(x => `${x.state === 'available' ? '可用' : '不可用'}：${periodText(x)}`).join('；') || '可用情况未知'}</p>
        </div>
        <div>
          <button disabled={disabled || busy || !!editing} onClick={() => onEditing({ id: r.id, data: structuredClone(r.data) })}>编辑资源</button>
          <button disabled={disabled || busy || !!editing} onClick={() => { if (window.confirm(`删除资源“${r.data.title}”？已被任务或草稿引用的资源不能删除。`)) mutate(`/${r.id}?revision=${revision}`, undefined, 'DELETE'); }}>删除资源</button>
        </div>
      </article>; })}</>}
      {editing && <form onSubmit={e => { e.preventDefault(); mutate(editing.id ? `/${editing.id}` : '', { revision, resource: editing.data }, editing.id ? 'PUT' : 'POST'); }}>
        <fieldset disabled={busy}>
          <label>资源名称
            <input required maxLength={200} value={editing.data.title} onChange={e => field('title', e.target.value)}/>
          </label>
          <label>资源类型
            <select value={editing.data.category} onChange={e => field('category', e.target.value)}>{[['location', '场地'], ['equipment', '器材'], ['prop', '道具'], ['costume', '服装'], ['other', '其他'], ...(!['location', 'equipment', 'prop', 'costume', 'other'].includes(editing.data.category) ? [[editing.data.category, editing.data.category || '未分类']] : [])].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          </label>
          {/* 历史字段保留原值供旧功能使用，不与落实资料自动同步，避免改写既有事实。 */}
          <details>
            <summary>历史资源资料</summary>
            <p className="plan-muted">以下保留原始记录，筹备检查使用下方落实资料。</p>
            <label>确认情况
              <select value={editing.data.status} onChange={e => field('status', e.target.value)}>{['待确认', '进行中', '已确认', '已完成', '待补拍'].map(s => <option key={s}>{s}</option>)}</select>
            </label>
            <label>联系人或负责人
              <input value={editing.data.owner} onChange={e => field('owner', e.target.value)}/>
            </label>
            <label>原有资源说明
              <textarea value={editing.data.notes} onChange={e => field('notes', e.target.value)}/>
            </label>
          </details>
          <label>来源
            <input value={editing.data.source} onChange={e => field('source', e.target.value)}/>
          </label>
          <h3>落实资料</h3>
          <label>落实状态
            <select value={prep.status} onChange={e => preparation('status', e.target.value)}>{Object.entries({ pending: '待落实', contacting: '联系中', confirmed: '已确认', unavailable: '不可用' }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          </label>
          <label>关联联系人
            <select value={prep.contact_person_id || ''} onChange={e => preparation('contact_person_id', e.target.value || null)}><option value="">不关联／手填</option>{people.map(p => <option key={p.id} value={p.id}>{p.name} · {p.phone || p.contact || '联系方式待填'}</option>)}</select>
          </label>
          <label>手填联系人（保留）
            <input value={prep.contact_name} onChange={e => preparation('contact_name', e.target.value)}/>
          </label>
          <label>手填联系方式（保留）
            <input value={prep.contact} onChange={e => preparation('contact', e.target.value)}/>
          </label>
          <AvailabilityEditor value={prep.availability} onChange={v => preparation('availability', v)}/>
          <label>费用状态
            <select value={prep.cost_status} onChange={e => costStatus(e.target.value)}>{Object.entries({ unknown: '未知', free: '免费', quoted: '已报价', confirmed: '已确认' }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          </label>
          <label>费用金额
            <input type="number" min="0" step="0.01" disabled={['unknown', 'free'].includes(prep.cost_status)} required={['quoted', 'confirmed'].includes(prep.cost_status)} value={prep.cost_amount ?? ''} onChange={e => preparation('cost_amount', e.target.value === '' ? null : Number(e.target.value))}/>
          </label>
          <label>落实说明
            <textarea value={prep.notes} onChange={e => preparation('notes', e.target.value)}/>
          </label>
          <button>确认保存资源</button>
          <button type="button" onClick={() => onEditing(null)}>取消编辑</button>
        </fieldset>
      </form>}
  </>;
  return editorOnly ? <div className="availability-editor">{content}</div> : <section>
    <details id="project-resources"><summary>项目资源 · {resources.length}</summary>{content}</details>
  </section>;
}
