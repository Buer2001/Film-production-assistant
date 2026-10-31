# 离线评估范围

运行 `python -m evaluations.run`，执行旧工作流、旧解析影响分析和 V1 剧本模块的契约测试，报告写入 `docs/evaluation-report.json`。

测试包括逐场流式拆解及草稿工具，使用模拟模型和临时 SQLite，覆盖人工编辑、确认、版本冲突、历史只读、原文证据、取消解析保护、删除核对和导出 XML 结构。

报告不是模型提取准确率，不代表真实模型抗提示注入效果、长剧本完整性、PostgreSQL 并发或桌面 Excel/WPS 兼容性。
