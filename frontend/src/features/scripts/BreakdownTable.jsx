// 展示可筛选的逐场拆解宽表，把字段编辑及结构调整交给父层草稿管理。
import React, { useState } from 'react';

export const columns = [
  ['scene_number', '场号'], ['interior_exterior', '内外'], ['atmosphere', '气氛'],
  ['word_count', '字数'], ['location', '场景'], ['summary', '内容'],
  ['cast', '角色'], ['makeup_costume', '妆造'], ['action_props', '戏用道具'],
  ['other_props', '其他道具'], ['notes', '备注'],
];
const multiple = new Set(['cast', 'makeup_costume', 'action_props', 'other_props']);

/**
 * 参数：field 决定角色、妆造或道具结构，value 为数组，disabled 控制编辑，onChange 接收新数组；返回多条目编辑控件 JSX。
 */
function MultipleEditor({ field, value, disabled, onChange }) {
  const isMakeup = field === 'makeup_costume', isCast = field === 'cast';
  const nameKey = isMakeup ? 'character' : 'name';
  function update(index, key, val) {
    onChange(value.map((item, i) => i === index ? { ...item, [key]: val } : item));
  }
  return <div className="multi-editor">
    {value.map((item, index) => <div className="multi-entry" key={index}>
      <input aria-label={isMakeup ? '妆造角色' : isCast ? '角色名称' : '道具名称'}
        disabled={disabled} maxLength={200} value={item[nameKey]}
        onChange={e => update(index, nameKey, e.target.value)} placeholder={isMakeup ? '角色' : '名称'}/>
      {isCast ? <select aria-label="角色分类" disabled={disabled} value={item.category}
        onChange={e => update(index, 'category', e.target.value)}>
        {['主要角色', '配角', '群演', '待确认'].map(x => <option key={x}>{x}</option>)}
      </select> : isMakeup ? <textarea aria-label="妆造要求" maxLength={3000}
        disabled={disabled} value={item.description} onChange={e => update(index, 'description', e.target.value)}/> : null}
      {!disabled && <button type="button" aria-label="移除此项" onClick={() => onChange(value.filter((_, i) => i !== index))}>×</button>}
    </div>)}
    {!disabled && <button type="button" onClick={() => onChange([...value,
      isCast ? { name: '', category: '待确认' } : { [nameKey]: '', description: '' }])}>＋ 添加</button>}
  </div>;
}

/**
 * 参数：scenes/comparison 为场次及比较结果，selected/onSelect 控制原文选择，customFields 为自定义列。
 * onChange/onAdd/onDelete/onMove/onRetry 处理字段、结构及重试；各 disabled 标志限制操作。返回拆解表 JSX。
 * 筛选保留原场次下标，避免编辑搜索结果时写入错误场次。
 */
