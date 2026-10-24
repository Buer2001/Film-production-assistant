# 验证记录

## 2026-10-24 复核（当前结果）

环境：Windows 11，Python 3.13.9，Node 24.13.1，npm 11.8.0，SQLite 本地库；未配置模型，未启动 PostgreSQL。

实际运行的命令和输出：

```text
python -m pytest tests -q      → 43 passed in 4.29s
python -m evaluations.run      → Evaluation: 25/25 passed
python scripts/smoke.py        → 12 条 PASS，服务子进程退出、临时库删除
cd frontend; npm run build     → vite v6.4.4，25 modules，built in 0.79s
```

`scripts/smoke.py` 起真实 uvicorn（随机端口、临时 SQLite），用 HTTP 走完：健康检查、建项目、新增场次与筹备和拍摄安排、确认草稿、发布通告、修改关联筹备后通告转待检查且 `reasons` 非空、恢复后重新有效、修改无关场次仍有效、导出 TXT 的文件名与快照内容、按资源做影响分析、删除关联筹备后通告仍待检查且快照不变、模型未配置时 Agent 与剧本解析返回 503。

自动化测试新增覆盖：

- 通告待检查按当天安排和快照关联筹备判定，覆盖无关变更、字段修改、新增、删除、数据恢复后重新有效（`tests/test_notice_status.py`）。
- 多线程并发确认同一草稿只写入一次、确认与取消竞争、两个草稿基于同一版本并发确认（`tests/test_concurrency.py`）。
- 取消草稿接口返回真实状态 `rejected`（`tests/test_workflow.py`）。

## 未验证

- PostgreSQL：Docker Desktop 的 Linux daemon 未运行，`psycopg` 未安装，本轮无法实测。
- 真实模型调用：没有配置密钥，剧本解析与 Agent 只验证了未配置时返回 503，以及离线模拟模型的契约回归。
- 浏览器交互与手机宽度：本轮没有浏览器自动化工具，前端只验证了生产构建通过；2026-10-18 的 390px 截图 `impact-mobile.png` 早于本轮改动。
- Word/Excel/PDF 解析、OCR、ASR、离线同步。

## 2026-10-18 记录

- `python -m evaluations.run`：25项通过，覆盖解析、影响分析、Agent工具边界及原有业务回归；具体用例结果见 `evaluation-report.json`。
- `npm ci --registry=https://registry.npmjs.org`：重装缺少Vite文件的本地依赖，随后生产构建通过。
- 浏览器：使用独立临时SQLite数据库和模拟模型，验证创建项目、剧本文本解析、证据预览、生成草稿、人工确认、资源影响查询，页面显示关联排期、筹备记录及相关通告。下游排期及通告通过API预置。
- 浏览器测试使用8017/5179端口，未修改原8000端口服务和正式本地数据库。
- 390px宽度影响分析页：页面宽度及文档宽度均390px，无横向溢出；截图 `impact-mobile.png`。

## 环境问题

- 本工作区一开始在 DSH 沙箱 workspace-write 下无法写入 `project/` 子目录（目录缺少 WRITE_OWNER、缺少低完整性标签），权限诊断脚本修复后仍被完整性标签拦住，改为在本会话使用完全权限运行。
- codex 沙箱在项目根目录留下 `.test-tmp/pytest-of-不二`，属另一个沙箱账户，普通权限删不掉；已加入 `.gitignore`，不影响构建与测试。
