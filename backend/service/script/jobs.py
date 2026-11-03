"""单进程解析任务；任务只修改文件草稿，模型等待期间不持有数据库会话。"""
import asyncio
import json
from copy import deepcopy
from backend.tools.script.draft_store import DraftStore
from backend.service.script.comparison import FIELDS, compare
from backend.tools.script.evidence import missing, duplicate_warnings
from backend.common.errors import BusinessError
from backend.tools.script.text import refresh_scene_metadata


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


class ParseJobs:
    def __init__(self, session_factory, store=None):
        self.sessions = session_factory
        self.store = store or DraftStore()
        self.tasks = {}

    def active(self, pid, sid):
        task = self.tasks.get((pid, sid))
        return task is not None and not task.done()

    def start(self, pid, sid, scene_id=None):
        if self.active(pid, sid):
            raise BusinessError(409, '该剧本仍在解析')
        task = asyncio.create_task(self._run(pid, sid, scene_id))
        self.tasks[pid, sid] = task
        return task

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
                def begin(value):
                    row = next(r for r in value['scenes'] if r['id'] == rid)
                    row['parse_status'], row['parse_error'] = 'running', ''
                    return advance(value)
                source_doc = self.store.update(pid, sid, begin)
                source = deepcopy(next(r for r in source_doc['scenes'] if r['id'] == rid))
                try:
                    result = await extract_scene(source)
                    def succeeded(value):
                        row = next((r for r in value['scenes'] if r['id'] == rid), None)
                        if row is None or value['progress']['state'] != 'running':
                            return value
                        proposed = {**source, **result}
                        if value['previous_script_id']:
                            apply_previous([proposed], value['previous_scenes'])
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
                    def failed(value):
                        row = next((r for r in value['scenes'] if r['id'] == rid), None)
                        if row is not None:
                            row['parse_status'] = 'failed'
                            row['parse_error'] = str(exc.detail) if isinstance(exc, BusinessError) else '该场解析失败，请重试或人工填写'
                        return advance(value, 'scene')
                    self.store.update(pid, sid, failed)
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

    def interrupt(self, pid, sid):
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

    async def cancel(self, pid, sid):
        task = self.tasks.get((pid, sid))
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.interrupt(pid, sid)

    async def shutdown(self):
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

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
            if sequence > last or first:
                event = doc.get('_event', 'snapshot') if sequence > last else 'snapshot'
                public = {k: v for k, v in doc.items() if not k.startswith('_')}
                yield f'id: {sequence}\nevent: {event}\ndata: {json.dumps({"document": public}, ensure_ascii=False, default=str)}\n\n'
                last = sequence
                first = False
            if doc['progress']['state'] != 'running':
                return
            await asyncio.sleep(.05)
