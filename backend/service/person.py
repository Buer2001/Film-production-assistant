# 文件职责：管理人员资料、引用保护及项目版本，保存时统一写入业务事件。
"""人员保存和删除规则，统一项目版本、引用保护及事件事务。"""
from backend.common.errors import BusinessError
from backend.dao import person as dao, project as projects
from backend.dao.event import add_event
from backend.service.project import get_project


# 用途：提取人员公开字段。
# 参数：person 为人员模型。
# 返回及副作用：返回资料字典，不修改模型。
def person_dict(person):
    return {k: getattr(person, k) for k in ('id', 'project_id', 'name', 'department', 'roles', 'phone', 'contact', 'availability', 'notes')}


# 用途：读取项目人员及当前项目版本。
# 参数：s/pid 为会话及项目 ID。
# 返回及副作用：返回 revision 和 people；项目不存在抛 BusinessError，不提交。
def read(s, pid):
    project = get_project(s, pid)
    return {'revision': project.revision, 'people': [person_dict(p) for p in dao.list_people(s, pid)]}


# 用途：新增、修改或删除人员。
# 参数：revision 为项目版本，person 为资料，person_id 为现有 ID，delete 指定删除。
# 返回及副作用：领取版本、保护引用、写人员及事件后提交并返回列表；冲突、对象不存在或引用未解除抛 BusinessError。
def save(s, pid, revision, person=None, person_id=None, *, delete=False):
    get_project(s, pid)
    # 项目版本领取、引用检查、写人员和事件必须在同一事务内。
    if projects.claim_revision(s, pid, revision, increment=True) != 1:
        s.rollback()
        raise BusinessError(409, '数据已更新，请刷新后重试')
    current = dao.get_person(s, pid, person_id) if person_id else None
    if person_id and current is None:
        raise BusinessError(404, '人员不存在或不属于本项目')
    before = person_dict(current) if current else None
    if delete:
        if dao.referenced(s, pid, person_id):
            raise BusinessError(422, '人员仍被正式任务或待确认资料引用，请先解除关联')
        dao.delete(s, current)
    else:
        current = dao.write(s, pid, person.model_dump(mode='json'), current)
    add_event(s, pid, 'person', {'before': before, 'person': None if delete else person_dict(current), 'revision': revision + 1})
    s.commit()
    s.expire_all()
    return read(s, pid)
