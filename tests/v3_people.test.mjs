// 测试职责：验证人员名称显示由稳定ID关联，兼容历史手填姓名并明确提示失效引用。
// 执行方式：在项目目录运行 node --test tests/v3_people.test.mjs；不启动浏览器或数据库。
import test from 'node:test';
import assert from 'node:assert/strict';
import { personNames } from '../frontend/src/features/preparation/people.js';

test('人员改名后按 ID 展示最新姓名，同时保留历史手填姓名', () => {
  const details = { person_ids: ['p1'], assignees: ['历史姓名'] };
  assert.deepEqual(personNames(details, [{ id: 'p1', name: '新姓名' }]), ['新姓名', '历史姓名']);
  assert.deepEqual(details, { person_ids: ['p1'], assignees: ['历史姓名'] });
});
test('关联和手填同名只显示一次，失效引用仍明确提示', () => {
  assert.deepEqual(personNames({ person_ids: ['p1', 'missing'], assignees: ['小王'] }, [{ id: 'p1', name: '小王' }]), ['小王', '人员资料不可用']);
  assert.deepEqual(personNames(), []);
});
