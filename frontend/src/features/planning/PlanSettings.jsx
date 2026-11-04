// 编辑项目拍摄日期和现状，保存动作交由父工作区处理。
import React from 'react';

/**
 * 参数：value 为设置，onChange 接收完整新设置，onSave 提交，busy/dirty 控制可编辑状态和保存入口。
 * 返回受控表单 JSX；未知日期保持 null，不自行推算。
 */
export default function PlanSettings({ value, onChange, onSave, busy, dirty }) {
  const field = (key, v) => onChange({ ...value, [key]: v });
  return <section><h2>项目安排</h2><p>从现在的筹备到拍摄结束，再到器材道具归还和费用结清。杀青、收尾日期未知时可留空，模型会提出待确认问题。</p>
    <form onSubmit={e => { e.preventDefault(); onSave(); }}><fieldset disabled={busy}>
      <div className="plan-grid"><label>开拍日期<input type="date" required value={value.shoot_start || ''} onChange={e => field('shoot_start', e.target.value || null)}/></label>
      <label>预计杀青日期<input type="date" min={value.shoot_start || undefined} value={value.shoot_end || ''} onChange={e => field('shoot_end', e.target.value || null)}/></label>
      <label>预计收尾日期<input type="date" min={value.shoot_end || value.shoot_start || undefined} value={value.close_date || ''} onChange={e => field('close_date', e.target.value || null)}/></label></div>
      <label>项目现状<textarea maxLength={12000} rows={4} value={value.context || ''} placeholder="已落实什么、还有哪些问题？例如异地拍摄、演员档期、场地申请、租借器材、预算限制。不要在这里填写账号或证件。" onChange={e => field('context', e.target.value)}/></label>
      <button disabled={!dirty}>保存项目安排</button>{dirty && <span className="plan-muted"> 有未保存修改，请先保存再生成</span>}
    </fieldset></form>
  </section>;
}
