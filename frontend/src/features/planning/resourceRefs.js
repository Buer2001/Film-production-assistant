// 把已选资源 ID 和手填名称合成为任务资源引用，保留历史关联快照。
// ID用于保持关联；名称只是显示快照，资源改名不能把关联退化成纯文本。
/**
 * 参数：ids 为已选 ID，text 为逐行名称，options 为最新资源，previous 为既有引用。
 * 返回资源引用数组；优先更新已关联资源名称和类型，失效 ID 保留旧引用，手填名称去空白并去重。
 */
export function resourceRefs(ids, text, options, previous = []) {
  const linked = ids.map(id => {
    const option = options.find(r => r.id === id);
    const old = previous.find(r => r.record_id === id);
    return option ? { record_id: id, name: option.data.title, type: ['equipment', 'prop', 'location', 'costume'].includes(option.data.category) ? option.data.category : old?.type || 'other' } : old;
  }).filter(Boolean);
  const names = [...new Set(text.split('\n').map(x => x.trim()).filter(Boolean))];
  return [...linked, ...names.map(name => previous.find(r => !r.record_id && r.name === name) || { record_id: null, name, type: 'other' })];
}
