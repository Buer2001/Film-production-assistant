# codex 任务书 · 第 2 轮

继续上一轮。现状：`pytest` 43 项通过（含你新增的通告判定和并发测试），离线评估 25/25，前端构建通过。本轮做三件事，都是小改动。

## 任务 1：修 reject 接口返回错误状态

`backend/main.py` 的 `POST /api/projects/{pid}/changes/{cid}/reject` 用 `s.execute(update(...))` 改状态，但随后 `return {'status': c.status}` 读的是 ORM 里缓存的旧对象，接口实际返回 `pending`，与数据库不符。改成返回真实状态（`rejected`），并补一条测试断言响应体。顺带检查同一文件里有没有同类「更新后读旧对象」的地方，有就一起修。

## 任务 2：模型未配置时前端给出明确提示

现在只有点开 Agent 侧栏的空白状态才提示模型未配置，用户容易先撞一次 503 再猜原因。改动：

- `frontend/src/api/client.js` 或 `main.jsx` 增加 `/api/health` 调用，`agent_configured` 为 false 时在页面顶部显示一条可关闭的提示：模型未配置，Agent 与剧本解析不可用，其余功能正常；配置方法见 README。
- 模型已配置时不显示，不引入新的轮询，不要每页都请求。
- 待确认区文案从「确认会更新正式记录，并使现有通告提示待检查」改为「确认会更新正式记录；与该通告当天相关的变更会让它转为待检查」。
- 不新增依赖，不改样式文件里已有的类名。

## 任务 3：真实 HTTP 端到端冒烟脚本

新增 `scripts/smoke.py`，从项目根目录运行 `python scripts/smoke.py`：

- 用临时 SQLite 文件启动真实 uvicorn 子进程（随机空闲端口，`127.0.0.1`），用 httpx 走 HTTP，结束时保证子进程退出、临时库删除。
- 覆盖：健康检查；建项目；新增场次、筹备、拍摄安排（含关联场次）；确认草稿；发布当天通告；修改关联筹备状态；查通告应转为待检查且 reasons 非空；改一个无关场次；通告仍有效；导出通告 TXT 并检查文件名和内容；按资源做影响分析；删除关联筹备后再看通告；`/agent` 与 `/scripts/parse` 在未配置模型时返回 503 而不是 500。
- 每步打印 `PASS 说明`，失败打印 `FAIL 说明` 并以退出码 1 结束；所有断言失败信息要说清期望值和实际值。
- 不依赖真实模型、不写 `docs/`、不动正式数据库。
- 顺带在 `.gitignore` 加 `scripts/__pycache__/` 和 `.test-tmp/`（一项遗留的沙箱临时目录，普通权限删不掉，别去删它）。

## 验收

```
python -m pytest tests -q
python -m evaluations.run
python scripts/smoke.py
cd frontend; npm run build
```

四条都要通过，最终回复里贴真实输出（冒烟脚本的 PASS 行贴关键几条即可），并说明改了哪些文件。

## 边界

- 不加依赖、不改表结构、不重写前端、不写 `README.md` 和 `docs/`。
- 别改通告判定规则和并发测试的既有断言，除非有真实缺陷。
- 注释与用户文案用中文。
