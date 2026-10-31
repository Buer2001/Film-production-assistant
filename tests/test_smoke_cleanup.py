from types import SimpleNamespace
import pytest
from scripts import smoke


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


def test_temporary_workspace_does_not_hide_persistent_lock(monkeypatch):
    def cleanup():
        raise PermissionError('still busy')
    monkeypatch.setattr(smoke.tempfile, 'TemporaryDirectory', lambda **kwargs: SimpleNamespace(name='owned-temp', cleanup=cleanup))
    monkeypatch.setattr(smoke.time, 'sleep', lambda seconds: None)
    with pytest.raises(PermissionError):
        with smoke.temporary_workspace():
            pass
