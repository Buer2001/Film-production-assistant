# 逐场流式拆解

## 用户流程

保存原文 → 分场 → 后台逐场提取和证据校验 → SSE展示结果 → 人工编辑、重试或排除 → 确认 → 正式入库。

第N场失败只影响本场。失败行保留原文和原因；人工填写后明确标记处理，或排除非场次。不能让失败行静默消失，也不能把失败的默认空值当成成功。

## 职责

- router/script.py：启动、SSE、单场重试、中止、草稿编辑、确认和导出接口。
- service/script/jobs.py：应用生命周期内的本地后台任务，逐场处理；SSE断线不取消任务。
- service/script/breakdown.py：文件草稿、版本保护、人工确认及事务落库。
- ai/script_extractor.py：单场模型提取，复用公共客户端，要求一场返回一条结果。
- tools/script/splitter.py：按明确标题分段，保留原文位置，跳过演职人员表等资料；未知边界交人工核对。
- tools/script/draft_store.py：文件锁、原子替换和持久化。目录默认project/.drafts/scripts，也可设置DRAFT_DIR。
- frontend/features/scripts/useScriptDraft.js：事件流连接和恢复、字段级本地编辑保护、串行草稿保存。

## 接口

- POST /api/projects/{pid}/script-workspace/{sid}/parse：立即返回启动状态，不等待整份结果。
- GET /api/projects/{pid}/script-workspace/{sid}/events?after=N：SSE，包含progress、scene、snapshot、complete、interrupted事件及document快照。
- POST /api/projects/{pid}/script-workspace/{sid}/scenes/{scene_id}/retry：本轮结束后重试单场。
- PUT /api/projects/{pid}/script-workspace/{sid}：按edited_fields保存实际修改字段，不清空其他刚完成的场次。
- POST /api/projects/{pid}/script-workspace/{sid}/confirm：处理所有失败和变化项后，写入正式结果。

## 一致性

原文和必要的版本元数据可先保存，正式场次只在人工确认时写入。草稿编辑revision只在文件内变化；进度sequence独立变化，不制造编辑冲突。base_revision用于确认时校验正式版本。

后台结果跳过人工字段；SSE接收端也合并保留未保存输入。带字段mask的旧快照不能物理删除未见到的场次；排除使用resolution=excluded。

文件写失败保持旧草稿；SQL确认失败保持草稿可重试。如果SQL已提交而文件确认回执写失败，详情读取在文件锁内重读并补齐回执，不能覆盖随后保存的编辑，重复确认幂等。

启动后没有活跃任务但草稿仍为running，标记为interrupted，保留已完成结果。服务重启不会自动重新收费调用全部场次；未完成行由用户重试或人工处理。

当前为本机单进程范围，没有Redis、任务队列或新数据库表。分场规则不代表语义完整性，真实模型质量仍需人工验收。

## 单场错误诊断

结构错误区分未调用工具、调用次数错误、工具名错误、响应结构错误、参数类型错误、JSON无效、Schema字段错误；单场数量及场号不一致也单独报告。草稿保留原场号、中文原因及稳定原因码，Schema错误最多显示6个去重后的字段路径。

`extraction.rejected` 通过现有日志器记录场号、原因码、字段路径、错误总数和请求ID。不记录参数原文、模型完整响应、Pydantic输入值或任意额外字段名；未知字段以field表示。原文证据校验仍按原规则执行。

失败后先查原因并说明修改方案，修改和本地验证完成后，须经用户确认才重试指定场次，不自动重跑全剧本。此前只保存笼统错误的历史失败无法还原具体响应原因。

## 表格字段

- 字数由程序统计每场正文：排除已识别的首行场次标题及所有空白，汉字、标点、字母、数字各计1。无原文的手填场次显示“—”，不采信客户端提交的字数。正式details保存word_count（无原文为null），不再保存page_count；旧页面提交的page_count被忽略，模型Schema不包含这两个统计字段。
- 后续模型拆解的内容要求一句主要事件，通常20～40字；道具只提简短名称和必要特征，不提动作描述。原文证据校验保持不变；已有概括、道具名和说明不批量重写。页面与Excel两张表隐藏道具说明，但内部原始数据保留。
- 自定义字段按项目保存，使用现有records表的script_fields配置记录，具有独立revision；不会进入筹备业务列表或Agent事实索引。最多20列启用、50列总数，名称最多50字符，说明最多300字符，每场值最多3000字符。仅人工填写，不加入模型Schema。
- GET/PUT `/api/projects/{pid}/script-workspace/fields` 查询及保存设置。字段ID由服务端生成；重名、固定列同名、未知ID和过期配置拒绝保存。删除仅归档，可恢复，已有值不删除。
- 场次custom_values复用现有details JSON和文件草稿；edited_fields保护人工修改，原文不变的新版本沿用人工值。导出按当前项目启用列输出，历史版本中的值不会因列隐藏而删除。备份须同时包含数据库和草稿目录。

## 旧页数数据迁移

停后端且没有运行中任务时，在project目录执行 `python -m scripts.migrate_word_counts`。先备份受影响记录的原始details及草稿完整文件到 `.drafts/backups/word-counts-时间戳`，再事务更新数据库并原子替换草稿。失败时数据库回滚并尝试恢复所有已更新草稿；若恢复失败，错误给出文件名及备份路径。脚本可重复执行，不改表结构、剧本原文、人工内容或版本号，也不调用模型。历史extracted_data原样保留作为当时的模型输出，不作为当前details字段使用。
