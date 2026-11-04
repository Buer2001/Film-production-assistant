// 维护项目人员资料及可用时段，使用共享项目版本防止并发覆盖。
import React, { useState } from 'react';
import { api } from '../../api/client';
import { AvailabilityEditor, periodText } from './PeriodEditor';

const emptyPerson = () => ({ name: '', department: '', roles: [], phone: '', contact: '', availability: [], notes: '' });
/** 参数 person 为可选人员资料；返回独立编辑副本及岗位输入文本，不修改原始资料。 */
export const createPersonDraft = (person = emptyPerson()) => ({ ...structuredClone(person), rolesText: (person.roles || []).join('、') });
// 人员独立保存并共享项目 revision；编辑草稿由父页面持有，写入失败不清空输入。
/**
 * 参数：pid/people/revision 提供项目、人员和版本；disabled 禁用操作，editing/onEditing 由父层持有草稿。
 * onBusy 通知请求状态，onChanged 在写入成功后刷新资料；返回人员列表及编辑表单 JSX。
 * editorOnly 为 true 时仅呈现编辑表单，用于周档期侧栏，保存和版本校验逻辑与原列表共用。
 */
export default function PeoplePanel({ pid, people, revision, disabled, editing, onEditing, onBusy, onChanged, editorOnly = false }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  /**
   * 参数：path 为人员子路径，person 为可选人员内容，method 为请求方法。
   * 写入成功后清空父层草稿并刷新；写入请求失败时保留输入，写入或刷新失败均显示错误，最终释放本地及父层忙碌状态。
   */
  async function mutate(path, person, method) {
    setBusy(true); onBusy(true); setError('');
    try {
      await api(`/projects/${pid}/people${path}`, person === undefined ? undefined : { revision, person }, { method });
      onEditing(null);
      await onChanged();
    }
    catch (e) { setError(e.message); }
    finally { setBusy(false); onBusy(false); }
  }
  // 岗位先保留输入文本，提交时才拆分，避免键入末尾分隔符时被吞掉。
  const startEditing = person => onEditing(createPersonDraft(person));
  const field = (key, value) => onEditing({ ...editing, [key]: value });
  // 档期侧栏只呈现同一份表单；保存和版本校验仍走原接口，避免另写一套编辑逻辑。
  const content = <>
      {error && <p role="alert" className="error">{error}</p>}
      {!editorOnly && <><button disabled={disabled || busy || !!editing} onClick={() => startEditing(emptyPerson())}>新增人员</button>
      {people.map(person => <article className="record" id={`person-${person.id}`} key={person.id}>
        <div>
          <h3>{person.name}</h3>
          <p>{person.department || '部门待填'} · {(person.roles || []).join('、')} · {person.phone || person.contact || '联系方式待填'}</p>
          <p>{person.availability?.map(x => `${x.state === 'available' ? '可用' : '不可用'}：${periodText(x)}`).join('；') || '可用情况未知'}</p>
          <p>{person.notes}</p>
        </div>
        <div>
          <button disabled={disabled || busy || !!editing} onClick={() => startEditing(structuredClone(person))}>编辑人员</button>
          <button disabled={disabled || busy || !!editing} onClick={() => { if (window.confirm(`删除人员“${person.name}”？已被引用的人员不能删除。`)) mutate(`/${person.id}?revision=${revision}`, undefined, 'DELETE'); }}>删除人员</button>
        </div>
      </article>)}</>}
      {editing && <form onSubmit={e => { e.preventDefault();
        const { id, project_id, rolesText, ...person } = editing;
        person.roles = [...new Set(rolesText.split(/[、,，]/).map(x => x.trim()).filter(Boolean))];
        mutate(id ? `/${id}` : '', person, id ? 'PUT' : 'POST'); }}>
        <fieldset disabled={busy}>
          <label>姓名
            <input required maxLength={200} value={editing.name} onChange={e => field('name', e.target.value)}/>
          </label>
          <label>部门
            <input value={editing.department} onChange={e => field('department', e.target.value)}/>
          </label>
          <label>岗位（顿号分隔）
            <input value={editing.rolesText} onChange={e => field('rolesText', e.target.value)}/>
          </label>
          <label>电话
            <input value={editing.phone} onChange={e => field('phone', e.target.value)}/>
          </label>
          <label>其他联系方式
            <input value={editing.contact} onChange={e => field('contact', e.target.value)}/>
          </label>
          <AvailabilityEditor value={editing.availability} onChange={v => field('availability', v)}/>
          <label>备注
            <textarea value={editing.notes} onChange={e => field('notes', e.target.value)}/>
          </label>
          <button>保存人员</button>
          <button type="button" onClick={() => onEditing(null)}>取消编辑</button>
        </fieldset>
      </form>}
  </>;
  return editorOnly ? <div className="availability-editor">{content}</div> : <section>
    <details id="project-people"><summary>项目人员 · {people.length}</summary>{content}</details>
  </section>;
}
