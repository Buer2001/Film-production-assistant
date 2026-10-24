# codex 任务书 · 第 1 轮

你是本项目的实现工程师。项目是「学生制片工作台」：FastAPI + SQLAlchemy 后端、React 前端、SQLite 本地库。
先读 `README.md`、`backend/production/service.py`、`backend/production/scheduling/checks.py`、`tests/` 了解现有约定，再动手。

现有基线：`python -m pytest tests -q` 25 项通过，`python -m evaluations.run` 25/25 通过。这两条必须保持通过。

## 任务 1：通告「待检查」精确判定

现在 `backend/production/service.py` 的 `state()` 用 `n.revision != p.revision` 判断通告是否待检查：任何一次正式变更都会把全部旧通告标成待检查，实际常常无关。要改成按当天实际影响判定。

规则（按当前数据比较快照，不依赖事件日志）：

1. 通告快照里当天的拍摄安排（`kind == 'schedule'` 且 `data['date'] == notice.date`）：
   - 当前数据中缺失、或任一字段与快照不同 → 待检查，原因如「当天拍摄安排「X」已改动」。
   - 当前数据里新出现了当天拍摄安排 → 待检查，原因「当天新增拍摄安排「X」」。
2. 当天涉及场次（从快照里当天安排的 `scene_ids` 取并集）的筹备事项（`kind` 为 `task` 或 `requirement` 且 `scene_ids` 与当天场次有交集）：
   - 当前数据中缺失、标题/状态/日期/备注等字段变化、或新增 → 待检查，原因如「「X」状态由 待确认 变为 已确认」。
3. 其他与当天无关的变更（别的日期的排期、别的场次的筹备、费用等）→ 不待检查，通告保持有效。
4. 变更被撤回或数据恢复到与快照一致 → 重新变为有效（按当前数据比较自然得到，不要额外记录状态）。
5. 删除当天关联场次记录本身不算影响通告内容，但删除当天拍摄安排算（见规则 1）。

实现要求：

- 新逻辑放到 `backend/production/notices/status.py`，函数 `notice_status(notice, records)` 返回 `{'stale': bool, 'reasons': [str]}`，纯函数、可单测，不查数据库。
- `state()` 用它填充每个通告的 `stale` 和 `reasons`（保留 `stale` 字段名，前端兼容）。
- 前端 `frontend/src/main.jsx` 的通告列表显示待检查原因（最多 3 条，其余折叠为「等 N 项」）。样式沿用 `frontend/src/style.css` 现有类，不引新依赖。
- 新增 `tests/test_notice_status.py`，至少覆盖：无关变更仍有效；当天安排字段变化；当天筹备状态变化；新增当天安排；删除当天安排；数据恢复后重新有效。测试直接用 `TestClient` 走真实接口，风格与 `tests/test_workflow.py` 一致。

## 任务 2：并发竞争的真实测试

`docs/verification.md` 承认并发只在单线程顺序验证过。补真实多线程测试，`tests/test_concurrency.py`：

- 用临时文件 SQLite（`tmp_path`），线程池 8 个线程用各自独立 session 同时 `confirm` 同一草稿：结果必须只有一次写入记录、项目版本只加一，其余请求返回已确认结果或 409，都不能产生重复记录。
- `confirm` 与 `reject` 同时作用于同一草稿：最终状态只有一种，不能出现已确认又取消、或取消后仍写入记录。
- 两个不同草稿基于同一 `base_revision` 并发确认：只允许一个成功，另一个 409，且失败方不写入任何记录。
- 测试要稳定：同一命令连跑 3 次不抖动。若 SQLite 报 `database is locked`，在 `backend/common/database/store.py` 的 `database()` 里给 SQLite 加合理的 `timeout` / 连接参数，不改表结构、不加新依赖，并在回复里说明。
- 如果并发测试暴露真实缺陷（例如版本已加但记录未写、状态与数据不一致），修 `service.py` 的 `confirm`，修法要小而准，别重构。

## 边界与禁止

- 只改代码和测试，不写 README、`结论池.md`、`docs/*`（文档由我统一更新）。
- 不加依赖、不换框架、不改表结构、不做认证/权限、不引入迁移框架、不重写前端、不做资源 ID 化。
- 保持现有 5 个 Agent 工具与权限边界不变。
- 注释和面向用户的文案用中文；标题别用「什么与什么」式对仗。
- 别顺手格式化整个文件，别改无关代码。

## 自检并在最终回复里给出

```
python -m pytest tests -q
python -m evaluations.run
cd frontend; npm run build
```

最终回复要列：改了哪些文件、每个任务怎么实现的、测试与评估实际输出、遗留问题。
