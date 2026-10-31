import React, { useState } from 'react';

export default function ScriptImport({ previous, busy, onImport }) {
  const [title, setTitle] = useState(previous?.title || '');
  const [label, setLabel] = useState('');
  const [text, setText] = useState('');
  const [source, setSource] = useState('粘贴文本');
  const [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  async function readFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(''); setReading(true);
    try {
      if (!file.name.toLowerCase().endsWith('.txt')) throw new Error('目前支持 UTF-8 TXT 或粘贴文本');
      if (file.size > 200000) throw new Error('文件过大，请限制在 50,000 字以内');
      const content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
      if (content.length > 50000) throw new Error('最多支持 50,000 字，请拆分剧本');
      setText(content); setSource(file.name);
      if (!title) setTitle(file.name.replace(/\.txt$/i, ''));
    } catch (err) { setError(err.message); }
    finally { setReading(false); }
  }
  return <section className="script-import">
    <h2>{previous ? '导入新版剧本' : '开始拆解剧本'}</h2>
    <p>{previous ? `基于 V${previous.version_number} 创建新版，旧版不会被覆盖。` : '先保存原文，再自动提取拍摄信息。支持粘贴文本、UTF-8 TXT。'}</p>
    <form onSubmit={e => { e.preventDefault(); onImport({ title, version_label: label,
      source_name: source, content: text, previous_script_id: previous?.id || null }); }}>
      <div className="columns">
        <label>剧本名称<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)}/></label>
        <label>版本名称<input maxLength={100} value={label} placeholder="例如：4.4 修改稿" onChange={e => setLabel(e.target.value)}/></label>
      </div>
      <label>读取 TXT 文件<input type="file" accept=".txt,text/plain" disabled={busy || reading} onChange={readFile}/></label>
      <label>剧本原文<textarea required maxLength={50000} rows={9} value={text} onChange={e => setText(e.target.value)}/></label>
      <small>{text.length.toLocaleString()} / 50,000 字 · 页数暂由人工填写</small>
      {error && <p role="alert" className="error">{error}</p>}
      <div><button disabled={busy || reading || !text.trim() || !title.trim()}>保存原文并拆解</button></div>
    </form>
  </section>;
}
