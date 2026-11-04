// 以模态弹窗只读回看任务关联的已确认剧本拆解和原文依据。
import React, { useEffect, useRef, useState } from 'react';
import EvidencePanel from '../scripts/EvidencePanel';
import { planningApi } from './api';

/**
 * 参数：pid/task/sceneRef 定位接口，trigger 为关闭后恢复焦点的元素，onClose 关闭弹窗；返回 dialog JSX。
 * 关联或重试次数变化时重新请求，清理标记阻止旧响应回写；卸载时关闭原生弹窗并恢复焦点。
 */
export default function TaskEvidence({ pid, task, sceneRef, trigger, onClose }) {
  const dialog = useRef(null);
  const [data, setData] = useState(null), [error, setError] = useState(''), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const node = dialog.current;
    node.showModal();
    return () => { node.close(); trigger?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    setData(null); setError('');
    const query = new URLSearchParams({ script_id: sceneRef.script_id, scene_id: sceneRef.scene_id });
    planningApi(pid, `/tasks/${encodeURIComponent(task.id)}/evidence?${query}`).then(result => {
      if (active) setData(result);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [pid, task.id, sceneRef.script_id, sceneRef.scene_id, attempt]);
  const names = entries => (entries || []).map(x => x.name).filter(Boolean).join('、') || '未填写';
  return <dialog ref={dialog} className="plan-evidence-dialog" aria-labelledby="task-evidence-title" onCancel={e => { e.preventDefault(); onClose(); }}>
    <div className="plan-toolbar"><h2 id="task-evidence-title">任务拆解依据</h2><button type="button" autoFocus onClick={onClose}>关闭回看</button></div>
    <p>{task.title}</p><p className="plan-muted">只读查看关联版本当前已确认的拆解，未确认修改不显示。场次关联便于追溯，不代表模型安排已被原文证明。</p>
    {error && <div role="alert" className="error"><p>{error}</p><button type="button" onClick={() => setAttempt(x => x + 1)}>重试读取</button></div>}
    {!data && !error && <p role="status">正在读取拆解依据…</p>}
    {data && <><p>剧本 V{data.script.version_number} · {data.script.version_label || data.script.title}</p>
      <section><h3>第 {data.scene.scene_number || '未编号'} 场 · {data.scene.location || '场地未填写'}</h3>
        <p>{data.scene.interior_exterior || '内外未填写'} · {data.scene.atmosphere || '气氛未填写'}</p>
        <p>内容：{data.scene.summary || '未填写'}</p><p>人物：{names(data.scene.cast)}</p>
        <p>戏用道具：{names(data.scene.action_props)}</p><p>其他道具：{names(data.scene.other_props)}</p>
        {data.scene.makeup_costume?.length > 0 && <details><summary>查看各角色妆造</summary><pre>{JSON.stringify(data.scene.makeup_costume, null, 2)}</pre></details>}
        {data.scene.notes && <p>备注：{data.scene.notes}</p>}
      </section><EvidencePanel scene={data.scene} content={data.content} onClose={onClose}/>
    </>}
  </dialog>;
}
