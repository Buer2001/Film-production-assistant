"""文件草稿不属于正式业务事实；每次以原子替换保存，跨实例共用线程锁。"""
import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from threading import RLock

_locks = {}
_registry_lock = RLock()


class DraftStore:
    def __init__(self, directory=None):
        root = Path(__file__).resolve().parents[3]
        self.directory = Path(directory or os.getenv('DRAFT_DIR', str(root / '.drafts/scripts'))).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, pid, sid):
        # 文件名不使用URL中的原始ID，避免任意路径和目录穿越。
        key = hashlib.sha256(f'{pid}:{sid}'.encode('utf-8')).hexdigest()
        return self.directory / (key + '.json')

    def _lock(self, path):
        with _registry_lock:
            return _locks.setdefault(str(path), RLock())

    def load(self, pid, sid):
        path = self._path(pid, sid)
        with self._lock(path):
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding='utf-8'))

    def _write(self, path, value):
        # 先序列化，失败时绝不覆盖旧草稿；临时文件与目标位于同一目录。
        content = json.dumps(value, ensure_ascii=False, allow_nan=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             prefix='.draft-', suffix='.tmp', delete=False) as file:
                temporary = Path(file.name)
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def write(self, pid, sid, value):
        path = self._path(pid, sid)
        with self._lock(path):
            self._write(path, value)

    def update(self, pid, sid, callback):
        path = self._path(pid, sid)
        with self._lock(path):
            current = self.load(pid, sid)
            updated = callback(deepcopy(current))
            if not isinstance(updated, dict):
                raise TypeError('草稿更新必须返回字典')
            self._write(path, updated)
            return deepcopy(updated)

    def delete(self, pid, sid):
        path = self._path(pid, sid)
        with self._lock(path):
            path.unlink(missing_ok=True)
