// 集中定义制片记录类型、导航项、页面可见类型及通用记录默认值。
export const kinds = { scene: '场次', requirement: '导演要求', task: '筹备事项', resource: '资源', schedule: '拍摄安排', expense: '费用', decision: '决策' };
export const tabs = ['项目概览', '剧本', '项目日程', '拍摄安排', '费用', '通告', '影响分析', '变更记录', '制片助手'];
export const visible = { 拍摄安排: ['schedule'], 费用: ['expense'] };
export const empty = { title: '', category: '', status: '待确认', owner: '', scene_ids: [], resources: [], date: null, start: null, minutes: 60, amount: '0', source: '', notes: '' };

