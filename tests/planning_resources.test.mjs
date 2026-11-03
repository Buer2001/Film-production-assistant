import test from 'node:test';
import assert from 'node:assert/strict';
import { resourceRefs } from '../frontend/src/features/planning/resourceRefs.js';

test('资源改名保留ID，未关联名称去重，同名资源不会误合并', () => {
  const previous = [{ record_id: 'a', name: '旧名', type: 'location' }];
  const result = resourceRefs(['a', 'b'], '教室\n教室\n待找器材', [
    { id: 'a', data: { title: '教室', category: 'location' } },
    { id: 'b', data: { title: '教室', category: 'location' } },
  ], previous);
  assert.deepEqual(result.map(r => r.record_id), ['a', 'b', null, null]);
  assert.equal(result[0].name, '教室');
});

test('暂时缺失的历史资源引用不在编辑时静默丢弃', () => {
  const ref = { record_id: 'old', name: '历史器材', type: 'equipment' };
  assert.deepEqual(resourceRefs(['old'], '', [], [ref]), [ref]);
});
