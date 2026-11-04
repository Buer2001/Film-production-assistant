# 文件职责：保存未确认拆解文件；同进程跨实例共用线程锁，通过同目录临时文件原子替换。
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


# 用途：文件草稿存储器。
# 参数：directory 可显式指定根目录，否则使用 DRAFT_DIR 或默认目录。
# 返回及副作用：管理 JSON 草稿读写和原子替换；线程锁只覆盖同一进程，不提供跨进程互斥。
class DraftStore:
    # 用途：确定草稿目录并确保目录存在。
    # 参数：directory 为可选路径，优先于环境变量和默认值。
    # 返回及副作用：初始化 directory；创建目录失败时传播文件系统异常。
    def __init__(self, directory=None):
        root = Path(__file__).resolve().parents[3]
        self.directory = Path(directory or os.getenv('DRAFT_DIR', str(root / '.drafts/scripts'))).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    # 用途：计算不包含原始标识的草稿文件路径。
    # 参数：pid/sid 为项目及剧本版本 ID。
    # 返回及副作用：返回以组合标识 SHA-256 摘要命名的 Path，防止原始 ID 影响路径层级。
    def _path(self, pid, sid):
        # 文件名不使用URL中的原始ID，避免任意路径和目录穿越。
        key = hashlib.sha256(f'{pid}:{sid}'.encode('utf-8')).hexdigest()
        return self.directory / (key + '.json')

    # 用途：获取路径对应的共享可重入锁。
    # 参数：path 为草稿路径。
    # 返回及副作用：返回 RLock；注册表锁保护同进程跨存储实例的锁创建。
    def _lock(self, path):
        with _registry_lock:
            return _locks.setdefault(str(path), RLock())

    # 用途：读取一份草稿。
    # 参数：pid/sid 为项目及版本 ID。
    # 返回及副作用：线程锁内返回 JSON 数据，不存在返回 None；文件读取或 JSON 解析失败原样传播。
    def load(self, pid, sid):
        path = self._path(pid, sid)
        with self._lock(path):
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding='utf-8'))

    # 用途：将草稿原子替换到目标路径。
    # 参数：path 为目标 Path，value 为可 JSON 序列化的草稿。
    # 返回及副作用：无返回值；先拒绝 NaN 并序列化，再写同目录临时文件、flush/fsync 后替换；异常传播，finally 清临时文件。
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

    # 用途：在路径锁内覆盖保存草稿。
    # 参数：pid/sid 为项目及版本，value 为草稿数据。
    # 返回及副作用：无返回值；复用原子写入，序列化和文件异常传播，不写正式数据库。
    def write(self, pid, sid, value):
        path = self._path(pid, sid)
        with self._lock(path):
            self._write(path, value)

    # 用途：在同一锁内完成读取、转换和原子写入。
    # 参数：pid/sid 为项目及版本，callback 接收当前内容的深复制，须返回字典。
    # 返回及副作用：返回保存结果的深复制；回调异常直接传播，返回非字典抛 TypeError，失败时不写回回调结果。
    def update(self, pid, sid, callback):
        path = self._path(pid, sid)
        with self._lock(path):
            current = self.load(pid, sid)
            updated = callback(deepcopy(current))
            if not isinstance(updated, dict):
                raise TypeError('草稿更新必须返回字典')
            self._write(path, updated)
            return deepcopy(updated)

    # 用途：删除指定文件草稿。
    # 参数：pid/sid 为项目及版本 ID。
    # 返回及副作用：无返回值；路径锁内删除，不存在时忽略，其他文件系统异常传播。
    def delete(self, pid, sid):
        path = self._path(pid, sid)
        with self._lock(path):
            path.unlink(missing_ok=True)
