// 以独立任务副本编辑安排、人员、依赖、约束和资源引用。
import React, { useId, useState } from 'react';
import ReferencePicker from './ReferencePicker';
import { PeriodEditor, emptyPeriod } from '../preparation/PeriodEditor';
import { resourceRefs } from './resourceRefs';
import { categories, phases, statuses, emptyTask, departments } from './api';

/**
 * 参数：initial 为初始任务，tasks/scenes/resources/people 为关联候选，peopleUnavailable 控制新增人员关联。
 * busy 控制提交，onSave 接收完整任务，onCancel 取消；draft/isNew 限制新增草稿任务状态。返回任务表单 JSX。
 * 姓名和部门文本在提交时拆分去重；资源通过 ID 保持关联，未保存的修改不写回 initial。
 */
export default function TaskEditor({ initial, tasks, scenes, resources = [], people = [], peopleUnavailable = false, busy, onSave, onCancel, draft = false, isNew = false }) {
  const [value, setValue] = useState(() => structuredClone(initial || emptyTask()));
  const detail = value.details || emptyTask().details;
  const [resourceText, setResourceText] = useState(() => (detail.resource_refs || []).filter(r => !r.record_id).map(r => r.name).join('\n'));
  const [resourceIds, setResourceIds] = useState(() => (detail.resource_refs || []).filter(r => r.record_id).map(r => r.record_id));
  const resourceOptions = [...resources, ...(detail.resource_refs || []).filter(r => r.record_id && !resources.some(x => x.id === r.record_id)).map(r => ({ id: r.record_id, data: { title: r.name + '（资源不可用，请核对）' } }))];
  const field = (key, v) => setValue(x => ({ ...x, [key]: v }));
  const details = (key, v) => field('details', { ...detail, [key]: v });
  const selected = e => [...e.target.selectedOptions].map(o => o.value);
  const departmentList = useId();
  const [assigneeText, setAssigneeText] = useState(() => (detail.assignees || []).join('、'));
  const [collaboratorText, setCollaboratorText] = useState(() => (detail.collaborating_departments || []).join('、'));
  const names = text => [...new Set(text.split(/[、,，;；\n]+/).map(x => x.trim()).filter(Boolean))];
  const constraints = detail.constraints || [];
  const updateConstraint = (i, patch) => details('constraints', constraints.map((c, n) => n === i ? { ...c, ...patch } : c));
  return <div className="plan-editor"><h3>{initial?.id ? '编辑任务安排' : '任务安排'}</h3><form onSubmit={e => { e.preventDefault(); onSave({ ...value, details: { ...detail, assignees: names(assigneeText), collaborating_departments: names(collaboratorText), resource_refs: resourceRefs(resourceIds, resourceText, resources, detail.resource_refs || []) } }); }}><fieldset disabled={busy}>
    <label>任务名称<input autoFocus required maxLength={200} value={value.title} onChange={e => field('title', e.target.value)}/></label>
    <div className="plan-grid"><label>主责部门<input list={departmentList} maxLength={50} value={detail.department || ''} placeholder="待分配，可自定义" onChange={e => details('department', e.target.value)}/><datalist id={departmentList}>{departments.map(name => <option value={name} key={name}/>)}</datalist></label>
    </div>
    <div className="plan-grid"><label>阶段<select value={value.phase} onChange={e => field('phase', e.target.value)}>{Object.entries(phases).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label>类别<select value={value.category} onChange={e => field('category', e.target.value)}>{Object.entries(categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
    <label>状态<select value={value.status} onChange={e => field('status', e.target.value)}>{Object.entries(statuses).filter(([k]) => !draft || !isNew || k === 'todo').map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div>
    <div className="plan-grid"><label>计划开始<input type="date" value={value.planned_start || ''} onChange={e => field('planned_start', e.target.value || null)}/></label>
    <label>计划完成<input type="date" min={value.planned_start || undefined} value={value.planned_end || ''} onChange={e => field('planned_end', e.target.value || null)}/></label>
</div>
    <label>需要落实人员<input type="checkbox" checked={!!detail.requires_people} onChange={e => details('requires_people', e.target.checked)}/></label>
    <ReferencePicker label="关联人员" disabled={peopleUnavailable} value={detail.person_ids || []} options={people.map(p => ({ id: p.id, label: `${p.name} · ${p.department || '部门待填'}` }))} onChange={v => details('person_ids', v)}/>
    <ReferencePicker label="关联资源" value={resourceIds} options={resourceOptions.map(r => ({ id: r.id, label: r.data.title }))} onChange={setResourceIds}/>
    <p className="plan-muted">任务期限是何时办完；计划使用时段是何时用到人员、资源。关联后会显示在对应档期表。</p>
    {peopleUnavailable && <p className="error" role="alert">人员资料尚不可用，暂时禁止更改人员关联；已有引用保留。</p>}
    <p className="plan-muted">关联人员会展示最新姓名；手填姓名保留在“更多设置”中。</p>
    <label>记录计划使用时段<input type="checkbox" checked={!!detail.usage_period} onChange={e => details('usage_period', e.target.checked ? emptyPeriod() : null)}/></label>
    {detail.usage_period && <PeriodEditor value={detail.usage_period} onChange={v => details('usage_period', v)}/>}
    <label>落实结果说明<textarea maxLength={2000} value={detail.result_notes || ''} onChange={e => details('result_notes', e.target.value)}/></label>
    <label>工作说明<textarea maxLength={5000} value={value.description} onChange={e => field('description', e.target.value)}/></label>

    <details><summary>更多设置：依赖、剧本依据、日期限制</summary>
    <label>协作部门<input maxLength={400} value={collaboratorText} placeholder="多个部门用顿号分隔" onChange={e => setCollaboratorText(e.target.value)}/></label>
    <label>手填实施人员（未关联资料）<input maxLength={1000} value={assigneeText} placeholder="待分配，多个姓名用顿号分隔" onChange={e => setAssigneeText(e.target.value)}/></label>
    <label>预计所需自然日<input type="number" min={1} max={365} value={detail.estimate_days ?? ''} onChange={e => details('estimate_days', e.target.value ? Number(e.target.value) : null)}/></label>
    <label>完成标准<textarea maxLength={2000} value={value.completion_criteria} onChange={e => field('completion_criteria', e.target.value)}/></label>
      <p className="plan-muted">多选框可使用 Ctrl / Command 选择多项。</p>
      <label>前置任务<select multiple size={Math.min(5, Math.max(2, tasks.length))} value={(detail.dependencies || []).map(d => d.task_id)} onChange={e => details('dependencies', selected(e).map(task_id => ({ task_id, relation: 'finish_to_start' })))}>{tasks.filter(t => t.id !== initial?.id && t.status !== 'cancelled').map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
      <label>关联场次<select multiple size={4} value={(detail.scene_refs || []).map(s => `${s.script_id}:${s.scene_id}`)} onChange={e => { const keys = selected(e); details('scene_refs', scenes.filter(s => keys.includes(`${s.script_id}:${s.scene_id}`))); }}>{scenes.map(s => <option key={`${s.script_id}:${s.scene_id}`} value={`${s.script_id}:${s.scene_id}`}>{s.scene_number} · {s.location}</option>)}</select></label>
      <p className="plan-muted">选定具体资源后，请移除已落实的需求名称；不会按相似名称自动合并。</p>
      <label>未落实资源需求（每行一个名称）<textarea value={resourceText} onChange={e => setResourceText(e.target.value)}/></label>
      <label>安排理由<textarea maxLength={2000} value={detail.rationale || ''} onChange={e => details('rationale', e.target.value)}/></label>
      <h4>外部期限和节点要求</h4>{constraints.map((c, i) => <div className="plan-constraint" key={i}>
        <label>约束类型<select value={c.kind} onChange={e => updateConstraint(i, { kind: e.target.value, date: e.target.value === 'relative_to_milestone' ? null : c.date, milestone: e.target.value === 'relative_to_milestone' ? 'shoot_start' : null })}><option value="finish_by">最迟完成</option><option value="start_on_or_after">最早开始</option><option value="relative_to_milestone">相对项目节点完成</option></select></label>
        {c.kind === 'relative_to_milestone' ? <div className="plan-grid"><label>项目节点<select value={c.milestone || 'shoot_start'} onChange={e => updateConstraint(i, { milestone: e.target.value })}><option value="shoot_start">开拍</option><option value="shoot_end">杀青</option><option value="close_date">收尾</option></select></label><label>日偏移（提前为负数）<input type="number" min={-365} max={365} value={c.offset_days || 0} onChange={e => updateConstraint(i, { offset_days: Number(e.target.value) })}/></label></div> : <label>约束日期<input type="date" required value={c.date || ''} onChange={e => updateConstraint(i, { date: e.target.value || null })}/></label>}
        <div className="plan-grid"><label>强度<select value={c.strength} onChange={e => updateConstraint(i, { strength: e.target.value })}><option value="soft">软要求</option><option value="hard">硬限制</option></select></label><label>确认情况<select value={c.confirmation} onChange={e => updateConstraint(i, { confirmation: e.target.value })}><option value="pending">待确认</option><option value="confirmed">制片已确认</option></select></label></div>
        <label>来源说明<input required={c.confirmation === 'confirmed'} maxLength={1000} value={c.source || ''} onChange={e => updateConstraint(i, { source: e.target.value })}/></label><button type="button" onClick={() => details('constraints', constraints.filter((_, n) => n !== i))}>移除约束</button>
      </div>)}<button type="button" onClick={() => details('constraints', [...constraints, { kind: 'finish_by', date: null, milestone: null, offset_days: 0, strength: 'soft', confirmation: 'pending', source: '' }])}>添加时间约束</button>
    </details>
    <div className="plan-actions"><button>保存{draft ? '到待审草稿' : '任务'}</button><button type="button" onClick={onCancel}>取消编辑</button></div>
  </fieldset></form></div>;
}
