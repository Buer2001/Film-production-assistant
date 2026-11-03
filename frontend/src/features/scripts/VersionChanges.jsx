import React from 'react';
import { columns } from './BreakdownTable';
const labels = { ...Object.fromEntries(columns), custom_values: '自定义字段' };

export default function VersionChanges({ doc, disabled, onChange, onDeletedReview }) {
  if (!doc.previous_script_id) return null;
  const changes = doc.comparison;
  const unlinked = [...(changes.unlinked || []), ...changes.deleted];
  return <section className="version-changes">
    <h2>相对上一版的变化</h2>
    <p>新增 {changes.added.length} · 修改 {changes.changed.length} · 待匹配 {changes.pending.length} · 未关联旧场次 {unlinked.length}</p>
    <p>对应关系用于比较两个版本，逐场匹配和核对均可选。可以直接确认本版，未匹配的场次暂不认定为新增，未关联的旧场次暂不认定为删除。拆场、合场可在备注说明。</p>
    {doc.scenes.map((row, index) => {
      const delta = changes.changed.find(c => c.id === row.id);
      const old = doc.previous_scenes.find(s => s.id === row.previous_scene_id);
      return <details key={row.id || row.local_id}>
        <summary>第 {row.scene_number || '未编号'} 场 · {row.match_status === 'pending' ? '待匹配' : row.match_status === 'new' ? '新增' : delta ? '有变化' : '原文对应'}
          {row.change_reviewed ? ' · 已核对' : ' · 待核对'}</summary>
        <label>对应上一版场次<select aria-label={'对应旧场次 ' + (row.scene_number || index + 1)} disabled={disabled}
          value={row.match_status === 'new' ? '__new' : row.previous_scene_id || ''}
          onChange={e => {
            onChange(index, 'previous_scene_id', e.target.value === '__new' ? null : e.target.value || null);
            onChange(index, 'match_status', e.target.value === '__new' ? 'new' : e.target.value ? 'matched' : 'pending');
            onChange(index, 'change_reviewed', false);
          }}>
          <option value="">暂不匹配</option><option value="__new">确认为新增场次</option>
          {doc.previous_scenes.map(s => <option key={s.id} value={s.id}>{s.scene_number} · {s.location} · {s.summary}</option>)}
        </select></label>
        {delta && <p>变化字段：{delta.fields.map(k => labels[k] || k).join('、')}</p>}
        {old && <div className="columns"><div><h3>上一版原文</h3><pre>{old.evidence.text}</pre>
          <details><summary>上一版拆解和人工补充（可复制）</summary><pre>{JSON.stringify({ ...Object.fromEntries(columns.map(([key, label]) => [label, old[key]])), ...Object.fromEntries((doc.custom_fields || []).map(f => [f.name, old.custom_values?.[f.id] || ''])) }, null, 2)}</pre></details></div>
          <div><h3>本版原文</h3><pre>{row.evidence.text}</pre></div></div>}
        {!old && <p>请在拆解表中核对本场信息。</p>}
        <label className="inline-check"><input type="checkbox" disabled={disabled || row.match_status === 'pending'}
          checked={row.change_reviewed} onChange={e => onChange(index, 'change_reviewed', e.target.checked)}/>已核对本场变化（可选）</label>
      </details>;
    })}
    {unlinked.length > 0 && <div className="warning">
      <h3>上一版未关联场次</h3>{unlinked.map(s => <p key={s.id}>{s.scene_number} · {s.location} · {s.summary}</p>)}
      {changes.pending.length > 0 && <p>仍有新版场次未匹配，以下旧场次不认定为删除。</p>}
      <label className="inline-check"><input type="checkbox" checked={doc.deleted_reviewed} disabled={disabled}
        onChange={e => onDeletedReview(e.target.checked)}/>已核对以上旧场次的删除或拆合情况（可选）</label>
    </div>}
  </section>;
}
