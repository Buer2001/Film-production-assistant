# 文件职责：单进程逐场后台解析编排；仅更新文件草稿，单场失败不中断其他场次。
"""单进程解析任务；任务只修改文件草稿，模型等待期间不持有数据库会话。"""
import asyncio
import json
from copy import deepcopy
from backend.tools.script.draft_store import DraftStore
from backend.service.script.comparison import FIELDS, compare
from backend.tools.script.evidence import missing, duplicate_warnings
from backend.common.errors import BusinessError
from backend.tools.script.text import refresh_scene_metadata


# 用途：刷新草稿统计、差异和重复场号提醒。
# 参数：doc 为可变文件草稿，event 为 SSE 事件类型。
# 返回及副作用：原地更新并返回 doc；只递增 progress.sequence，不递增用于人工编辑冲突检测的 revision。
def advance(doc, event='progress'):
    for row in doc['scenes']:
        refresh_scene_metadata(row)
    progress = doc['progress']
    progress['sequence'] += 1
    progress['completed'] = sum(r['parse_status'] == 'succeeded' for r in doc['scenes'])
    progress['failed'] = sum(r['parse_status'] == 'failed' for r in doc['scenes'])
    progress['total'] = len(doc['scenes'])
    kept = [row for row in doc['scenes'] if row.get('resolution') != 'excluded']
    doc['comparison'] = compare(kept, doc.get('previous_scenes', []), bool(doc.get('previous_script_id')), doc.get('deleted_reviewed', False))
    base_warnings = [warning for warning in doc.get('review_issues', []) if not warning.startswith('重复场号：')]
    doc['review_issues'] = list(dict.fromkeys(base_warnings + duplicate_warnings(kept)))
    doc['_event'] = event
    return doc


