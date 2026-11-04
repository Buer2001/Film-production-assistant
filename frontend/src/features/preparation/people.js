// 为任务展示解析人员名称，不改写保存所用的人员 ID 或历史姓名。
// 保存仍使用原始 person_ids 和历史姓名；展示时才解析最新姓名。
/**
 * 参数：details 为任务详情，people 为最新人员列表。返回去重后的关联人员及手填姓名，缺失人员显示不可用提示。
 */
export function personNames(details = {}, people = []) {
  return [...new Set([...(details.person_ids || []).map(id => people.find(person => person.id === id)?.name || '人员资料不可用'), ...(details.assignees || [])])];
}
