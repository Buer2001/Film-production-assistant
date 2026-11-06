import test from 'node:test';
import assert from 'node:assert/strict';
import { navigation, sectionFor, editOperation, fieldLabel } from '../frontend/src/workspace.js';

test('六个主入口容纳旧业务页，影响分析不丢失入口归属', () => {
  assert.equal(navigation.length, 6);
  assert.equal(sectionFor('通告'), '拍摄管理');
  assert.equal(sectionFor('费用'), '项目记录');
  assert.equal(sectionFor('影响分析'), '制片助手');
});
test('草稿表单只修改指定字段，保留嵌套关联、操作身份和其他操作', () => {
  const original = [{op_id:'a', entity:'project_task', patch:{title:'场地', details:{person_ids:['p1']}}}, {op_id:'b', patch:{title:'拍摄'}}];
  const result = editOperation(original, 'a', 'planned_end', '2026-11-12');
  assert.equal(result[0].patch.planned_end, '2026-11-12');
  assert.deepEqual(result[0].patch.details, {person_ids:['p1']});
  assert.equal(original[0].patch.planned_end, undefined);
  assert.deepEqual(result[1], original[1]);
  assert.equal(editOperation(result, 'a', 'planned_end', '')[0].patch.planned_end, null);
});
test('主要业务字段用中文展示', () => {
  assert.equal(fieldLabel('start_at'), '开始时间');
  assert.equal(fieldLabel('person_ids'), '关联人员');
});
