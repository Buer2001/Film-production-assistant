# Film-production-assistant
Chen's Practical tools.

# 片场 · 学生制片工作台

制片单人使用的助手。剧本拆解、项目日程和筹备资料已提供独立工作区；V4 拍摄管理首版接入正式场次、人员资源和准备任务，支持按天安排、每日通告及逐场日志。旧排期和历史通告保留兼容，旧 Agent 尚未全面接入新业务。

## V4 拍摄管理

- “拍摄安排”按天查看拍摄、转场、用餐、妆造、布光和置景；不同组可并行，按所选人员资源检查冲突、档期及明确关联的准备缺口。
- 拍摄项关联已确认场次，保留剧本版本身份；同场可多次安排。非拍摄项无需场次，跨午夜填写次日结束时间。
- 从安排记录逐场日志，也可直接选择正式场次记录临时加拍；完成情况只表示本次结果。从日志建立补拍安排，保留来源，归还、交场、结款继续在项目日程维护。
- “通告”带入当天安排，补充集合、交妆、交通、用餐和注意事项。点击“保存草稿”后刷新可恢复；发布保存冻结快照，支持历史版本查看和 TXT 下载，不自动发送给剧组。
- 保存失败保留当前输入，版本冲突可刷新来源后再核对。未保存时保护项目和页面切换。
- 启动增量创建 `shooting_items`、`shooting_logs`；通告草稿复用 `notices`，不清库、不自动迁移旧排期。不新增 Agent、RAG、自动排程或逐镜逐条场记。

详见 [V4 架构](docs/shooting-v4-architecture.md) 和 [验证记录](docs/verification.md)。真实剧组使用质量尚待验收。

## V1 剧本拆解

请求日志统一由中间件处理，文件为 `logs/app.jsonl`（5MB 轮转，保留三份备份）。报错中的“请求编号”可在文件中搜索，定位状态、耗时、异常栈及证据失败字段。不使用业务函数日志装饰器；不记录认证头、完整请求体或模型响应。目录通过 `LOG_DIR` 配置，相对路径以 project 为准。

1. 创建或选择项目，粘贴文本或读取UTF-8 TXT（最多50,000字、200场）。原文先保存，再按场次标题分段；不确定边界保留并提示核对。
2. 拆解任务在后台逐场运行，通过SSE把进度和单场结果推送到工作台。显示真实总场数、自动完成、模型失败、人工处理、排除、当前场次及用时，不展示虚假百分比或模型思维链。
3. 完成一场即可查看、编辑、核对原文。单场失败保留原文及原因，其他场继续；本轮结束后可单场重试，也可人工填写后标记处理，或排除非场次。排除保留草稿，可撤销，确认时不入库。
4. 编辑自动保存到服务端草稿文件（默认 .drafts/scripts，可由DRAFT_DIR配置），未确认结果不写正式scene_breakdowns。刷新恢复已完成结果；断线重新连接事件流，不重发整份模型请求。服务重启或中止后保留结果，未完成场次可重试或手工处理。
5. 模型晚到和SSE事件不能覆盖人工字段；保存失败保留输入，支持重试和JSON备份。未保存时禁止切换项目、页面和版本。页数仍手填，缺失项需补齐或明确接受。
6. 全部场次处理后人工确认，通过一个数据库事务写正式结果。入库失败草稿保留；重复确认不重复创建。已确认结果再次编辑也先保存文件草稿，再次确认后才更新正式表。
7. 导入新版前先确认当前版；新版保留旧版，原文相同场次沿用已确认人工修改，变化场次提示匹配和差异。旧版只读。
8. 导出基础XLSX包含拆解表和变更说明，未确认结果标注草稿，已排除行在工作台保留。尚未实测桌面Excel/WPS。

草稿目录是确认前的恢复依据，请在需要保留未确认工作时同时备份；该目录被Git忽略。当前任务执行范围为本机单进程，不支持多实例共享文件草稿。更多实现和故障恢复说明见 [流式拆解](docs/streaming-breakdown.md)。

