# 验证记录

日期：2026-10-18。

- `python -m evaluations.run`：25项通过，覆盖解析、影响分析、Agent工具边界及原有业务回归；具体用例结果见 `evaluation-report.json`。
- `npm ci --registry=https://registry.npmjs.org`：重装缺少Vite文件的本地依赖，随后生产构建通过。
- 浏览器：使用独立临时SQLite数据库和模拟模型，验证创建项目、剧本文本解析、证据预览、生成草稿、人工确认、资源影响查询，页面显示关联排期、筹备记录及相关通告。下游排期及通告通过API预置。
- 浏览器测试使用8017/5179端口，未修改原8000端口服务和正式本地数据库。
- 390px宽度影响分析页：页面宽度及文档宽度均390px，无横向溢出；截图 `impact-mobile.png`。

未验证：真实模型提取质量、真实付费调用、PostgreSQL、Word/PDF解析、OCR。离线通过不代表生产可用。
