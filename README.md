# 片场 · 学生制片工作台

面向约20人的学生剧组，制片单人维护。筹备平行推进，制片估时和排期，Agent 查询项目并提交待确认修改。

## 本地启动

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
8. 在“剧本”中粘贴文本或读取 UTF-8 TXT，解析场次、人物、场地、道具和昼夜信息；展开原文证据核对后生成草稿，再在待确认区保存。需配置模型；最多50,000字、50场，不自动猜测拍摄日期或时长。
9. 在“影响分析”按资源名称查询，或从记录、待确认草稿点击“分析影响”，查看相关场次、筹备、排期、影响路径及需复核通告。分析只读，建议通过编辑记录或 Agent 另行形成草稿。

## 结构

- `backend/common`：数据库、模型客户端；确认和版本规则目前集中在业务服务，避免重复实现。
- `backend/production`：结构化记录、事务确认、排期检查、费用汇总、通告快照与待检查判定。
- `backend/agent`：工具注册、模型循环、上下文和提示词。
- `frontend`：React 工作台，支持手机布局。
- `tests`：一致性、项目隔离、通告和 Agent 权限测试，含多线程确认竞争与通告待检查判定。
- `scripts/smoke.py`：真实 uvicorn 进程加临时 SQLite 的 HTTP 冒烟检查，不依赖模型。

参考 jiaoshoujia 的公共底座、工具 schema 和 Agent 循环思路，未依赖其数据库配置或复制密钥。

## 当前限制

- 单维护者本地/可信环境版本，尚无登录权限，不可直接向公网开放。
- 档期和导演要求暂以结构化记录及备注维护；程序检查同日资源重叠、跨午夜和关联筹备未落实，尚无自动档期求解、天光校验、拖拽排期。
- 资源通过统一名称匹配；场次通过ID关联。资源统一实体引用可在后续完善。
- 通告是否待检查，按当天拍摄安排和快照关联的筹备事项与当前数据比较；未录入的间接关系不会提示，仍需制片判断。
- 原始资料暂手动粘贴；尚无 Word/Excel/PDF 上传解析、OCR、ASR、离线同步、向量检索。
- 会话持久化保存，当前上下文读取最近3轮；长期历史以事件工具检索，不自动生成反思摘要。
- 初始化使用 create_all；既有表结构升级尚需添加正式迁移脚本。
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
