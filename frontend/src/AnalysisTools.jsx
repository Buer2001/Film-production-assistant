import React from 'react';

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