数据库只新增 `scripts`、`scene_breakdowns` 两张表。Router → Service → DAO 分层，AI 提取、原文校验、输入转换及导出分开；模型通信复用公共客户端，不使用 Agent 循环。入口为 `/api/projects/{pid}/script-workspace`。

启动时执行 `backend/common/database/migrations/script_v1.py` 的幂等增量建表检查，不删除或转换旧数据。修改旧表字段仍须另写迁移，不能清库替代。新表启用外键约束，不双写旧 `records`。

当前仅支持文本/TXT；DOCX、PDF、OCR 尚未接入。旧场次不会自动迁入新拆解。超出结构或原文校验的模型结果不入库；字面证据不代表语义准确，仍须人工核对。真实模型质量及 PostgreSQL 尚未实测。

## V2 项目日程

“项目日程”提供“任务日程 / 人员档期 / 资源档期”三个视图。周档期支持按日期翻周、姓名或资源名称搜索、部门或资源类型筛选；点击日期格查看已登记时段，点击深绿安排查看关联任务。人员、资源可在右侧表单维护资料和可用时段，仍使用原接口及项目版本校验。

档期只用任务的实际使用时间，不从任务起止日期推算占用。未录入可用时段显示“未知”，部分可用单独标注；相邻时段不算重叠，时间重叠仅提示人工核对。未填写实际使用时间或未关联具体资料的任务列入待补清单。查看档期不会修改业务数据；第一版不提供拖拽改期、自动分配或库存数量推断。

V2已收拢旧“筹备”入口：任务统一在项目日程维护，概览的未完成及逾期统计只读正式日程任务，不包含草稿。从日程返回概览会刷新统计。

项目日程内提供独立资源面板，可新增、编辑、删除场地、器材、道具等资源，沿用`records.kind=resource`，不新增表。人工保存资源直接确认并记录事件；资源维护使用项目revision，任务及草稿使用日程revision。正式任务及日程草稿均可按ID选择资源，未落实需求仍可只记名称；生成日程时也提供现有资源，但资源存在不代表已经落实或可用。

资源被正式任务（含已完成项）或待确认日程草稿引用时禁止删除，通用变更接口也执行相同检查。资源改名保留任务引用ID，详情显示当前名称，原任务快照不被自动重写。资源编辑和任务编辑期间禁止切换页面或项目，失败保留输入。

旧`task`记录只读兼容；通用变更接口和Agent禁止新增、修改、删除旧任务，升级前含旧任务的待确认草稿不能继续确认，但可以取消。旧排期、通告、影响分析仍使用历史records，尚未全面接入新任务和新剧本场次，不能据此宣称已完成跨模块检查。没有自动迁移历史任务、自动确认用户草稿或调用真实模型。

资源分层位于`backend/router/resource.py`、`schemas/resource.py`、`service/resource.py`及`dao/resource.py`；前端为`features/resources/ResourcePanel.jsx`。共用变更、通告和排期文件仍有业务用途，保留其职责，删除旧筹备导航及任务入口。

“AI 补全部门”只为空白主责部门的未完成任务生成建议：有待确认草稿时补到原草稿，无草稿时为正式任务创建部门修改草稿，人工确认后生效。已有部门、协作分工、实施人员和日期保留。每次最多300项，显示剩余数量；不确定的部门仍待确认，不自动重跑日程或调用多轮模型。

日程以部门甘特表展示，支持部门折叠、日/周/月刻度、项目节点、任务详情和姓名搜索。草稿与正式安排共用表格。主责部门、协作部门和计划实施人员可人工编辑，支持多名实施人员；旧任务缺少信息时显示待分配，不自动编造。未知日期不绘制假时间条。前端日期/分组回归可运行 `node --test tests/planning_timeline.test.mjs`。

