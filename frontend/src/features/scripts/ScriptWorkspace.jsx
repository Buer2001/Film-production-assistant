import React, { useEffect, useState } from 'react';
import useScriptDraft from './useScriptDraft';
import { scriptApi } from './api';
import ScriptImport from './ScriptImport';
import BreakdownTable from './BreakdownTable';
import EvidencePanel from './EvidencePanel';
import ProgressPanel from './ProgressPanel';
import VersionChanges from './VersionChanges';
import CustomFields from './CustomFields';
import './scripts.css';

const blank = () => ({ id: crypto.randomUUID(), local_id: crypto.randomUUID(), scene_number: '', interior_exterior: '',
  atmosphere: '', location: '', summary: '', cast: [], makeup_costume: [],
  action_props: [], other_props: [], custom_values: {}, word_count: null, notes: '', previous_scene_id: null, match_status: 'first',
  parse_status: 'succeeded', resolution: 'manual', parse_error: '', change_reviewed: false, evidence: {}, extracted_data: {}, review_issues: [] });

export default function ScriptWorkspace({ pid, onLockChange }) {
  const [customFields, setCustomFields] = useState([]), [fieldsDirty, setFieldsDirty] = useState(false);
  const [fieldsBusy, setFieldsBusy] = useState(false), [draftLocked, setDraftLocked] = useState(false);
  useEffect(() => { onLockChange?.(draftLocked || fieldsDirty || fieldsBusy); }, [draftLocked, fieldsDirty, fieldsBusy, onLockChange]);
  const { versions, setVersions, doc, selected, setSelected, importing, setImporting, busy, error, setError, saveState, acceptMissing, setAcceptMissing, dirty, install, mutate, updateScene, backupDraft, reloadSaved, run, switchVersion, parse, retrySave, connection, reconnect, retryScene } = useScriptDraft(pid, setDraftLocked);
  const running = doc?.progress?.state === 'running' || doc?.status === 'parsing';
  const locked = busy || fieldsBusy || doc?.read_only;
  const unresolved = doc?.scenes.some(s => ['pending', 'running', 'failed'].includes(s.parse_status) && !['manual', 'excluded'].includes(s.resolution));
  const unsaved = dirty || fieldsDirty || saveState === '保存中';
  return <div className="script-workspace">
    <div className="script-toolbar">
      <label>剧本版本<select aria-label="剧本版本" disabled={busy || unsaved} value={doc?.id || ''}
        onChange={e => switchVersion(e.target.value)}>
        {!doc && <option value="">尚无剧本</option>}
        {versions.map(v => <option key={v.id} value={v.id}>V{v.version_number} {v.version_label || v.title}</option>)}
      </select></label>
      <span role="status">{saveState}{doc ? ` · 编辑版本 ${doc.revision}` : ''}</span>
      {doc && <span className="script-tag">{doc.read_only ? '历史版本 · 只读' : doc.status === 'confirmed' ? '已确认' : doc.status === 'parsing' ? '解析中' : '待核对'}</span>}
      <button disabled={busy || unsaved || (doc && doc.status !== 'confirmed')} title={doc && doc.status !== 'confirmed' ? '请先确认当前版本再导入新版' : ''} onClick={() => setImporting(!importing)}>导入新版</button>
      {doc && doc.status !== 'confirmed' && <small>请先确认当前版本，再导入新版。</small>}
      {doc && <a aria-disabled={unsaved || busy} onClick={e => { if (unsaved || busy) e.preventDefault(); }}
        href={scriptApi.exportUrl(pid, doc.id)}>导出 Excel{doc.status !== 'confirmed' ? '（未确认）' : ''}</a>}
    </div>
    {error && <div className="error" role="alert">{error}</div>}
    <CustomFields key={pid} pid={pid} disabled={busy || running || doc?.read_only || dirty || saveState === '保存中'}
      onChange={setCustomFields} onDirtyChange={setFieldsDirty} onBusyChange={setFieldsBusy}/>
    {saveState === '保存失败' && <div className="script-toolbar">
      <button onClick={retrySave}>重试保存</button>
      <button onClick={backupDraft}>下载本地草稿备份</button>
      <button onClick={reloadSaved}>重新加载已保存版本</button>
    </div>}
    {(importing || !doc) && <ScriptImport key={versions[0]?.id || 'first'} previous={versions[0]}
      busy={busy || unsaved} onImport={payload => run(async () => {
        const value = await scriptApi.create(pid, payload);
        install(value); setVersions(await scriptApi.list(pid)); setImporting(false); setSelected(null); setAcceptMissing(false);
        await parse(value);
      })}/>}
    {doc && <>
      <p className="script-hint">{doc.title} · {doc.version_label || `V${doc.version_number}`} · 原文保存后不覆盖；改原文请导入新版。</p>
      <p className="script-hint">未确认结果暂存草稿文件，确认本版拆解后才正式入库。</p>
      <ProgressPanel doc={doc} connection={connection} onReconnect={reconnect} disabled={busy || unsaved || doc.read_only}
        onStop={() => run(async () => install(await scriptApi.recover(pid, doc.id, doc.revision)))}/>
      {doc.review_issues.length > 0 && <div className="warning">{doc.review_issues.map((w, i) => <p key={i}>{w}</p>)}</div>}
      {(doc.can_start_parse || !doc.scenes.length) && <section>
        <p>{doc.parse_error || (doc.scenes.length ? '当前只有空白占位，还没有生成拆解结果。请从原文开始逐场拆解。' : '原文已保存，可以开始自动拆解，或增加场次手工填写。')}</p>
        {running ? <button disabled={busy || doc.read_only} onClick={() => run(async () => {
          install(await scriptApi.recover(pid, doc.id, doc.revision));
        })}>解析异常时中止并恢复</button> :
          <button disabled={locked || running} onClick={() => run(() => parse(doc))}>{doc.can_start_parse ? '从原文开始逐场拆解' : '开始 / 重试拆解'}</button>}
        {!doc.scenes.length && <button disabled={locked} onClick={() => mutate(d => ({ ...d, scenes: [{ ...blank(), match_status: d.previous_script_id ? 'pending' : 'first' }] }))}>手工填写</button>}
        <details><summary>查看已保存原文</summary><pre>{doc.content}</pre></details>
      </section>}
      {doc.scenes.length > 0 && <>
        <BreakdownTable scenes={doc.scenes} comparison={doc.comparison} disabled={locked} customFields={customFields}
          onRetry={retryScene} retryDisabled={busy || unsaved || running || doc.can_start_parse} structuralDisabled={running}
          selected={selected} onSelect={setSelected} onChange={updateScene}
          onAdd={() => mutate(d => ({ ...d, scenes: [...d.scenes, { ...blank(), match_status: d.previous_script_id ? 'pending' : 'first' }] }))}
          onDelete={index => {
            if (window.confirm('排除本场？草稿内容仍会保留，确认时本场不会入库，可随时撤销排除。')) updateScene(index, 'resolution', 'excluded');
          }}
          onMove={(index, delta) => mutate(d => { const scenes = [...d.scenes]; [scenes[index], scenes[index + delta]] = [scenes[index + delta], scenes[index]]; return { ...d, scenes }; })}/>
        <EvidencePanel scene={doc.scenes.find(s => (s.id || s.local_id) === selected)} content={doc.content} onClose={() => setSelected(null)}/>
        <VersionChanges doc={doc} disabled={locked} onChange={updateScene}
          onDeletedReview={value => mutate(d => ({ ...d, deleted_reviewed: value }))}/>
        {!doc.read_only && <section>
          <label className="inline-check"><input type="checkbox" checked={acceptMissing} onChange={e => setAcceptMissing(e.target.checked)}/>
            已核对并接受当前缺失信息和待补项</label>
          <button disabled={locked || unsaved || running || unresolved || doc.status === 'confirmed'} onClick={() => run(async () => {
            const kept = doc.scenes.filter(row => row.resolution !== 'excluded');
            const unmatched = kept.filter(row => row.match_status === 'pending').length;
            const unchecked = kept.filter(row => !row.change_reviewed).length;
            const oldUnlinked = (doc.comparison.unlinked || []).length;
            const acceptUnreviewed = Boolean(doc.previous_script_id && (unmatched || unchecked || oldUnlinked));
            if (acceptUnreviewed && !window.confirm(`本版有 ${unmatched} 场待匹配、${unchecked} 场未逐场核对、${oldUnlinked} 场旧场次未确认去向。\n这些状态会保留，不会自动认定新增或删除。仍然确认本版？`)) return;
            const result = await scriptApi.confirm(pid, doc.id, { revision: doc.revision,
              accept_missing: acceptMissing, accept_unreviewed: acceptUnreviewed });
            install(result); setVersions(await scriptApi.list(pid));
          })}>确认本版拆解</button>
          {unresolved && <small>请处理未完成或失败场次后再确认。</small>}
          {unsaved && <small>等待修改保存后再确认。</small>}
        </section>}
      </>}
    </>}
  </div>;
}
