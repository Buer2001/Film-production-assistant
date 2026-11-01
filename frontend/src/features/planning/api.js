import { api } from '../../api/client';
export const planningApi = (pid, path = '', body, method) => api(`/projects/${pid}/planning${path}`, body, method ? { method } : {});
export const phases = { preparation: '筹备', shooting: '拍摄', closing: '收尾' };
export const categories = { script: '剧本方案', people: '人员到位', location: '场地', equipment: '器材', art: '服化道', logistics: '交通后勤', shooting: '拍摄组织', finance: '财务', other: '其他' };
export const statuses = { todo: '待办', in_progress: '进行中', completed: '已完成', cancelled: '已取消' };
export const emptyTask = () => ({ title: '', description: '', phase: 'preparation', category: 'other', status: 'todo', planned_start: null, planned_end: null, completion_criteria: '', details: { dependencies: [], constraints: [], scene_refs: [], resource_refs: [], estimate_days: null, rationale: '', checklist_refs: [], origin: { type: 'manual', generation_id: null } } });
