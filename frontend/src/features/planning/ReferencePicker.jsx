import React, { useState } from 'react';

/** 可搜索的ID多选，显示已选标签；隐藏候选不会丢失既有引用。 */
export default function ReferencePicker({ label, options, value, onChange, disabled = false }) {
  const [query, setQuery] = useState('');
  const selected = new Set(value.map(String));
  const toggle = id => onChange(selected.has(String(id)) ? value.filter(x => String(x) !== String(id)) : [...value, id]);
  return <fieldset className="reference-picker" disabled={disabled}><legend>{label}</legend>
    <div className="reference-tags">{value.map(id => <button type="button" key={id} aria-label={`移除${options.find(o => String(o.id) === String(id))?.label || id}`} onClick={() => toggle(id)}>{options.find(o => String(o.id) === String(id))?.label || `资料不可用（${id}）`} ×</button>)}</div>
    <input aria-label={`搜索${label}`} value={query} onChange={e => setQuery(e.target.value)} placeholder="输入名称筛选，可勾选多项"/>
    <div className="reference-options">{options.filter(o => o.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())).map(o => <label key={o.id}><input type="checkbox" checked={selected.has(String(o.id))} onChange={() => toggle(o.id)}/>{o.label}</label>)}</div>
  </fieldset>;
}
