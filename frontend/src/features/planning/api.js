// 集中定义日程接口、展示枚举和新任务默认结构。
import { api } from '../../api/client';
/**
 * 参数：pid 为项目 ID，path 为日程子路径，body 为可选请求数据，method 为可选方法。返回接口响应 Promise。
 */
export const planningApi = (pid, path = '', body, method) => api(`/projects/${pid}/planning${path}`, body, method ? { method } : {});
export const phases = { preparation: '筹备', shooting: '拍摄', closing: '收尾' };
export const categories = { script: '剧本方案', people: '人员到位', location: '场地', equipment: '器材', art: '服化道', logistics: '交通后勤', shooting: '拍摄组织', finance: '财务', other: '其他' };
export const statuses = { todo: '待办', in_progress: '进行中', completed: '已完成', cancelled: '已取消' };
/**
 * 创建独立的新任务对象；无参数，返回含完整 details 默认值的任务，避免多个表单共享可变数组。
 */
export const emptyTask = () => ({ title: '', description: '', phase: 'preparation', category: 'other', status: 'todo', planned_start: null, planned_end: null, completion_criteria: '', details: { person_ids: [], usage_period: null, result_notes: '', requires_people: false, department: '', collaborating_departments: [], assignees: [], dependencies: [], constraints: [], scene_refs: [], resource_refs: [], estimate_days: null, rationale: '', checklist_refs: [], origin: { type: 'manual', generation_id: null } } });

export const departments = ['制片组', '导演组', '摄影组', '灯光组', '录音组', '美术组', '服化组', '后勤组'];
