# V3 筹备落实实施清单

**目标：** 复用 V2 日程和资源，补齐人员、实际落实资料、可解释的筹备检查，不增加 Agent 工具。

**架构：** Router → Service → DAO；Schema 校验契约，tools 内纯函数计算检查结果。人员新增 project_people 表；资源沿用 records.data；任务沿用 project_tasks.details。继续使用 FastAPI、Pydantic 2、SQLAlchemy 2、SQLite、React 19、Vite，不引入依赖。

**依据：** 本次聊天已确认的 V3 方案及用户“按照计划，将V3的架构做好，把注释写好”的授权。复用当前 checkout，不创建新 worktree，不提交或推送。

## 契约

- 时间段：start_date、end_date 必填；start_time、end_time 成对可选；日期闭区间，无时刻代表整天。availability 项额外含 state=available/unavailable；缺省 [] 表示未知。
- 人员：id、project_id、name、department、roles[]、phone、contact、availability[]、notes。API /api/projects/{pid}/people；GET/POST/PUT/{id}/DELETE/{id}；写入 {revision, person}，返回 {revision, people}，删除通过 query revision。复用项目 revision 和事件。
- 资源：保留 Item 字段，新增 preparation={status:pending/contacting/confirmed/unavailable, contact_person_id:null, contact_name:'', contact:'', availability:[], cost_status:unknown/free/quoted/confirmed, cost_amount:null, notes:''}；旧资源缺失 preparation 时视为未知，不解释旧 amount=0 为免费。联系人用 ID 时支持当前人员资料展示，手填联系信息保留。
- 任务 Details 新增 person_ids[]、usage_period:null|时间段、result_notes:''、requires_people:false。保留 assignees[]（历史/手填姓名），resource_refs 沿用现有结构，一个需求可按现有多个引用表示，不增加需求库。resource_refs 无 ID 为未落实，有 ID 为实际选定。
- GET /api/projects/{pid}/preparation 返回 {issues:[{code, message, task_id, resource_id:null, person_id:null}], checked_tasks}。仅检查正式且未取消任务；resource_refs 无 ID 提示未落实，有 ID 检查 preparation 状态、使用时间；requires_people 且无 person_ids/assignees 提示缺人员（仅姓名时提示资料未关联）；完成且有明确未落实需求追加结果待补。时间未知返回信息不足，不凭任务截止日推断使用日。已完成仍保留事实缺口，避免完成状态掩盖未落实。
- 规则检查不持久化、不调用模型、不查询数据库；Service 汇集数据。改名保 ID、跨项目拒绝、正式任务/待审草稿引用删除保护。模型不得编造或覆盖人员引用、使用时段、结果说明、已落实的资源关联；旧通用接口/Agent 不得擦掉新增资源资料。

## 执行

- [x] 1. 资料后端：先测试失败，再实现共享时间契约、人员各层及增量建表、资源专用契约、兼容保存和删除保护。负责人：资料实现代理。
- [x] 2. 日程和检查：先测试失败，再扩展任务契约/校验、人工资料保护、纯规则检查和只读接口。负责人：主代理。
- [x] 3. 界面：人员面板、资源落实字段、共享时间编辑、任务关联及检查跳转；保护编辑期间输入和项目切换。负责人：界面实现代理。
- [x] 4. 审查：独立代理检查上述实现的范围、事务、引用、模型兼容及前端状态；修复并复核。
- [x] 5. 验证：完整 pytest、evaluations、Node 逻辑测试、前端构建、临时数据库冒烟和必要浏览器交互。更新结论池和验证说明，不改对外 README 展示设计。

## 决策记录

- 时间精度采用已提方案“日期必填、时刻可选”，无记录为未知；若实际业务需要更复杂的重复日历，再独立确认。
- 人员使用项目 revision，资源与任务保持既有版本边界；检查 GET 汇集同一事务中的数据，不缓存结果。
- 当前工作区已有用户授权的结论池收尾待办，保留，不覆盖。
- 沿用 V2 已有契约：模型可建议关联已录入资源，人工确认后保存；不会把关联等同资源确认。已有人工关联受保护。
- 最终 HTTP 冒烟发现脚本仍创建 V2 已停用的 records.task，按当前契约改用日程维护任务；旧通告兼容检查使用 requirement，增加 V3 完整 HTTP 闭环。未恢复旧任务写入口。

## 完成记录

资料测试先出现预期失败，补实现后通过；日程检查测试先 5 failed，完善契约、规则、路由及 JSON 序列化后通过。独立审查及补强后的复核均未发现阻塞缺陷。最终 197 项后端测试、55 项离线评估、10 项前端逻辑测试、Vite 构建、真实 HTTP 冒烟通过；临时浏览器完成录入、关联、缺口消除及资源不可用重新提示，无控制台错误。验证细节见 ../../verification.md。未提交或推送。
