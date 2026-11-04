# 创建数据库引擎、公共表和会话工厂，并保留历史模型导入入口。
"""数据库连接和 Session；旧模型导入路径保留兼容，不在此定义业务表。"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from backend.common.database.base import Base, uid, now
# 兼容旧调用方，确保所有地方复用同一 ORM 类，不重复定义表。
from backend.models.project import Project
from backend.models.record import Record
from backend.models.change import Change
from backend.models.notice import Notice
from backend.models.event import Event


# 读取环境数据库地址并返回 SQLAlchemy URL；MySQL 密码可独立配置，避免特殊字符破坏地址。
def configured_url():
    url = make_url(os.getenv('DATABASE_URL', 'sqlite:///./film_production.db'))
    if url.get_backend_name() == 'mysql' and 'MYSQL_PASSWORD' in os.environ:
        # 密码单独保存，避免 @、#、百分号等字符被当作 URL 结构。
        url = url.set(password=os.environ['MYSQL_PASSWORD'])
    return url


# 按 url 建引擎和旧公共表，返回引擎及会话工厂；SQLite 关闭线程限制并为每次连接启用外键。
def database(url):
    parsed = make_url(url)
    engine = create_engine(parsed, pool_pre_ping=True,
        **({'connect_args': {'check_same_thread': False}} if parsed.get_backend_name() == 'sqlite' else {}))
    if engine.dialect.name == 'sqlite':
        # 接收 DBAPI connection 和事件占位参数；执行 SQLite 外键开关，无返回值。
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(connection, _):
            # SQLite 默认不校验外键，新拆解表必须显式启用。
            connection.execute('PRAGMA foreign_keys=ON')
    # 新剧本表由专用增量迁移创建，旧公共表初始化保持兼容。
    Base.metadata.create_all(engine, tables=[Project.__table__, Record.__table__,
                             Change.__table__, Notice.__table__, Event.__table__])
    # 提交后不自动过期 ORM 属性，便于业务在提交后组装响应；关闭和回滚仍由请求生命周期管理。
    return engine, sessionmaker(engine, expire_on_commit=False)
