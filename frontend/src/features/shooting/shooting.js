// 拍摄页面的日期、显示和表单转换规则；本地时刻不经 UTC 转换，避免日期偏移。
export const kinds = { shoot: '场次拍摄', transfer: '转场', meal: '用餐', makeup: '妆造', lighting: '布光', set: '置景', other: '其他' };
export const logStatuses = { completed: '本次完成', partial: '部分完成', not_shot: '未拍摄' };
export const emptyDetails = { assembly: '', makeup: '', transport: '', meals: '', notes: '' };

export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// 以整日的左闭右开区间筛选；跨午夜安排在两天都可见，但不复制业务记录。
export function onDay(row, day) {
  return row.data.start_at.slice(0, 10) <= day && (row.data.end_at.slice(0, 10) > day ||
    (row.data.end_at.slice(0, 10) === day && row.data.end_at.slice(11, 19) > '00:00:00'));
}

export function sceneLabel(scene) {
  return scene ? `V${scene.script_version} · ${scene.scene_number || '未编号'}场 · ${scene.location || '地点待定'}` : '未关联场次';
}

export function timeLabel(value) { return value ? value.replace('T', ' ').slice(0, 16) : '未记录'; }

export function newItem(day, changes = {}) {
  return { title: '', kind: 'shoot', status: 'planned', start_at: `${day}T08:00`, end_at: `${day}T09:00`, scene_id: '',
    person_ids: [], resource_ids: [], location: '', shots: '', reshoot_log_id: '', notes: '', ...changes };
}

// 空镜头数表示未知；切换到非拍摄项时解除不适用的场次及补拍引用。
export function itemPayload(data) {
  return { ...data, scene_id: data.kind === 'shoot' ? data.scene_id || null : null,
    reshoot_log_id: data.kind === 'shoot' ? data.reshoot_log_id || null : null,
    shots: data.shots === '' || data.shots == null ? null : Number(data.shots) };
}

export function newLog(day, changes = {}) {
  return { scene_id: '', item_id: '', date: day, actual_start: '', actual_end: '', status: 'completed', remaining: '', reshoot_reason: '', notes: '', ...changes };
}

export function logPayload(data) {
  return { ...data, item_id: data.item_id || null, actual_start: data.actual_start || null, actual_end: data.actual_end || null };
}