# 用途：后台解析任务管理器。
# 参数：session_factory 为会话工厂，store 为可选文件存储。
# 返回及副作用：按项目和版本保存进程内 asyncio 任务，协调重试、取消和 SSE；不充当跨进程队列。
class ParseJobs:
    # 用途：初始化后台任务注册表。
    # 参数：session_factory 为会话工厂，store 缺省时创建 DraftStore。
    # 返回及副作用：保存依赖及空任务映射；默认文件存储会确保草稿目录存在。
    def __init__(self, session_factory, store=None):
        self.sessions = session_factory
        self.store = store or DraftStore()
        self.tasks = {}

    # 用途：判断版本是否仍有运行任务。
    # 参数：pid/sid 为项目及版本 ID。
    # 返回及副作用：返回 bool，仅检查本管理器登记且尚未完成的 asyncio 任务。
    def active(self, pid, sid):
        task = self.tasks.get((pid, sid))
        return task is not None and not task.done()

    # 用途：注册并启动一次解析任务。
    # 参数：pid/sid 为项目及版本 ID，scene_id 可指定单场。
    # 返回及副作用：返回 asyncio.Task；同版本已有运行任务抛 BusinessError(409)。
    def start(self, pid, sid, scene_id=None):
        if self.active(pid, sid):
            raise BusinessError(409, '该剧本仍在解析')
        task = asyncio.create_task(self._run(pid, sid, scene_id))
        self.tasks[pid, sid] = task
        return task

    # 用途：串行提取目标场次并合并到最新草稿。
    # 参数：pid/sid 为项目及版本，scene_id 为单场 ID 或 None。
    # 返回及副作用：无返回值；每场重新读取草稿，保留人工保护字段，失败记入该场后继续；取消或整体失败标记中断。
    async def _run(self, pid, sid, scene_id):
        from backend.ai.script_extractor import extract_scene
        from backend.service.script.comparison import apply_previous
        try:
            doc = self.store.load(pid, sid)
            targets = [r['id'] for r in doc['scenes'] if r['id'] == scene_id or (scene_id is None and r['parse_status'] == 'pending')]
            for rid in targets:
                latest = self.store.load(pid, sid)
                entry = next((r for r in latest['scenes'] if r['id'] == rid), None)
                if entry is None or entry.get('resolution') == 'excluded':
                    continue
                # 用途：标记目标场次开始解析。
                # 参数：value 为文件锁内草稿，闭包 rid 为目标场次。
                # 返回及副作用：返回推进 sequence 后的草稿；设置 running 并清除旧错误。
                def begin(value):
                    row = next(r for r in value['scenes'] if r['id'] == rid)
                    row['parse_status'], row['parse_error'] = 'running', ''
                    return advance(value)
                source_doc = self.store.update(pid, sid, begin)
                source = deepcopy(next(r for r in source_doc['scenes'] if r['id'] == rid))
                try:
                    # 模型调用使用独立快照且不持有文件锁；完成后再读取最新草稿合并人工修改。
                    result = await extract_scene(source)
                    # 用途：将模型结果合并到仍有效的草稿。
                    # 参数：value 为最新草稿，闭包 result/source 为模型结果及调用前快照。
                    # 返回及副作用：返回草稿；保留 manual_fields 和人工匹配，重算缺失提醒；场次已移除或任务不运行时不合并。
                    def succeeded(value):
                        row = next((r for r in value['scenes'] if r['id'] == rid), None)
                        if row is None or value['progress']['state'] != 'running':
                            return value
                        proposed = {**source, **result}
                        if value['previous_script_id']:
                            apply_previous([proposed], value['previous_scenes'])
                        # 结果可能晚于人工保存到达：以最新草稿的人工字段和匹配标记决定哪些内容仍允许回写。
                        manual = set(row['evidence'].get('manual_fields', []))
                        for key in FIELDS:
                            if key not in manual and key in proposed:
                                row[key] = proposed[key]
                        if not row['evidence'].get('match_manual'):
                            for key in ('previous_scene_id', 'match_status', 'change_reviewed'):
                                row[key] = proposed.get(key, row[key])
                        row['extracted_data'] = result.get('extracted_data', {k: result.get(k) for k in FIELDS})
                        model_missing = set(missing(result))
                        warnings = [issue for issue in result.get('review_issues', []) if issue not in model_missing]
                        row['review_issues'] = list(dict.fromkeys(missing(row) + warnings))
                        row['parse_status'], row['parse_error'] = 'succeeded', ''
                        return advance(value, 'scene')
                    self.store.update(pid, sid, succeeded)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # 用途：记录单场失败以便重试或人工处理。
                    # 参数：value 为最新草稿，闭包 rid/exc 为场次及错误。
                    # 返回及副作用：返回推进 sequence 的草稿；业务错误保留 detail，其他错误使用固定提示，不中断后续场次。
                    def failed(value):
                        row = next((r for r in value['scenes'] if r['id'] == rid), None)
                        if row is not None:
                            row['parse_status'] = 'failed'
                            row['parse_error'] = str(exc.detail) if isinstance(exc, BusinessError) else '该场解析失败，请重试或人工填写'
                        return advance(value, 'scene')
                    self.store.update(pid, sid, failed)
            # 用途：将整轮解析转为待人工确认。
            # 参数：value 为当前草稿。
            # 返回及副作用：返回更新为 review 且带 complete 事件的草稿，不写数据库确认。
            def complete(value):
                value['status'] = 'review'
                value['progress'].update(state='review', stage='待人工确认')
                return advance(value, 'complete')
            self.store.update(pid, sid, complete)
        except asyncio.CancelledError:
            self.interrupt(pid, sid)
            raise
        except Exception:
            self.interrupt(pid, sid)

    # 用途：修复运行任务中断后的草稿状态。
    # 参数：pid/sid 为项目及版本 ID。
    # 返回及副作用：无返回值；运行状态转 interrupted，未完成 running 场次重置 pending，仅修改文件。
    def interrupt(self, pid, sid):
        # 用途：在文件锁内应用中断状态修复。
        # 参数：doc 为当前草稿。
        # 返回及副作用：返回草稿；仅运行状态推进事件及 sequence，其他状态保持不变。
        def update(doc):
            if doc['progress']['state'] == 'running':
                doc['status'] = 'review'
                doc['progress'].update(state='interrupted', stage='解析已中止，请处理未完成场次')
                for row in doc['scenes']:
                    if row['parse_status'] == 'running':
                        row['parse_status'] = 'pending'
                advance(doc, 'interrupted')
            return doc
        if self.store.load(pid, sid):
            self.store.update(pid, sid, update)

    # 用途：取消指定后台任务并修复中断状态。
    # 参数：pid/sid 为项目及版本 ID。
    # 返回及副作用：无返回值；等待任务取消完成并收集异常，然后执行 interrupt。
    async def cancel(self, pid, sid):
        task = self.tasks.get((pid, sid))
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.interrupt(pid, sid)

    # 用途：关闭管理器中尚未完成的后台任务。
    # 参数：无额外参数。
    # 返回及副作用：无返回值；发送取消并等待所有已登记任务结束，取消路径由任务自身修复草稿。
    async def shutdown(self):
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    # 用途：按进度序号输出 SSE 草稿事件。
    # 参数：pid/sid 为项目及版本，after 为客户端已收到的 sequence。
    # 返回及副作用：异步产生 SSE 文本；首次发快照，发现丢失后台任务时修复中断，草稿缺失或不再运行时结束。
    async def events(self, pid, sid, after=0):
        last = after
        first = True
        while True:
            doc = self.store.load(pid, sid)
            if doc is None:
                return
            if doc['progress']['state'] == 'running' and not self.active(pid, sid):
                self.interrupt(pid, sid)
                doc = self.store.load(pid, sid)
            sequence = doc['progress']['sequence']
            # SSE 去重和续传使用 sequence；人工保存冲突检测的 revision 不随每个进度事件增长。
            if sequence > last or first:
                event = doc.get('_event', 'snapshot') if sequence > last else 'snapshot'
                public = {k: v for k, v in doc.items() if not k.startswith('_')}
                yield f'id: {sequence}\nevent: {event}\ndata: {json.dumps({"document": public}, ensure_ascii=False, default=str)}\n\n'
                last = sequence
                first = False
            if doc['progress']['state'] != 'running':
                return
            await asyncio.sleep(.05)
