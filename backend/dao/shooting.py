# 文件职责：V4 SQL 访问及项目内引用查询；不自行提交，锁由外层业务事务释放。
from datetime import datetime, date
from sqlalchemy import select
from backend.models.shooting import ShootingItem, ShootingLog
from backend.models.script import Script, SceneBreakdown
from backend.models.planning import ProjectPlan, ProjectTask
from backend.models.person import ProjectPerson
from backend.models.record import Record


# 查询整个项目的安排或日志，固定排序使快照指纹和页面顺序稳定。
def items(s, pid, *, locked=False):
    statement = select(ShootingItem).where(ShootingItem.project_id == pid).order_by(ShootingItem.start_at, ShootingItem.id)
    if locked:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return s.scalars(statement).all()


def logs(s, pid, *, locked=False):
    statement = select(ShootingLog).where(ShootingLog.project_id == pid).order_by(ShootingLog.date.desc(), ShootingLog.id)
    if locked:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return s.scalars(statement).all()


# 写事务使用当前读，避免 MySQL 可重复读返回领取项目锁之前的旧资料。
def support(s, pid, *, locked=False):
    people = select(ProjectPerson).where(ProjectPerson.project_id == pid).order_by(ProjectPerson.id)
    resources = select(Record).where(Record.project_id == pid, Record.kind == 'resource').order_by(Record.id)
    if locked:
        people = people.with_for_update().execution_options(populate_existing=True)
        resources = resources.with_for_update().execution_options(populate_existing=True)
    return s.scalars(people).all(), s.scalars(resources).all()


# 查询单个项目对象，跨项目 ID 与不存在都返回 None，避免越权引用。
def get_item(s, pid, iid):
    return s.scalar(select(ShootingItem).where(ShootingItem.project_id == pid, ShootingItem.id == iid))


def get_log(s, pid, lid):
    return s.scalar(select(ShootingLog).where(ShootingLog.project_id == pid, ShootingLog.id == lid))


# 正式场次保留历史版本身份；locked=True 用于写事务，执行当前读避免陈旧快照。
def scenes(s, pid, *, locked=False):
    statement = select(SceneBreakdown, Script).join(Script, Script.id == SceneBreakdown.script_id).where(
        Script.project_id == pid, Script.confirmed_at.is_not(None)).order_by(Script.version_number.desc(), SceneBreakdown.sort_order)
    if locked:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return s.execute(statement).all()


# 按项目→准备计划→任务→剧本的顺序读取发布来源；不改动 V2 自有版本。
def preparation(s, pid, *, locked=False):
    statement = select(ProjectPlan).where(ProjectPlan.project_id == pid)
    if locked:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    plan = s.scalar(statement)
    if not plan:
        return None, []
    statement = select(ProjectTask).where(ProjectTask.plan_id == plan.id).order_by(ProjectTask.id)
    if locked:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return plan, s.scalars(statement).all()


# data 是已校验的 JSON；更新显式列和 JSON 保持一致，提交由服务负责。
def write_item(s, pid, data, current=None):
    current = current or ShootingItem(project_id=pid)
    current.scene_id = data['scene_id']
    current.start_at = datetime.fromisoformat(data['start_at'])
    current.end_at = datetime.fromisoformat(data['end_at'])
    current.data = data
    s.add(current)
    s.flush()
    return current


def write_log(s, pid, data, current=None):
    current = current or ShootingLog(project_id=pid)
    current.scene_id, current.item_id = data['scene_id'], data['item_id']
    current.date = date.fromisoformat(data['date'])
    current.data = data
    s.add(current)
    s.flush()
    return current


# 正式安排含取消项也保留人工引用，必须先解除关联才能删除人员或资源。
def referenced(s, pid, field, value):
    return any(value in row.data.get(field, []) for row in items(s, pid))