日程生成日志使用 `planning.requested`、`planning.rejected` 和 `planning.response_validated`，可按页面请求编号关联。校验失败记录最多6条安全字段路径、错误类型/原因和完整错误数量，不记录剧本、字段值或完整模型响应。

“项目日程”覆盖筹备、拍摄及器材道具归还和费用结清，不默认安排剪辑、调色或成片交付，不接 Agent。

1. 保存开拍日期、预计杀青/收尾日期及项目现状；未知日期可以留空，开拍日期是模型生成的必要输入。
2. 生成日程建议时读取已确认剧本摘要、正式任务和9类制片检查框架。没有已确认剧本时可按项目现状生成，但需要补充更多信息。
3. 模型返回新增/修改/取消草稿、待确认问题及框架覆盖。草稿先保存在服务端，可编辑、刷新恢复、放弃；确认前不改变正式任务。
4. 审阅完成标准、前置任务、场次资源关联和时间约束后，保存草稿修改，再确认应用。模型新增约束一律待确认，不能伪造已确认硬期限。
5. 正式任务支持人工增改、取消、开始处理、完成及重新打开。显示逾期、今日到期、三天内到期和前置未完成；人工保存直接生效，不再调用模型。
6. 正式日程改变后已有草稿失效，需重新生成；正式剧本来源改变也禁止确认旧草稿。已有场次关联不自动猜测迁移。
7. 有场次关联的正式任务可点击“回看第…场”，只读查看关联剧本版本的已确认拆解、原文行号及完整剧本。未确认草稿不显示；场次失效时提示核对，不自动按场号换到新版。

新增 `project_plans`、`project_tasks` 两表，不迁移旧 `records` 任务。启动时增量创建缺失表并检查必要字段及项目唯一约束；不会升级已有同名表的不兼容结构。离线检查可在 project 目录执行 `.\.venv\Scripts\python.exe -m scripts.migrate_planning`，脚本读取本地 `.env`，执行前应停后端并保留数据库备份。

日程采用计划级 revision、短事务、确认幂等和变更事件。单项目最多500项任务；生成是单次模型请求，失败不自动重试，不持数据库事务等待模型。资源名称只是线索，没有实现统一资源实体或自动影响求解。框架被逐项处理不等于模型判断正确，仍需制片核对。

## 本地启动

本地环境：Python 3.13、Node.js 24、npm 11。Python 依赖安装在 `project/.venv`，前端依赖在 `project/frontend/node_modules`。

环境首次安装：在本目录执行 `python -m venv .venv`，再执行 `.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt`；前端在 `frontend` 目录执行 `npm ci`。`requirements.lock.txt` 记录本轮通过测试的 Python 3.13 依赖版本，`requirements.txt` 保留允许范围。已有 `.env` 时保留原配置，不覆盖。

分别在两个 PowerShell 终端启动（无需激活虚拟环境）：

```powershell
.\scripts\run-backend.ps1
```

```powershell
.\scripts\run-frontend.ps1
```

后端脚本固定使用项目虚拟环境，读取 `.env`，监听 `127.0.0.1:8000`；前端监听 `127.0.0.1:5173` 并代理后端。不要重复启动占用相同端口的实例。也可以按下方原始命令启动。

