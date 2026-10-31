# 代码架构

2026-10-31：按用户确认的技术层分包，层包内再按业务组织。原来按 production/业务 分文件的布局已移除。Agent按用户后续确认，作为独立模块集中管理。

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
├─ models/                 # ORM表定义，含原有表和两张V1表
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
├─ runner.py       # 多步模型/工具调用循环
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