export default function BreakdownTable({ scenes, comparison, disabled, selected, onSelect, onChange, onAdd, onDelete, onMove, onRetry, retryDisabled, structuralDisabled, customFields = [] }) {
  const [query, setQuery] = useState(''), [filter, setFilter] = useState('all');
  const changed = new Set([...comparison.changed, ...comparison.added, ...comparison.pending].map(r => r.id));
  const visible = scenes.map((row, index) => ({ row, index })).filter(({ row }) =>
    JSON.stringify(row).toLowerCase().includes(query.toLowerCase()) &&
    (filter === 'all' || (filter === 'issues' ? row.review_issues.length > 0 : changed.has(row.id))));
  return <section className="breakdown-section">
    <div className="script-toolbar">
      <h2>逐场拆解 <small>{scenes.length} 场</small></h2>
      <input aria-label="搜索拆解" placeholder="搜索场号、角色、场景…" value={query} onChange={e => setQuery(e.target.value)}/>
      <select aria-label="筛选拆解" value={filter} onChange={e => setFilter(e.target.value)}>
        <option value="all">全部场次</option><option value="issues">有待补项</option><option value="changed">有变化</option>
      </select>
      {!disabled && !structuralDisabled && <button onClick={onAdd}>增加场次</button>}
    </div>
    <p className="script-hint">直接编辑单元格，停止输入后自动保存。选择“核对原文”查看证据；角色和道具名称不能为空。宽表可横向滚动。</p>
    <p className="script-hint">字数不含场次标题和空白，标点计入；无原文的手填场次显示“—”。内容概括主要事件，道具只列名称及必要特征。</p>
    <div className="breakdown-scroll"><table className="breakdown-table">
      <thead><tr><th>核对</th>{columns.map(([key, label]) => <th key={key}>{label}</th>)}
        {customFields.filter(f => f.active).map(f => <th key={f.id} title={f.description}>{f.name}</th>)}<th>操作</th></tr></thead>
      <tbody>{visible.map(({ row, index }) => <tr key={row.id || row.local_id}
        className={selected === (row.id || row.local_id) ? 'selected' : ''}>
        <td><button onClick={() => onSelect(row.id || row.local_id)}>核对原文</button>
          <span className="script-tag">{row.resolution === 'excluded' ? '已排除' : row.resolution === 'manual' ? '人工处理' : ({ pending: '等待拆解', running: '正在拆解', succeeded: '已完成', failed: '拆解失败' })[row.parse_status] || '待核对'}</span>
          {(row.parse_status === 'failed' || (!structuralDisabled && ['pending', 'running'].includes(row.parse_status))) && <div className="scene-failure" role="status">
            <p>{row.parse_error || (row.parse_status === 'failed' ? '本场拆解失败，请重试或人工处理。' : '本场尚未完成，可重试或人工处理。')}</p>
            <details><summary>查看本场原文</summary><pre>{row.evidence?.text || '请点击核对原文查看完整剧本。'}</pre></details>
            {!disabled && <>
              <button disabled={retryDisabled} onClick={() => onRetry(row.id)}>重试本场</button>
              {structuralDisabled && <small>本轮拆解结束后可单场重试。</small>}
              <button onClick={() => onChange(index, 'resolution', 'manual')}>已人工填写，标为已处理</button>
              <button onClick={() => { if (window.confirm('确定这段原文不是有效场次，并从确认结果中排除？')) onChange(index, 'resolution', 'excluded'); }}>排除非场次</button>
            </>}
          </div>}
          {row.resolution === 'excluded' && <small>已排除，本场确认时不会入库。</small>}
          {row.resolution === 'excluded' && !disabled && <button onClick={() => onChange(index, 'resolution', 'pending')}>撤销排除</button>}
          <small>{row.review_issues.length > 0 ? `${row.review_issues.length} 项待补` : '信息完整'}</small>
          {row.match_status === 'pending' && <span className="script-tag">待匹配</span>}
        </td>
        {columns.map(([key, label]) => <td key={key}>
          {multiple.has(key) ? <MultipleEditor field={key} value={row[key] || []} disabled={disabled}
            onChange={value => onChange(index, key, value)}/>
            : key === 'word_count' ? <span aria-label={label + ' ' + (row.scene_number || index + 1)}>{row.word_count ?? '—'}</span>
            : <textarea aria-label={label + ' ' + (row.scene_number || index + 1)} disabled={disabled}
              value={row[key] || ''} onChange={e => onChange(index, key, e.target.value)}/>}
        </td>)}
        {customFields.filter(f => f.active).map(f => <td key={f.id}>
          <textarea aria-label={`${f.name} ${row.scene_number || index + 1}`} title={f.description} maxLength={3000}
            disabled={disabled} value={row.custom_values?.[f.id] || ''}
            onChange={e => onChange(index, 'custom_values', { ...row.custom_values, [f.id]: e.target.value })}/>
        </td>)}
        <td>{!disabled && <div className="scene-actions">
          <button aria-label="场次上移" disabled={structuralDisabled || index === 0} onClick={() => onMove(index, -1)}>上移</button>
          <button aria-label="场次下移" disabled={structuralDisabled || index === scenes.length - 1} onClick={() => onMove(index, 1)}>下移</button>
          {row.resolution !== 'excluded' && <button onClick={() => onDelete(index)}>排除</button>}
        </div>}</td>
      </tr>)}</tbody>
    </table></div>
    {!visible.length && <p>没有符合条件的场次。</p>}
  </section>;
}
