"""公共 ORM 基类和标识/时间生成，不导入业务模型。"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.orm import DeclarativeBase


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass
