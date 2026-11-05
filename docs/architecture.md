# 代码架构

模块化单体：FastAPI、SQLAlchemy、React。项目单制片本地使用，业务按技术层组织，Agent 专用流程集中管理。

```text
backend/
├─ main.py
├─ router/                 # HTTP接口：项目、剧本、草稿、通告、事件、影响分析
├─ service/                # 业务流程和事务
│  ├─ script/              # 剧本版本、拆解、编辑确认、版本对比
│  └─ project.py ...       # 项目及其余旧业务
├─ dao/                    # SQL读写
│  ├─ script/              # 剧本版本和场次
│  └─ project.py ...       # 项目、记录、草稿、通告、事件
├─ models/                 # ORM 表定义
├─ schemas/                # Pydantic输入输出、模型提取结构
├─ agent/                  # Agent接口、循环、上下文、工具、Schema、专用提示词
├─ ai/                     # 共用模型通信、剧本提取、提示词
├─ tools/                  # 文件、文本、证据、导出、相似度等工具
│  └─ script/
└─ common/                 # 共用基础设施
   ├─ dependencies.py      # 接口共用Session生命周期
   ├─ errors.py            # 无HTTP框架依赖的业务异常
   ├─ database/            # Base、连接、Session、迁移
   └─ logging/             # 请求中间件、日志配置、请求ID
```

## 职责和依赖

Router → Service → DAO → 数据库。Service 可以调用 AI 和工具；AI 复用模型客户端、Schema 和文本工具。models 定义数据库存储结构，schemas 定义接口及提取结构，二者职责不同。

- Router 不写 SQL、不控制事务；文件导出由 Service 准备数据和内容，Router 返回响应。
- Service 不导入 FastAPI/Starlette、不构造 SQL；业务失败抛 BusinessError。commit/rollback 属于 Service。
- DAO 执行查询和更新，可 flush，但不自行 commit，不调用模型。
- AI 负责模型通信和结果解析，不查询数据库，不决定业务是否确认。
- tools 保存可复用的文本、文件和规则处理。Agent专用工具适配器位于agent/tools.py，只调用既有服务，不复制业务规则。
- common 不放无归属的业务函数。Base/时间/ID、数据库连接、Session依赖、异常和日志是真正共用能力。
- main.py 只负责应用创建、生命周期、中间件、异常处理和路由注册。

项目锁及事件追加共用 DAO 方法，不在剧本模块重复实现。日志没有独立切面文件和装饰器，仍由中间件统一记录；字段证据诊断保留在校验工具中。

## Agent独立模块

```text
backend/agent/
├─ router.py       # Agent HTTP接口
├─ runner.py       # 旧助手循环与 V5 状态机执行
├─ state_machine.py # V5 状态转换
├─ state.py         # 持久化运行状态
├─ steps.py         # 理解、生成、检查和复核
├─ context.py      # 上下文组织
├─ tools.py        # 工具注册和服务调用适配
├─ schemas.py      # Agent请求结构
└─ prompts/
   └─ system.txt
```

main注册agent/router.py。Agent复用ai/client.py、共用提示词读取、Session依赖及已有Service。数据库模型、DAO和通用能力不复制进Agent；工具不直接执行SQL。剧本拆解保持独立，不经过Agent。

## 前端

- main.jsx：项目选择、导航、应用框架和页面组装。
- features/scripts/ScriptWorkspace.jsx：剧本工作台界面。
- features/scripts/useScriptDraft.js：加载、串行保存、冲突恢复、草稿备份和离开保护。
- features/production：旧业务页面、Agent界面、记录编辑及业务状态Hook。
- api/client.js：共用HTTP请求及请求编号错误显示。

## 保持兼容的范围

HTTP路径、请求响应字段、表名及列定义保持不变；不双写拆解结果，不自动迁移旧场次，不引入新依赖。Python内部导入路径随本次包重组更新，外部脚本如直接导入旧 backend.production 或分散的 service.agent、router.agent，需要同步改用现有层包及 backend.agent 路径。

MySQL历史只读检查改为锁定后的当前读，避免可重复读快照继续允许修改已成为历史的版本。已有测试包含当前读模拟回归和MySQL SQL编译检查，尚未进行真实MySQL并发验收。

## 核心数据和边界

| 业务 | 数据归属 | 关键约束 |
|---|---|---|
| 剧本 | scripts、scene_breakdowns；确认前使用文件草稿 | 保留版本身份，人工确认事务入库 |
| 项目日程 | project_plans、project_tasks | 独立日程 revision，依赖检查和人工字段保护 |
| 筹备落实 | project_people、records 中的资源、任务 details | 稳定 ID 关联，未知档期不等于可用 |
| 拍摄管理 | shooting_items、shooting_logs | 支持并行和跨午夜，日志保留实际结果及补拍来源 |
| 通告 | notices | version=0 为草稿，发布为冻结快照，相关来源变化提示复核 |
| V5 | agent_runs、agent_drafts、agent_executions | 持久化状态机、联合草稿、统一事务及幂等凭据 |

### 剧本解析

后台逐场处理由 service/script/jobs.py 管理，SSE 断开不取消任务。文件草稿通过锁和原子替换保存；编辑 revision 与进度 sequence 分离，edited_fields 保护人工内容。重复确认幂等，正式入库检查来源版本。原文证据匹配不保证语义准确或没有遗漏。

正文非空白字符由程序统计为 word_count，不使用模型估计页数。自定义列仅由人工填写，隐藏不删除历史值。数据库和 .drafts/scripts 需一起备份；文件草稿目前仅支持本机单进程，不用于多实例共享。

### 人员资源和拍摄

人员是管理资料，不是登录账号。任务按稳定 ID 关联人员和资源，手填同名不自动绑定。资源联系人不自动占用联系人的档期；任务期限不代替实际使用时段。准备检查读取正式事实，以纯规则实时计算，不存一套重复检查状态。

拍摄项引用已确认正式场次，保留剧本版本身份；已有日志的安排不可随意换绑场次。仅实际共享的人员资源占用触发重叠检查，未知资料提示核实，不把所有并行安排视为冲突。旧 records 排期保留兼容，不自动迁移或双写。

通告发布检查相关来源并冻结快照，按日递增版本，支持 TXT 导出，不自动发送。无关日期或场次变化不统一使通告失效。日志记录不等于宣布整场拍完。

### V5 联合调整

一个 Agent、首次编排和变化后重排两条工作流，自写持久化状态机，不引入 LangGraph。模型等待不持有业务事务；候选在内存试算，程序检查后进行模型复核，必要时请求人工决定。任务和拍摄安排在同一业务事务执行，包含事件、草稿状态及唯一执行凭据，失败整体回滚，重试返回已有结果。

具体限制及状态转换见 [V5 设计](v5-agent-design.md)，验证范围见 [验证记录](verification.md)。
