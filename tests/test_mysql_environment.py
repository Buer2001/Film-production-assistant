# 测试职责：验证数据库配置和MySQL建表语句；编译DDL不代表连接过真实MySQL。
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql


# 用例：MySQL密码中的特殊字符按原值传入，不被连接URL解析破坏。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_mysql_password_keeps_special_characters(monkeypatch):
    from backend.common.database.store import configured_url
    monkeypatch.setenv('DATABASE_URL', 'mysql+pymysql://film@127.0.0.1:3306/film_production?charset=utf8mb4')
    monkeypatch.setenv('MYSQL_PASSWORD', 'test@:/#%password')
    url = configured_url()
    assert url.password == 'test@:/#%password'
    assert url.database == 'film_production'
    assert url.username == 'film'
    assert url.query['charset'] == 'utf8mb4'


# 用例：MySQL剧本正文使用可容纳长中文文本的LONGTEXT列。
# 返回：无；使用断言或预期异常检查上述行为。
def test_mysql_script_content_supports_long_chinese_text():
    from backend.models.script import Script
    ddl = str(CreateTable(Script.__table__).compile(dialect=mysql.dialect()))
    assert 'content LONGTEXT' in ddl


# 用例：配置MySQL密码不会影响SQLite连接地址。
# 参数：monkeypatch 为临时替换配置或依赖的pytest工具。
# 返回：无；使用断言或预期异常检查上述行为。
def test_sqlite_configuration_is_not_changed(monkeypatch):
    from backend.common.database.store import configured_url
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///./film_production.db')
    monkeypatch.setenv('MYSQL_PASSWORD', 'ignored')
    assert configured_url().get_backend_name() == 'sqlite'
