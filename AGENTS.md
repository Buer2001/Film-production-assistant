# 本项目的实施约定

学生制片工作台：FastAPI + SQLAlchemy + React，单制片本地使用，测试用 FastAPI TestClient。

后端按技术层分包：backend/router、service、dao、models、schemas、ai、tools；共用能力位于 common。包内按业务组织，禁止重新退回 production/业务/router.py 的布局。main.py 只组装应用。Agent按用户确认单独集中在backend/agent（接口、循环、上下文、工具、Schema、专用提示词），复用AI客户端和业务服务，不再分散到各层。
Router 只接收请求和返回响应；Service 管业务和事务；DAO 管 SQL 且不自行 commit；模型调用归 AI，纯文本/文件/校验工具归 tools；业务层不导入 FastAPI，抛 BusinessError，由接口边界统一转换。Session 生命周期复用 common/dependencies.py，通用请求日志留在中间件，不引入业务日志切面装饰器。

## 授权

常规实现已经获得用户授权：直接改代码、补测试、跑自检，不需要先出方案等确认。
只有改变产品范围、改表结构、引入新依赖或动到 `D:/py/film_production/jiaoshoujia/` 时，才先停下来问。

## 文风

- 中文表述，面向用户的文案简洁，解释清楚代价和限制。
- 标题不要用「什么与什么」式对仗；意思相近就合并，不同就拆开。
- 不过度设计：能用一个函数说清的事不要拆成三层。

## 自检

```powershell
python -m pytest tests -q
python -m evaluations.run
cd frontend; npm run build
```

三项都要通过再声称完成。不要写「已验证」而没有实际运行输出。

## 现状

`README.md` 与 `结论池.md` 记录了已实现范围、已知限制和未验证项。未验证的能力不得写成已实现。

## 剧本拆解草稿规则

新拆解按场次后台处理、SSE推送，单场失败不得终止其余场。未确认结果仅在tools/script/draft_store.py管理的文件草稿内，保存、重试、中止使用文件revision；确认时按base_revision检查正式版本，事务写scene_breakdowns。禁止恢复为自动解析后直接入库。进度sequence与编辑revision分开，edited_fields保护人工修改。任务编排属于service/script/jobs.py，不接Agent、不改表、不引入通用队列。
