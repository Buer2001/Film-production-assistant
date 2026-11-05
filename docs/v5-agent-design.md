# V5 Agent 设计与实现状态

日期：2026-11-04
状态：P1（联合草稿与统一事务闭环）已实现并通过自检；模型工作流 P2 及以后未实现。
本文替代此前以 LangGraph 和 checkpointer 为基础的方案，被替代的表述已删除。

## 1. 范围

一个 Agent，两条工作流，一套联合草稿：

| 工作流 | 用途 | 起点 |
|---|---|---|
| 协助编排 | 按项目节点、已确认剧本、准备情况和制片要求提出任务及拍摄安排 | 制片发起 |
| 条件变化后重排 | 按已确认变化分析影响并调整现有安排 | 制片发起 |

**可写对象**：项目日程任务（筹备、拍摄期间跟进、收尾）和拍摄大计划（场次拍摄、转场、用餐等）。两类修改进入同一份草稿，确认后统一事务执行，数据仍归原业务表。

**只读对象**：开拍/杀青/收尾等项目节点、人员档案与档期、资源落实资料、拍摄日志、已发布通告、剧本。模型和草稿都不能修改这些字段，越界直接拒绝。

范围只支持「阶段 + 日期区间」，单次不超过 120 天；候选最多 100 项操作。

## 2. 运行方式

固定步骤的持久化状态机，一个执行器，不引入 LangGraph，也不建设通用工作流引擎。

- 步骤是普通函数，接收状态和依赖，返回下一步与状态更新；节点不直接执行 SQL，也不提交业务事务。
- 允许的转换集中声明在 `backend/agent/state_machine.py`，不在此表中的跳转直接报错，模型无法指定节点。
- 每步结束后用版本条件更新保存运行状态并提交，进程重启后从数据库继续。
- 需要模型调用时先提交读事务再等待响应，等待期间不持有业务事务和项目锁；步骤返回后重新加载运行记录再推进。
- 状态结构见 `backend/agent/state.py`；运行、草稿、执行凭据分别在 `agent_runs`、`agent_drafts`、`agent_executions`。

## 3. 步骤与状态转换

`status`：`running`、`waiting_input`、`waiting_review`、`completed`、`abandoned`。
`current_step`：`understand`、`load`、`impact`、`propose`、`validate`、`save_draft`、`review`、`preflight`、`apply`、`report`、`feedback`。

| 当前 | 下一步 | 守卫 |
|---|---|---|
| understand | load | 有开拍日期、有候选、涉及场次时已有确认剧本 |
| understand | clarify | 缺开拍日期、缺候选、需要剧本却未确认 |
| clarify | understand | 制片补充后重新检查门槛 |
| load | propose / impact | 首次编排走 propose，重排先算影响 |
| impact | propose | 关系来自程序查询，不来自模型 |
| propose | validate | 候选结构合法 |
| validate | reflect | 无阻断项 |
| validate | clarify | 存在阻断项 |
| reflect | save_draft | 复核通过，或候选由制片直接提交 |
| reflect | revise | 发现可自行修正的问题且在预算内 |
| revise | validate | 修正后重新跑程序检查和复核 |
| save_draft | review | 草稿入库，进入待审阅 |
| review | preflight → apply → report → feedback | 制片确认后按顺序执行 |
| review | feedback | 制片放弃 |

`clarify` 和 `review` 是等待状态，不是步骤：写入状态后结束请求，恢复时带 `expected_version`。

## 4. 检查与分级

程序检查在候选合并后的整体视图上运行，同时覆盖未修改的正式数据：

- 任务：复用 `tools/planning.check_tasks`（依赖、环、日期、约束）与 `service/planning.apply_result`（字段净化、模型保护）。
- 拍摄：复用 `tools/shooting.check_shooting`（人员资源重叠、未知、失效引用、落实状态、准备缺口）。
- 范围：首次编排计算未排场次；重排模式只提示影响范围外的改动。

三档级别由 `tools/agent_checks.py` 统一判定：

- **阻断**：数据无效、越权字段、引用不存在。修正前不能提交。
- **冲突**：档期或固定约束冲突，需要先改方案。
- **缺口**：未知可用时间、准备未完成、未排场次。允许知情保留。

未知信息一律记为缺口，不当作通过；模型复核不得降低程序检查级别。

**漏排处理**：未排场次单独成类（`scope_uncovered`），确认时必须带 `accept_uncovered=true`，否则拒绝执行并列出场号。

**通告复核**：执行时按受影响日期比较已发布通告的来源指纹，变化的列入结果提示复核，不自动重发、不改写历史快照。

**模型复核**：只对模型生成的候选执行，制片自己提交的候选跳过。复核检查是否满足要求、是否遗漏范围目标、是否改动无关内容、是否虚构资料、取舍是否解释清楚。每 run 最多两次复核、两轮修正、六次模型调用；修正后重新跑程序检查并再次复核，达到上限转人工决定。模型不能降低程序检查级别。

## 5. 草稿契约

```json
{
  "schema_version": 1,
  "operations": [
    {"op_id": "op-1", "entity": "project_task", "action": "add", "temp_id": "t1",
     "patch": {"title": "确认场地", "phase": "preparation"}, "reason": "准备"},
    {"op_id": "op-2", "entity": "shooting_item", "action": "update", "target_id": "<id>",
     "patch": {"start_at": "2026-11-10T09:00"}, "reason": "改期"}
  ]
}
```

