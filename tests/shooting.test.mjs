// 验证本地日期、跨午夜展示和表单转换，避免 UTC 日期偏移或未知估时变为零。
import test from 'node:test';
import assert from 'node:assert/strict';
import { onDay, itemPayload, sceneLabel } from '../frontend/src/features/shooting/shooting.js';

test('跨午夜安排按日期交集显示，零点结束不占次日', () => {
  const row = { data: { start_at: '2026-11-05T23:00:00', end_at: '2026-11-06T01:00:00' } };
  assert.equal(onDay(row, '2026-11-05'), true);
  assert.equal(onDay(row, '2026-11-06'), true);
  assert.equal(onDay(row, '2026-11-07'), false);
  row.data.end_at = '2026-11-06T00:00:00';
  assert.equal(onDay(row, '2026-11-06'), false);
});

test('非拍摄项清除场次和补拍引用，空镜头数保留未知', () => {
  const payload = itemPayload({ kind: 'meal', shots: '', scene_id: 's', reshoot_log_id: 'l' });
  assert.equal(payload.scene_id, null);
  assert.equal(payload.reshoot_log_id, null);
  assert.equal(payload.shots, null);
  assert.match(sceneLabel({ script_version: 2, scene_number: '3', location: '教室' }), /V2/);
});
