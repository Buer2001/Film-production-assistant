# 测试职责：静态检查分层依赖，并模拟数据库快照验证历史版本的当前读保护。
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# 用例：业务和数据处理层不直接依赖HTTP框架，保持技术层边界。
# 返回：无；使用断言或预期异常检查上述行为。
def test_script_business_layers_do_not_import_http_framework():
    modules = []
    for layer in ('service', 'dao', 'ai', 'tools'):
        files = list((ROOT / 'backend' / layer).rglob('*.py'))
        assert files, layer
        modules.extend(files)
    invalid = []
    for module in modules:
        for node in ast.walk(ast.parse(module.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in ('fastapi', 'starlette'):
                invalid.append(str(module.relative_to(ROOT)))
    assert not invalid, f'业务层不能依赖 HTTP 框架：{invalid}'


# 用例：剧本导出路由通过业务服务调用，不跨层直接组装导出。
# 返回：无；使用断言或预期异常检查上述行为。
def test_script_router_only_uses_services_for_export():
    source = (ROOT / 'backend/router/script.py').read_text(encoding='utf-8')
    imports = [node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)]
    assert not any((module or '').startswith('backend.tools') for module in imports)


# 用例：业务异常保存状态和说明，但不继承HTTP框架异常。
# 返回：无；使用断言或预期异常检查上述行为。
def test_business_error_is_framework_independent():
    from backend.common.errors import BusinessError
    error = BusinessError(409, '版本冲突')
    assert error.status_code == 409 and error.detail == '版本冲突'
    assert not any(base.__module__.startswith(('fastapi', 'starlette')) for base in type(error).__mro__)


# 用例：后端保留约定的技术层包结构及包入口。
# 返回：无；使用断言或预期异常检查上述行为。
def test_backend_uses_layer_packages():
    for layer in ('router', 'service', 'dao', 'models', 'schemas', 'ai', 'tools'):
        package = ROOT / 'backend' / layer
        assert package.is_dir() and (package / '__init__.py').is_file(), layer

# 用例：历史版本检查使用当前读，避免可重复读快照误判旧版可编辑。
# 返回：无；使用断言或预期异常检查上述行为。
def test_history_guard_uses_current_read_instead_of_old_snapshot():
    from types import SimpleNamespace
    import pytest
    from sqlalchemy.dialects import mysql
    from backend.common.errors import BusinessError
    from backend.service.script.version import require_editable
    old = SimpleNamespace(id='v1', project_id='project')
    newest = SimpleNamespace(id='v2', project_id='project')
    class SnapshotSession:
        def get(self, *args):
            return SimpleNamespace(id='project')
        def scalars(self, statement):
            # 模拟可重复读：普通SELECT仍返回旧版本，当前读才看见已提交新版。
            sql = str(statement.compile(dialect=mysql.dialect()))
            values = [newest, old] if 'FOR UPDATE' in sql else [old]
            return SimpleNamespace(all=lambda: values)
    with pytest.raises(BusinessError, match='历史版本只读'):
        require_editable(SnapshotSession(), old)

# 用例：Service不直接构建SQL，DAO不自行提交事务。
# 返回：无；使用断言或预期异常检查上述行为。
def test_services_do_not_build_sql_and_daos_do_not_commit():
    for module in (ROOT / 'backend/service').rglob('*.py'):
        tree = ast.parse(module.read_text(encoding='utf-8'))
        assert not any(isinstance(n, ast.ImportFrom) and (n.module or '').startswith('sqlalchemy') for n in ast.walk(tree)), module
    for module in (ROOT / 'backend/dao').rglob('*.py'):
        tree = ast.parse(module.read_text(encoding='utf-8'))
        assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'commit' for n in ast.walk(tree)), module


# 用例：应用入口负责组装，不直接注册业务接口实现。
# 返回：无；使用断言或预期异常检查上述行为。
def test_main_only_assembles_the_application():
    tree = ast.parse((ROOT / 'backend/main.py').read_text(encoding='utf-8'))
    verbs = {'get', 'post', 'put', 'patch', 'delete'}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
                   isinstance(n.func.value, ast.Name) and n.func.value.id == 'app' and n.func.attr in verbs
                   for n in ast.walk(tree))
