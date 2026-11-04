# 定义项目人员资料，稳定主键供任务和资源引用，改名不改变引用身份。
"""人员独立存储身份，改名不改变任务和资源所引用的 ID。"""
from sqlalchemy import String, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from backend.common.database.base import Base, uid


# 项目内人员；身份归属、姓名/部门/角色、联系方式、可用时段和备注分别保存。
class ProjectPerson(Base):
    __tablename__ = 'project_people'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    # 人工资料分为姓名/部门/角色和联系方式；业务引用使用 id，不依赖姓名唯一性。
    name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(200), default='')
    roles: Mapped[list] = mapped_column(JSON, default=list)
    phone: Mapped[str] = mapped_column(String(200), default='')
    contact: Mapped[str] = mapped_column(Text, default='')
    # 可用时段使用共用 Availability 契约，空列表表示没有录入时段资料。
    availability: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default='')
