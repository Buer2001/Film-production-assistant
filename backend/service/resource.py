# 文件职责：复用通用变更完成资源人工维护，不另建资源写入事务规则。
"""资源业务入口；复用通用变更事务及事件，不新建资源表或第二套写入规则。"""
from backend.common.errors import BusinessError
from backend.dao import resource as dao
from backend.schemas.change import ChangeInput
from backend.service.project import get_project, record_dict
from backend.service.change import propose, confirm


# 用途：读取资源及项目版本。
# 参数：s/pid 为会话及项目 ID。
# 返回及副作用：返回 revision 和 resources；项目不存在抛 BusinessError，不提交。
def read(s, pid):
    project = get_project(s, pid)
    return {'revision': project.revision, 'resources': [record_dict(r) for r in dao.list_resources(s, pid)]}


# 用途：将资源人工保存转为立即确认的通用变更。
# 参数：revision 为项目版本，resource 为资料，rid 为现有 ID，delete 指定删除。
# 返回及副作用：草稿创建延迟提交，交给 confirm 统一落库后返回资源列表；版本、归属或引用不合法抛 BusinessError。
def save(s, pid, revision, resource=None, rid=None, *, delete=False):
    get_project(s, pid)
    if rid and dao.get_resource(s, pid, rid) is None:
        raise BusinessError(404, '资源不存在或不属于本项目')
    operation = {'kind': 'resource', 'id': rid, 'delete': delete, 'data': resource}
    request = ChangeInput(base_revision=revision, reason='制片维护资源', operations=[operation])
    # 人工点击保存已表达确认意图；草稿创建和正式确认在同一事务，失败整体回滚。
    draft = propose(s, pid, request, commit=False)
    confirm(s, pid, draft['id'])
    s.expire_all()
    return read(s, pid)
