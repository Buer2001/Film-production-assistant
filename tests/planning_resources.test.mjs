// 测试职责：验证资源选择转换时保持稳定ID、名称去重及失效历史引用，不访问服务端。
// 执行方式：在项目目录运行 node --test tests/planning_resources.test.mjs。
import test from 'node:test';
import assert from 'node:assert/strict';
import { resourceRefs } from '../frontend/src/features/planning/resourceRefs.js';

// 已关联资源按ID保留，同名不同ID不能合并；手填资源名称单独去重。
test('资源改名保留ID，未关联名称去重，同名资源不会误合并', () => {
  const previous = [{ record_id: 'a', name: '旧名', type: 'location' }];
  const result = resourceRefs(['a', 'b'], '教室\n教室\n待找器材', [
    { id: 'a', data: { title: '教室', category: 'location' } },
    { id: 'b', data: { title: '教室', category: 'location' } },
  ], previous);
  assert.deepEqual(result.map(r => r.record_id), ['a', 'b', null, null]);
  assert.equal(result[0].name, '教室');
});

// 当前资源列表暂缺某个ID时，保留原引用供用户核对，不自动删除历史关联。
test('暂时缺失的历史资源引用不在编辑时静默丢弃', () => {
  const ref = { record_id: 'old', name: '历史器材', type: 'equipment' };
  assert.deepEqual(resourceRefs(['old'], '', [], [ref]), [ref]);
});