用户选择本机 MySQL 和 DeepSeek。MySQL 配置见下文；模型默认 `LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`，按 [DeepSeek 官方文档](https://api-docs.deepseek.com/en/) 配置，在本地补填 `LLM_API_KEY`。密钥只保存在 `.env`，该文件和 `.venv` 均已被 Git 忽略。未填写模型配置时仍可手工编辑，自动拆解暂不可用。修改 `.env` 后重启后端。

### 模型调用

统一入口是 `backend.ai.llm.ModelClient`，旧的 `backend.ai.client` 导入继续兼容。不新增 SDK；DeepSeek 和本地 Ollama 共用 `httpx` 请求逻辑。

```python
from backend.ai.llm import ModelClient

# 不传 provider 时使用 LLM_PROVIDER，未配置时仍为 deepseek。
client = ModelClient(provider='qwen3')  # 也可指定 deepseek
message = await client.chat([{'role': 'user', 'content': '提取这段文字中的人物：小林走进教室。'}])
# message 为 assistant 消息对象；普通回答取 message['content']。
# 结构化调用仍使用 chat(messages, tools)，结果由现有业务 Schema 校验。
```

DeepSeek 继续读取 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，`LLM_TIMEOUT` 默认 60 秒。本地 Qwen3 读取 `QWEN3_BASE_URL`（默认 `http://localhost:11434/v1`）、`QWEN3_MODEL`（默认 `qwen3:8b-q4_K_M`）、`QWEN3_TIMEOUT`（默认 180 秒），不需要密钥，也不会使用 DeepSeek 的密钥。

要让现有业务默认使用 Qwen3，在本地 `.env` 中设置 `LLM_PROVIDER=qwen3` 并重启后端，同时保证 Ollama 正在运行且已安装对应模型。应用部署到其他机器时，地址必须指向可访问的 Ollama 服务。不会在两个服务之间自动回退。`/api/health` 的 `agent_configured` 只表示默认模型配置有效，不保证服务可达、模型已加载或解析准确。

本次封装不改变当前默认模型，也不自动更改本地 `.env`。2026-11-03 使用虚构教室场景，通过现有 `script_extractor.extract` 实测本地 Qwen3：成功调用拆解工具，返回一场、地点“教室”、人物“小林”，通过现有结构校验，耗时约 18.5 秒。此为单个样例，不代表长剧本准确率、场号保留或连续调用稳定性；DeepSeek 本次仅验证离线请求契约，未调用真实云端 API。

### 本机 MySQL

在 `.env` 中配置以下内容，替换实际用户名、端口和库名：

```dotenv
DATABASE_URL=mysql+pymysql://YOUR_USER@127.0.0.1:3306/film_production?charset=utf8mb4
MYSQL_PASSWORD=
```

密码单独填写，程序通过 SQLAlchemy URL 对象注入，不需要手工对特殊字符编码。驱动为 PyMySQL（含 MySQL 8 RSA 认证支持），已包含在依赖清单中。

目标数据库需要先存在，使用 utf8mb4 字符集；启动后仅创建缺失的业务表，不删除已有数据。原文字段在 MySQL 使用 LONGTEXT，以容纳 50,000 字中文。旧 SQLite 数据不会自动迁移；如需迁移，必须另行核对并实施。

2026-10-31：本机 MySQL80 服务运行中，连接代码和驱动已准备。等待用户提供账号、库名及本地密码后再切换实际 `.env` 数据库地址；暂保留原 SQLite 连接，尚未完成 MySQL 实库验证。

在本目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.main:app --reload --env-file .env
```

先复制 `.env.example` 到 `.env` 并填写配置。使用 PostgreSQL 时先运行 `docker compose up -d db`。只想本地体验，可把 `.env` 的 `DATABASE_URL` 改为 `sqlite:///./film_production.db`。不要提交密钥。

另一个终端：

```powershell
cd frontend
npm install
npm run dev
```

打开终端显示的本地地址，默认 http://127.0.0.1:5173。后端接口说明：http://127.0.0.1:8000/docs 。模型配置放后端，支持带 tools 的 OpenAI-compatible chat/completions 接口。

## 使用

1. 创建项目，录入场次、导演要求、资源和筹备事项；来源和原文可写入记录。
2. 新增操作先生成草稿，在待确认区展开检查差异后确认。
3. 每确认一份草稿，项目版本加一；其他旧草稿必须重新生成。确认重试不会重复创建记录。
4. 拍摄安排支持日期、时间、制片估时、关联场次及占用资源。布光、置景可单独录入，与拍摄安排并行。
5. 费用分预算、报价、已确定、实际支出，使用十进制金额分别汇总。
6. 发布通告保存完整快照，支持按日递增版本和 TXT 下载；不自动发送给剧组。当天拍摄安排或关联筹备事项变化时，旧通告标为待检查并列出原因；与该天无关的变更不再误报。
7. Agent 可查询、检查、生成修改草稿。它没有确认、发布、任意 SQL 或文件操作工具。
8. “剧本”已切换到独立 V1 工作台，使用方法见上文。旧 `/scripts/parse` 和草稿导入接口暂保留兼容，前端不再调用；旧流程的 50 场限制不代表新工作台限制。
9. 在“影响分析”按资源名称查询，或从记录、待确认草稿点击“分析影响”，查看相关场次、筹备、排期、影响路径及需复核通告。分析只读，建议通过编辑记录或 Agent 另行形成草稿。

## 结构

后端按技术层分包，包内再按业务命名；不再使用 production/业务/router.py 这种组织方式。

- backend/router：HTTP 接口、参数接收、响应转换。
- backend/service：业务流程、版本规则和事务边界。
- backend/dao：数据库查询和修改，不自行提交事务。
- backend/models：SQLAlchemy 表模型，不定义接口输入。
- backend/schemas：Pydantic 输入输出及模型提取结构。
- backend/agent：Agent接口、循环、上下文、工具注册和专用提示词集中管理。
- backend/ai：公共模型客户端、剧本提取器和提示词。
- backend/tools：文本、证据、导出、相似度及旧业务工具。
- backend/common：数据库基础设施、共用 Session 依赖、业务异常、日志中间件。
- backend/main.py：应用创建、生命周期和各 Router 注册。
- frontend/src/features/scripts：剧本组件及 useScriptDraft 自动保存 Hook。
- frontend/src/features/production：旧业务页面及状态 Hook；main.jsx 仅负责应用框架和组装。

接口路径及数据库表不变，旧业务也已迁入对应层包；旧 production 目录已移除，Agent专用实现集中到独立agent包。详见 [架构说明](docs/architecture.md)。

参考 jiaoshoujia 的公共底座、工具 schema 和 Agent 循环思路，未依赖其数据库配置或复制密钥。

## 当前限制

- 单维护者本地/可信环境版本，尚无登录权限，不可直接向公网开放。
- 档期和导演要求暂以结构化记录及备注维护；程序检查同日资源重叠、跨午夜和关联筹备未落实，尚无自动档期求解、天光校验、拖拽排期。
- 资源通过统一名称匹配；场次通过ID关联。资源统一实体引用可在后续完善。
- 通告是否待检查，按当天拍摄安排和快照关联的筹备事项与当前数据比较；未录入的间接关系不会提示，仍需制片判断。
- 原始资料暂手动粘贴；尚无 Word/Excel/PDF 上传解析、OCR、ASR、离线同步、向量检索。
- 会话持久化保存，当前上下文读取最近3轮；长期历史以事件工具检索，不自动生成反思摘要。
- 旧公共表使用 create_all 初始化；新剧本两表有独立增量建表检查，后续字段升级仍须编写对应迁移。
- Agent 当前请求内执行，限制8轮；尚无后台任务队列、流式输出。长请求失败时已提交草稿仍可刷新查看。
- PostgreSQL 配置已提供，实际验证环境和结果见 `docs/verification.md`。

## 检查

```powershell
python -m pytest tests -q
python -m evaluations.run
python scripts/smoke.py
cd frontend
npm run build
```

`scripts/smoke.py` 会自己启动临时 uvicorn 和临时 SQLite，走完建项目到发布通告、导出、影响分析的主流程，结束时清理，不影响正式数据库。

离线评估报告写入 `docs/evaluation-report.json`，具体范围见 [评估说明](docs/analysis-evaluation.md)。模拟模型通过率是业务契约回归结果，不是真实模型准确率。
