// ID用于保持关联；名称只是显示快照，资源改名不能把关联退化成纯文本。
export function resourceRefs(ids, text, options, previous = []) {
  const linked = ids.map(id => {
    const option = options.find(r => r.id === id);
    const old = previous.find(r => r.record_id === id);
    return option ? { record_id: id, name: option.data.title, type: ['equipment', 'prop', 'location', 'costume'].includes(option.data.category) ? option.data.category : old?.type || 'other' } : old;
  }).filter(Boolean);
  const names = [...new Set(text.split('\n').map(x => x.trim()).filter(Boolean))];
  return [...linked, ...names.map(name => previous.find(r => !r.record_id && r.name === name) || { record_id: null, name, type: 'other' })];
}
