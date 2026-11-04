// 文件职责：编辑一条安排或逐场日志；只管理表单输入，保存和事务由工作区及后端负责。
import React, { useEffect, useRef } from 'react';
import { kinds, logStatuses, sceneLabel } from './shooting';

// 受控复选列表保留稳定 ID，避免同名人员或资源互相覆盖；空列表明确指引到准备页面维护。
function References({ title, options, selected, onChange }) {
  return <fieldset className="shoot-references"><legend>{title}</legend>{options.length ? <div>{options.map(o =>
    <label key={o.id}><input type="checkbox" checked={selected.includes(o.id)} onChange={e => onChange(e.target.checked ? [...selected, o.id] : selected.filter(id => id !== o.id))}/>{o.label}</label>)}</div> : <p className="shoot-muted">暂无资料，请先在项目日程维护。</p>}</fieldset>;
}

/** editor 保存 {type,id,data}；onChange 接受完整新输入。原生 dialog 提供焦点限制和 Esc 关闭。 */
export default function ShootingEditor({ editor, source, busy, error, onChange, onSave, onClose, onRefresh }) {
  const ref = useRef(null), isItem = editor.type === 'items', value = editor.data;
  useEffect(() => { ref.current.showModal(); }, []);
  function field(key, next) { onChange({ ...value, [key]: next }); }
  function chooseScene(id) {
    const scene = source.scenes.find(s => s.id === id);
    onChange({ ...value, scene_id: id, ...(isItem ? { location: scene?.location || value.location, reshoot_log_id: '' } : { item_id: '' }) });
  }
  const sameSceneItems = source.items.filter(r => r.data.kind === 'shoot' && r.data.scene_id === value.scene_id);
  return <dialog className="shoot-dialog" ref={ref} onCancel={e => { e.preventDefault(); if (!busy) onClose(); }} aria-labelledby="shoot-editor-title">
    <form onSubmit={e => { e.preventDefault(); onSave(); }}>
      <div className="shoot-heading"><div><small>{isItem ? 'SHOOTING PLAN' : 'DAILY REPORT'}</small><h2 id="shoot-editor-title">{editor.id ? '编辑' : '新增'}{isItem ? '安排' : '拍摄日志'}</h2></div><button type="button" disabled={busy} onClick={onClose}>关闭</button></div>
      {error && <div className="error" role="alert">{error}<button type="button" disabled={busy} onClick={onRefresh}>刷新版本，保留输入</button></div>}
      <fieldset disabled={busy} className="shoot-fields">
        {isItem && <><div className="shoot-form-grid"><label>安排类型<select value={value.kind} onChange={e => onChange({ ...value, kind: e.target.value, ...(e.target.value !== 'shoot' ? { scene_id: '', reshoot_log_id: '' } : {}) })}>{Object.entries(kinds).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label><label>状态<select value={value.status} onChange={e => field('status', e.target.value)}><option value="planned">已安排</option><option value="cancelled">已取消</option></select></label></div><label>安排名称<input autoFocus required maxLength={200} value={value.title} onChange={e => field('title', e.target.value)} placeholder="例如：第二场湖边拍摄"/></label></>}
        {(!isItem || value.kind === 'shoot') && <label>正式场次<select required value={value.scene_id || ''} onChange={e => chooseScene(e.target.value)}><option value="">选择已确认的场次</option>{source.scenes.map(s => <option key={s.id} value={s.id}>{sceneLabel(s)}</option>)}</select></label>}
        {isItem ? <>
          <div className="shoot-form-grid"><label>计划开始<input type="datetime-local" required value={value.start_at?.slice(0, 16) || ''} onChange={e => field('start_at', e.target.value)}/></label><label>计划结束<input type="datetime-local" required value={value.end_at?.slice(0, 16) || ''} onChange={e => field('end_at', e.target.value)}/></label></div>
          <div className="shoot-form-grid"><label>具体拍摄点<input maxLength={500} value={value.location} onChange={e => field('location', e.target.value)} placeholder="主场地内的具体位置"/></label><label>预计镜头数<input type="number" min="0" max="10000" value={value.shots ?? ''} onChange={e => field('shots', e.target.value)} placeholder="未知可留空"/></label></div>
          <References title="参与人员" options={source.people.map(p => ({ id: p.id, label: `${p.name}${p.department ? ' · ' + p.department : ''}` }))} selected={value.person_ids} onChange={v => field('person_ids', v)}/>
          <References title="占用资源（含场地）" options={source.resources.map(r => ({ id: r.id, label: r.data.title }))} selected={value.resource_ids} onChange={v => field('resource_ids', v)}/>
          {value.kind === 'shoot' && <label>补拍来源（可选）<select value={value.reshoot_log_id || ''} onChange={e => field('reshoot_log_id', e.target.value)}><option value="">普通拍摄安排</option>{source.logs.filter(l => l.data.scene_id === value.scene_id).map(l => <option key={l.id} value={l.id}>{l.data.date} · {l.data.remaining || l.data.reshoot_reason || logStatuses[l.data.status]}</option>)}</select></label>}
        </> : <>
          <label>对应安排<select value={value.item_id || ''} onChange={e => field('item_id', e.target.value)}><option value="">临时加拍（未预先安排）</option>{sameSceneItems.map(r => <option key={r.id} value={r.id}>{r.data.start_at.replace('T', ' ').slice(0, 16)} · {r.data.title}</option>)}</select></label>
          <div className="shoot-form-grid"><label>拍摄日期<input type="date" required value={value.date} onChange={e => field('date', e.target.value)}/></label><label>本次完成情况<select value={value.status} onChange={e => field('status', e.target.value)}>{Object.entries(logStatuses).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label></div>
          <div className="shoot-form-grid"><label>实际开始<input type="datetime-local" value={value.actual_start?.slice(0, 16) || ''} onChange={e => field('actual_start', e.target.value)}/></label><label>实际结束<input type="datetime-local" value={value.actual_end?.slice(0, 16) || ''} onChange={e => field('actual_end', e.target.value)}/></label></div>
          <label>剩余内容<textarea value={value.remaining} maxLength={10000} onChange={e => field('remaining', e.target.value)} placeholder="例如：门口反应特写尚未拍摄"/></label>
          <label>未完成或补拍原因<textarea value={value.reshoot_reason} maxLength={10000} onChange={e => field('reshoot_reason', e.target.value)} placeholder="按实际情况填写"/></label>
        </>}
        <label>备注<textarea value={value.notes} maxLength={10000} onChange={e => field('notes', e.target.value)}/></label>
      </fieldset>
      <footer className="shoot-actions"><span className="shoot-muted">{isItem ? '可并行安排；跨午夜请填写次日结束时间。' : '仅记录本次结果，不自动改写场次或通告。'}</span><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="shoot-primary" disabled={busy}>{busy ? '保存中…' : '保存'}</button></footer>
    </form>
  </dialog>;
}
