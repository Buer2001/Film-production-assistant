import React, { useEffect, useState } from 'react';
import { api } from './api/client';

export function ScriptPanel({ pid, revision, busy, act, onDraft }) {
  const [text, setText] = useState(''), [source, setSource] = useState('粘贴剧本');
  const [results, setResults] = useState([]);
  const [historyError, setHistoryError] = useState('');
  useEffect(() => {
    let active = true;
    api(`/projects/${pid}/scripts`).then(data => {
      if (active) setResults(old => [...old, ...data.filter(x => !old.some(y => y.id === x.id))]);
    }).catch(error => { if (active) setHistoryError('读取解析历史失败：' + error.message); });
    return () => { active = false; };
  }, [pid]);
  return <section><h2>剧本解析</h2><p>粘贴文本或读取 UTF-8 TXT，最多 50,000 字、50 场。点击解析后发送给已配置的模型。结果先核对原文，再生成待确认草稿。</p>
    {historyError && <p role="alert" className="warning">{historyError}</p>}
    <form onSubmit={e => { e.preventDefault(); act(async () => {
      const result = await api(`/projects/${pid}/scripts/parse`, { text, source_name: source, base_revision: revision });
      setResults(old => [result, ...old]);
    }); }}>
      <label>来源名称<input required maxLength={200} value={source} onChange={e => setSource(e.target.value)}/></label>
      <label>读取 TXT 文件<input type="file" accept=".txt,text/plain" disabled={busy} onChange={e => {
        const file = e.target.files?.[0]; if (!file) return;
        act(async () => {
          if (file.size > 200000) throw new Error('文件过大，请拆分为不超过 50,000 字的文本');
          const value = await file.text();
          if (value.length > 50000) throw new Error('文本超过 50,000 字，请分段解析');
          if (value.includes('\uFFFD')) throw new Error('文件编码异常，请另存为 UTF-8 TXT');
          setText(value); setSource(file.name.slice(0, 200));
        });
      }}/></label>
      <label>剧本文本<textarea required maxLength={50000} rows={10} value={text} onChange={e => setText(e.target.value)}/></label>
      <button disabled={busy || !text.trim()}>解析并预览</button>
    </form>
    {results.map(result => <details key={result.id} open={results[0]?.id === result.id}><summary>{result.source_name} · {result.scenes.length} 场 · 基于版本 {result.base_revision}</summary>
      <p>{result.limitations}</p>{result.warnings.map((warning, i) => <p className="warning" key={i}>{warning}</p>)}
      {result.scenes.map((scene, i) => <article key={i}><h3>{scene.title}</h3>
        <p>人物：{scene.characters.join('、') || '待确认'} · 场地：{scene.location || '待确认'}</p>
        <p>道具：{scene.props.join('、') || '未提取'} · 昼夜：{scene.time || '待确认'} · 内外景：{scene.interior || '待确认'}</p>
        {scene.questions.map((q, n) => <p className="warning" key={n}>{q}</p>)}
        <details><summary>查看原文 L{scene.line_start}–{scene.line_end}</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{scene.evidence}</pre></details>
      </article>)}
      <button disabled={busy || (result.base_revision !== revision && !result.change_id)} onClick={() => act(async () => {
        const draft = await api(`/projects/${pid}/scripts/${result.id}/draft`, {});
        setResults(old => old.map(x => x.id === result.id ? { ...x, change_id: draft.id } : x));
        await onDraft();
      })}>{result.change_id ? '草稿已生成（见待确认区）' : '已核对，生成待确认草稿'}</button>
      {result.base_revision !== revision && !result.change_id && <p>数据已变化，请重新解析。</p>}
    </details>)}
  </section>;
}

export function ImpactReport({ result, revision }) {
  if (!result) return null;
  return <section aria-live="polite"><h2>影响分析结果</h2>
    <p>基于版本 {result.base_revision}；{result.base_revision !== revision ? '数据已变化，请重新分析。' : '只读分析，尚未修改正式数据。'}</p>
    <p>{result.limitations}</p>{result.warnings.map((w, i) => <p className="warning" key={i}>{w}</p>)}
    {!result.records.length && <p>没有找到明确关联，请核对资源名称和场次关联是否完整。</p>}
    {result.records.map(r => <p key={r.id}><strong>{r.title}</strong> · {r.status}<br/>{r.path.join(' → ')}</p>)}
    {result.suggestions.map((s, i) => <p className="warning" key={i}>{result.records.find(r => r.id === s.record_id)?.title}：{s.action}</p>)}
    {result.notices.map(n => <p className="warning" key={n.id}>{n.date} 通告 V{n.version}：{n.action}</p>)}
  </section>;
}
