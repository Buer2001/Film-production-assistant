# 本项目的实施约定

学生制片工作台：FastAPI + SQLAlchemy + React，单制片本地使用。业务规则集中在 `backend/production/service.py`，测试用 FastAPI `TestClient`。

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
