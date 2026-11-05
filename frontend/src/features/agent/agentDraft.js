// 集中处理助手草稿的分组、差异和检查分级，供界面和纯逻辑测试复用。

export const entityLabels = { project_task: '项目任务', shooting_item: '拍摄安排' };
export const actionLabels = { add: '新增', update: '修改', cancel: '取消' };
export const levelLabels = { block: '必须处理', conflict: '需要修改', gap: '可以保留' };
export const statusLabels = {
  running: '处理中', waiting_input: '等待补充', waiting_review: '待审阅',
  completed: '已完成', abandoned: '已放弃',
};

/**
 * 参数：operations 为草稿操作列表。返回：按对象类型分组的操作，保持后端顺序。
 * 未知类型归入项目任务，避免界面丢项。
 */
export function groupOperations(operations = []) {
  const groups = { project_task: [], shooting_item: [] };
  operations.forEach(op => (groups[op.entity] || groups.project_task).push(op));
  return groups;
}

/**
 * 参数：op 为一条草稿操作。返回：实际变化的字段及前后值。
 * 新增项没有原值，只显示新值；前后相等的字段不列出。
 */
export function changedFields(op) {
  const patch = op.patch || {};
  const before = op.before || {};
  return Object.keys(patch)
    .map(key => ({ key, before: before[key], after: patch[key] }))
    .filter(item => JSON.stringify(item.before) !== JSON.stringify(item.after));
}

/**
 * 参数：op 为一条草稿操作。返回：用于列表展示的标题。
 * 依次取新标题、原标题、正式 ID、临时编号，保证每行都有可识别名称。
 */
export function operationTitle(op) {
  const patch = op.patch || {};
  const before = op.before || {};
  return patch.title || before.title || op.target_id || op.temp_id || op.op_id;
}

/**
 * 参数：validation 为程序检查结果。返回：按阻断、冲突、缺口分组的检查项。
 * 缺少级别的项按缺口处理，未知信息不能当作通过。
 */
export function groupIssues(validation) {
  const issues = (validation && validation.issues) || [];
  const groups = { block: [], conflict: [], gap: [] };
  issues.forEach(issue => (groups[issue.level] || groups.gap).push(issue));
  return groups;
}

/**
 * 参数：uncovered 为未安排场次列表。返回：一行可读文字，用于确认前提示。
 */
export function uncoveredText(uncovered = []) {
  return uncovered
    .map(scene => `场次 ${scene.scene_number}${scene.location ? `（${scene.location}）` : ''}`)
    .join('、');
}
