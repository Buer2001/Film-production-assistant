// 草稿使用普通表单编辑，保留未暴露的关联字段；保存由父组件进行版本复核。
import React from 'react';
import { editOperation, fieldLabel } from '../../workspace';
import { operationTitle, entityLabels } from './agentDraft';

export default function DraftEditor({ operations, busy, onChange, onSave, onCancel }) {
  function field(op, key, value) { onChange(editOperation(operations, op.op_id, key, value)); }
  return <form className="draft-editor" onSubmit={e => { e.preventDefault(); onSave(); }}>
    <h3>修改草稿</h3><p>修改后重新检查。未编辑的关联和其他资料保持原样。</p>
    {operations.map(op => <fieldset key={op.op_id} disabled={busy}>
      <legend>{entityLabels[op.entity]} · {operationTitle(op)}</legend>
      {op.action === 'cancel' ? <p>此项拟取消。如需保留，可移除这项操作。</p> : <>
        <label>名称<input required maxLength={200} value={op.patch.title ?? op.before?.title ?? ''} onChange={e => field(op,'title',e.target.value)}/></label>
        <div className="columns">{(op.entity === 'project_task' ? ['planned_start','planned_end'] : ['start_at','end_at']).map(key => <label key={key}>{fieldLabel(key)}<input type={op.entity === 'project_task' ? 'date' : 'datetime-local'} required={op.entity === 'shooting_item'} value={(op.patch[key] !== undefined ? op.patch[key] : op.before?.[key]) || ''} onChange={e => field(op,key,e.target.value)}/></label>)}</div>
        {op.entity === 'project_task' ? <label>说明<textarea value={op.patch.description ?? op.before?.description ?? ''} onChange={e => field(op,'description',e.target.value)}/></label> : <><label>地点<input value={op.patch.location ?? op.before?.location ?? ''} onChange={e => field(op,'location',e.target.value)}/></label><label>备注<textarea value={op.patch.notes ?? op.before?.notes ?? ''} onChange={e => field(op,'notes',e.target.value)}/></label></>}
      </>}
      <button type="button" onClick={() => onChange(operations.filter(item => item.op_id !== op.op_id))}>从草稿移除此项</button>
    </fieldset>)}
    {!operations.length && <p>没有操作可保存，可取消编辑返回原草稿。</p>}
    <div className="form-actions"><button className="primary" disabled={busy || !operations.length}>保存修改并重新检查</button><button type="button" disabled={busy} onClick={onCancel}>取消编辑</button></div>
  </form>;
}
