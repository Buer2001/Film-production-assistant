import React from 'react';

export default function EvidencePanel({ scene, content, onClose }) {
  if (!scene) return null;
  const evidence = scene.evidence || {};
  return <section className="evidence-panel">
    <div className="script-toolbar"><h2>第 {scene.scene_number || '未编号'} 场 · 原文核对</h2><button onClick={onClose}>收起</button></div>
    {evidence.line_start && <small>原文 L{evidence.line_start}–L{evidence.line_end}</small>}
    <pre>{evidence.text || '人工新增场次，尚无原文关联。'}</pre>
    <p>原文定位只证明来源，仍需核对内容是否准确、完整。</p>
    {scene.review_issues?.length > 0 && <div className="warning">{scene.review_issues.join('；')}</div>}
    {evidence.manual_fields?.length > 0 && <p>包含人工编辑字段：{evidence.manual_fields.join('、')}</p>}
    <details><summary>查看完整剧本</summary><pre>{content}</pre></details>
  </section>;
}
