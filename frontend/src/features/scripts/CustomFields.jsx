// 维护项目共用自定义文本列，单独保存字段设置并通知父层导航锁。
import React, { useEffect, useState } from 'react';
import { scriptApi } from './api';

/**
 * 参数：pid 为项目 ID，disabled 控制编辑；onChange 接收已保存字段，onDirtyChange/onBusyChange 通知状态。
 * 返回字段设置 JSX；按 saved.revision 保存，既有列删除仅隐藏，已有场次内容保留。
 */
export default function CustomFields({ pid, disabled, onChange, onDirtyChange, onBusyChange }) {
  const [saved, setSaved] = useState(null), [fields, setFields] = useState([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const dirty = saved !== null && JSON.stringify(fields) !== JSON.stringify(saved.fields);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);
  useEffect(() => {
    const warn = event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => {
    let active = true;
    setSaved(null); setFields([]); setError(''); onChange([]);
    scriptApi.fields(pid).then(value => {
      if (active) { setSaved(value); setFields(value.fields); onChange(value.fields); }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [pid, onChange]);
  /**
   * 参数 index/key/value 指定字段设置项；只更新本地表单副本，等待显式保存。
   */
  function update(index, key, value) {
    setFields(fields.map((field, i) => i === index ? { ...field, [key]: value } : field));
  }
  /**
   * 使用已读设置版本提交字段数组，成功后同步保存基线和父层列定义；失败时保留本地设置。
   */
  async function save() {
    setBusy(true); setError('');
    try {
      const value = await scriptApi.saveFields(pid, { revision: saved.revision, fields });
      setSaved(value); setFields(value.fields); onChange(value.fields);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  /**
   * 需要时先确认丢弃本地修改，再读取最新字段及 revision，成功后同步父层。
   */
  async function reload() {
    if (dirty && !window.confirm('重新加载字段设置会丢弃尚未保存的列名修改，继续吗？')) return;
    setBusy(true); setError('');
    try {
      const value = await scriptApi.fields(pid);
      setSaved(value); setFields(value.fields); onChange(value.fields);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <details className="custom-fields">
    <summary>自定义字段{dirty ? ' · 设置未保存' : ''}</summary>
    <p className="script-hint">项目内共用，保存设置后显示为文本列，由你填写，不由 AI 提取。删除只隐藏列，已有内容保留。</p>
    {error && <p className="error" role="alert">{error}</p>}
    {fields.map((field, index) => <div className="custom-field-row" key={field.id || `new-${index}`}>
      <input aria-label={`自定义字段名称 ${index + 1}`} placeholder="例如：车辆" maxLength={50}
        disabled={disabled || busy || !field.active} value={field.name} onChange={e => update(index, 'name', e.target.value)}/>
      <input aria-label={`自定义字段说明 ${index + 1}`} placeholder="填写说明（可选）" maxLength={300}
        disabled={disabled || busy || !field.active} value={field.description} onChange={e => update(index, 'description', e.target.value)}/>
      <button disabled={disabled || busy} onClick={() => {
        if (!field.id) { setFields(fields.filter((_, i) => i !== index)); return; }
        if (field.active && !window.confirm('隐藏此列？已有场次内容会保留，可恢复显示。')) return;
        update(index, 'active', !field.active);
      }}>{field.active ? '删除列' : '恢复列'}</button>
    </div>)}
    <div className="script-toolbar">
      <button disabled={disabled || busy || !saved || fields.length >= 50 || fields.filter(f => f.active).length >= 20}
        onClick={() => setFields([...fields, { name: '', description: '', active: true }])}>添加自定义字段</button>
      <button disabled={disabled || busy || !dirty} onClick={save}>{busy ? '保存中…' : '保存字段设置'}</button>
      <button disabled={disabled || busy} onClick={reload}>重新加载字段设置</button>
    </div>
  </details>;
}
