# 测试职责：模拟Windows文件占用，验证冒烟临时目录清理的重试和最终失败行为。
from types import SimpleNamespace
import pytest
from scripts import smoke


# 用例：临时目录清理遇到短暂文件占用时重试，最终能正常退出。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_temporary_workspace_retries_busy_file(monkeypatch):
    attempts = []
    def cleanup():
        attempts.append(True)
        if len(attempts) < 3:
            raise PermissionError('file busy')
    monkeypatch.setattr(smoke.tempfile, 'TemporaryDirectory', lambda **kwargs: SimpleNamespace(name='owned-temp', cleanup=cleanup))
    monkeypatch.setattr(smoke.time, 'sleep', lambda seconds: None)
    with smoke.temporary_workspace() as name:
        assert name == 'owned-temp'
    assert len(attempts) == 3


# 用例：文件持续被占用时清理最终抛错，不静默忽略失败。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_temporary_workspace_does_not_hide_persistent_lock(monkeypatch):
    def cleanup():
        raise PermissionError('still busy')
    monkeypatch.setattr(smoke.tempfile, 'TemporaryDirectory', lambda **kwargs: SimpleNamespace(name='owned-temp', cleanup=cleanup))
    monkeypatch.setattr(smoke.time, 'sleep', lambda seconds: None)
    with pytest.raises(PermissionError):
        with smoke.temporary_workspace():
            pass