- `entity` 只有 `project_task` 和 `shooting_item`；`action` 只有 `add`、`update`、`cancel`。
- 新增用 `temp_id`，修改和取消用 `target_id`；取消保留记录，不物理删除。
- 同批新增任务之间的依赖可引用临时编号，执行时统一映射正式 ID。
- `before` 只用于审阅展示，不作为执行依据，执行时必须重新读库。

人工修改草稿递增 `revision`，旧检查和旧确认立即失效；确认绑定 `draft_id + revision`。

## 6. 统一执行

`POST /drafts/{draft_id}/confirm` 在一个事务内完成：

```text
条件领取草稿状态（WHERE id AND revision AND status='pending'）
  → 领取计划版本（project_plans.revision）
  → 领取项目版本（projects.revision）
  → 写任务（apply_task_ops）
  → 写拍摄安排（apply_item_ops）
  → 写业务事件、执行凭据、草稿状态、运行状态
提交
```

- 两个版本号按固定顺序领取，抢不到直接 409，任一写入失败整体回滚。
- `(draft_id, draft_revision)` 唯一约束由数据库兜底；重复确认先查执行凭据，命中即返回原结果。
- 运行状态与业务数据同库同事务，不存在「业务已提交但状态未更新」的分裂；执行凭据查询是防御性检查。
- 已发布通告和拍摄日志不会被改写；执行时按受影响日期复核当天来源，来源变化的通告列入「需要复核」，只提示不自动重发。
- 执行记录保留每项的改动前后值和「建议稿 → 最终稿」的差异，制片改过草稿时也能追溯改了哪些项。

## 7. 接口

```text
POST   /api/projects/{pid}/agent/runs                        发起（可带候选）
GET    /api/projects/{pid}/agent/runs                        最近 20 条工作
GET    /api/projects/{pid}/agent/runs/{run_id}               读取状态、问题、待审草稿
POST   /api/projects/{pid}/agent/runs/{run_id}/resume        恢复（expected_version + decision）
PUT    /api/projects/{pid}/agent/runs/{run_id}/draft         人工修改草稿
POST   /api/projects/{pid}/agent/drafts/{draft_id}/confirm   确认并统一执行
DELETE /api/projects/{pid}/agent/drafts/{draft_id}           放弃
```

`decision` 只有 `provide_input` 和 `discard`；审阅阶段不允许通过恢复接口跳过确认。

## 8. 代码位置

```text
backend/
├─ agent/
│  ├─ router.py         发起、恢复、审阅、确认接口
│  ├─ runner.py         步骤推进与边界保存（保留旧对话循环）
│  ├─ steps.py          各步骤实现
│  ├─ state_machine.py  允许的转换
│  ├─ state.py          状态结构
│  └─ schemas.py        输入与候选契约
├─ service/
│  ├─ agent_work.py     运行、草稿、检查、统一执行、幂等
│  ├─ planning.py       新增 task_operations / plan_task_ops / apply_task_ops
│  └─ shooting.py       新增 prepare_item / plan_item_ops / apply_item_ops
├─ tools/
│  └─ agent_checks.py   分级与漏排计算
├─ dao/agent.py         运行、草稿、执行凭据读写
├─ models/agent.py      三张表
└─ common/database/migrations/agent_v5.py
```

依赖方向：router → runner → steps → service → dao。Service 不导入 agent 包。

前端：`frontend/src/features/agent/` 下的 `api.js`、`agentDraft.js`（分组、差异、分级纯函数）和 `AgentWorkspace.jsx`；导航新增「制片助手」，旧对话助手在其他页面保留。

## 9. 状态

**已实现**：

- P1：三张表和增量迁移、状态机与边界保存、发起/恢复/读取、联合草稿、程序检查与分级、漏排知情确认、人工改草稿、统一事务执行、幂等确认、并发推进保护、重启恢复、跨项目隔离。
- P2：模型理解要求（模式、范围、约束、假设、问题）、模型生成联合候选、模型复核、有限修正、预算上限；模型调用失败转业务错误，不留半成品。
- P3：执行时按受影响日期复核已发布通告的来源指纹，把需要复核的通告列入结果，不自动重发、不改写历史版本。
- P4：执行记录保存每项改动的前后值和「建议稿 → 最终稿」差异，人工改过草稿也能追溯。
- P5：新增「制片助手」页面：发起编排、等待补充时回复、按对象分组审阅草稿、按级别查看检查结果、未排场次知情确认、草稿编辑、确认执行和结果展示。

**未实现**：偏好沉淀与复盘（需要先确认偏好范围和存储），跨项目记忆，自动摘要。

**已知限制**：单次最多 100 项操作、模型调用最多 6 次；任务与拍摄安排不互相引用；多实例部署不在保证范围；模型生成质量尚未用真实剧本验收。

## 10. 验证

2026-11-04 本轮实际执行：

| 检查 | 结果 |
|---|---|
| 后端 pytest | 242 passed |
| V5 回归 | 16 项：联合草稿、漏排知情确认、整体回滚、并发确认、来源变化、暂停恢复、草稿改版、模型越权、重启恢复、自然语言生成、复核修正、制片候选跳过模型、修正预算、模型失败处理、通告复核提示、建议稿与最终稿差异 |
| 离线评估 | 55/55 |
| 前端逻辑测试 | 28 passed（含助手草稿分组、差异、分级 5 项） |
| 前端构建 | 通过 |

未做：真实模型生成质量验收、真实剧组使用、MySQL/PostgreSQL 实测、浏览器页面流程验证（本轮只验证构建和接口契约，未在浏览器里点过新面板）。
