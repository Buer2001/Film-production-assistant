from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql


def test_mysql_password_keeps_special_characters(monkeypatch):
    from backend.common.database.store import configured_url
    monkeypatch.setenv('DATABASE_URL', 'mysql+pymysql://film@127.0.0.1:3306/film_production?charset=utf8mb4')
    monkeypatch.setenv('MYSQL_PASSWORD', 'test@:/#%password')
    url = configured_url()
    assert url.password == 'test@:/#%password'
    assert url.database == 'film_production'
    assert url.username == 'film'
    assert url.query['charset'] == 'utf8mb4'


def test_mysql_script_content_supports_long_chinese_text():
    from backend.models.script import Script
    ddl = str(CreateTable(Script.__table__).compile(dialect=mysql.dialect()))
    assert 'content LONGTEXT' in ddl


def test_sqlite_configuration_is_not_changed(monkeypatch):
    from backend.common.database.store import configured_url
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///./film_production.db')
    monkeypatch.setenv('MYSQL_PASSWORD', 'ignored')
    assert configured_url().get_backend_name() == 'sqlite'
