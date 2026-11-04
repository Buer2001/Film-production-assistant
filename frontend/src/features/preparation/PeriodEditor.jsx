// 提供人员、资源和任务共用的日期时段及可用情况编辑控件。
import React from 'react';

// 人员和资源共用同一时间契约：无记录为未知，不能从任务截止日推算。
/**
 * 无参数；返回独立空时段，日期待填写，两端时刻为 null。
 */
export const emptyPeriod = () => ({ start_date: '', end_date: '', start_time: null, end_time: null });
/**
 * 参数 value 为可选时段；返回便于展示的范围文字，缺失时段显示未知，不推断可用性。
 */
export function periodText(value) {
  return value ? `${value.start_date} ${value.start_time || '全天'} 至 ${value.end_date} ${value.end_time || '全天'}` : '使用时间未知';
}

// 日期闭区间；两端时刻成对填写，均为空时表示整天。
/**
 * 参数：value 为时段，onChange 接收新时段；返回受控日期及时间表单 JSX。
 * 开始和结束时刻成对填写；空时刻表示全天，日期包含首尾两天。
 */
export function PeriodEditor({ value, onChange }) {
  const set = (key, next) => onChange({ ...value, [key]: next });
  return <div className="plan-grid">
    <label>开始日期
      <input required type="date" value={value.start_date} onChange={e => set('start_date', e.target.value)}/>
    </label>
    <label>结束日期
      <input required type="date" min={value.start_date || undefined} value={value.end_date} onChange={e => set('end_date', e.target.value)}/>
    </label>
    <label>开始时刻（可选）
      <input type="time" required={!!value.end_time} value={value.start_time || ''} onChange={e => set('start_time', e.target.value || null)}/>
    </label>
    <label>结束时刻（可选）
      <input type="time" required={!!value.start_time} min={value.start_date === value.end_date ? value.start_time || undefined : undefined} value={value.end_time || ''} onChange={e => set('end_time', e.target.value || null)}/>
    </label>
  </div>;
}

/**
 * 参数：value 为可用时段数组，onChange 接收新数组；返回添加、修改及移除时段的控件 JSX。
 * 空数组表示未知；新增项初始为可用，不代表其他日期同样可用。
 */
export function AvailabilityEditor({ value = [], onChange }) {
  return <div>
    <p className="plan-muted">无记录表示可用情况未知；不填时刻表示整天。</p>
    {value.map((period, i) => <div key={i}>
      <PeriodEditor value={period} onChange={next => onChange(value.map((x, n) => n === i ? next : x))}/>
      <label>可用情况
        <select value={period.state} onChange={e => onChange(value.map((x, n) => n === i ? { ...x, state: e.target.value } : x))}>
          <option value="available">可用</option>
          <option value="unavailable">不可用</option>
        </select>
      </label>
      <button type="button" onClick={() => onChange(value.filter((_, n) => n !== i))}>移除此时段</button>
    </div>)}
    <button type="button" onClick={() => onChange([...value, { ...emptyPeriod(), state: 'available' }])}>添加可用时段</button>
  </div>;
}
