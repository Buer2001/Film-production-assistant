import React, { useEffect, useState } from 'react';
export default function ProgressPanel({ doc, connection, onReconnect, onStop, disabled }) {
  const p = doc.progress, [now, setNow] = useState(Date.now());
  useEffect(() => { if (p?.state !== 'running') return; setNow(Date.now()); const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [p?.state]);
  if (!p) return null;
  const running = p.state === 'running', active = doc.scenes.filter(s => s.parse_status === 'running');
  const manual = doc.scenes.filter(s => s.resolution === 'manual').length;
  const excluded = doc.scenes.filter(s => s.resolution === 'excluded').length;
  const seconds = p.started_at ? Math.max(0, Math.floor((now - Date.parse(p.started_at)) / 1000)) : 0;
  return <section className="parse-progress" aria-label="拆解进度">
    <div className="script-toolbar"><strong>{doc.can_start_parse ? '尚未开始拆解' : ({ running: '正在逐场拆解', review: '拆解结束，请核对', interrupted: '拆解已中止，已完成结果保留', confirmed: '本版已确认' })[p.state] || '拆解进度'}</strong>
      {running && <span role="status">{connection === 'connected' ? '进度已连接' : connection === 'disconnected' ? '连接断开，正在重连' : '正在连接进度'}</span>}
      {running && connection !== 'connected' && <button onClick={onReconnect}>重新连接</button>}
      {running && <button disabled={disabled} onClick={onStop}>中止拆解并保留结果</button>}
    </div>
    <p>总场数 {doc.can_start_parse ? '待识别' : p.total ?? '待识别'} · 自动完成 {p.completed ?? 0} · 模型失败 {p.failed ?? 0} · 人工处理 {manual} · 已排除 {excluded} · 进行中 {active.length}{running && p.started_at ? ` · 已用时 ${seconds} 秒` : ''}</p>
    {active.length > 0 && <p>正在处理：{active.map(s => s.scene_number || '未编号场次').join('、')}</p>}
    {running && <small>每场完成即显示，可直接核对和编辑。失败场次不会阻止其他场次继续。</small>}
  </section>;
}
