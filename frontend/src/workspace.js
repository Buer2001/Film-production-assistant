// 主导航只管理页面归属，不改变旧接口及业务记录类型。
export const navigation = [
  {label:'项目概览', tab:'项目概览'}, {label:'剧本拆解', tab:'剧本'},
  {label:'筹备日程', tab:'项目日程'}, {label:'拍摄管理', tab:'拍摄安排'},
  {label:'制片助手', tab:'制片助手'}, {label:'项目记录', tab:'费用'},
];
export function sectionFor(tab) {
  if (['拍摄安排','通告'].includes(tab)) return '拍摄管理';
  if (['费用','变更记录'].includes(tab)) return '项目记录';
  if (tab === '影响分析') return '制片助手';
  return navigation.find(item => item.tab === tab)?.label || '项目概览';
}
const labels = {title:'名称',description:'说明',phase:'阶段',category:'类别',status:'状态',
  planned_start:'开始日期',planned_end:'截止日期',start_at:'开始时间',end_at:'结束时间',
  location:'地点',notes:'备注',reason:'调整依据',details:'任务关联及要求',scene_id:'关联场次',
  person_ids:'关联人员',resource_ids:'关联资源',kind:'安排类型',shots:'镜头数',
  completion_criteria:'完成标准',reshoot_log_id:'补拍来源',department:'主责部门',collaborating_departments:'协作部门',assignees:'实施人员',usage_period:'计划使用时段',resource_refs:'资源关联',scene_refs:'场次关联',requires_people:'需要人员落实',result_notes:'落实结果',dependencies:'前置任务',constraints:'约束',start_date:'开始日期',end_date:'结束日期',start_time:'开始时刻',end_time:'结束时刻',script_id:'剧本版本',record_id:'资源',name:'名称',type:'类型',scene_number:'场号',task_id:'前置任务',confirmation:'确认状态'};
export function fieldLabel(key) { return labels[key] || '其他信息'; }
// 表单编辑只写入显式修改的字段，其他关联和人工内容保持原样。
export function editOperation(operations, id, field, value) {
  return operations.map(op => op.op_id !== id ? op : {...op, patch:{...op.patch,
    [field]: value === '' && ['planned_start','planned_end'].includes(field) ? null : value}});
}
