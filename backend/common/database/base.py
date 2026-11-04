# 共享 ORM 元数据、UUID 主键和 UTC 时间生成函数。
"""公共 ORM 基类和标识/时间生成，不导入业务模型。"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.orm import DeclarativeBase


# 返回新 UUID 字符串，作为业务实体默认主键。
def uid():
    return str(uuid4())


# 返回带 UTC 时区的 ISO 时间文本，统一记录创建及更新时间。
def now():
    return datetime.now(timezone.utc).isoformat()


# 所有业务 ORM 模型共享的声明式基类和元数据集合。
class Base(DeclarativeBase):
    pass
