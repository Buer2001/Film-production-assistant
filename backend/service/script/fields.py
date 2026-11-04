# 文件职责：管理项目自定义列；删除仅归档，保留历史场次字段值。
from backend.common.database.base import uid
from backend.common.errors import BusinessError
from backend.dao.script import fields as dao
from backend.dao import project

RESERVED = {'场号', '内外', '气氛', '页数', '字数', '场景', '内容', '角色', '妆造', '戏用道具', '其他道具', '备注'}


# 用途：读取项目自定义列配置。
# 参数：session/pid 为会话及项目 ID。
# 返回及副作用：返回现有配置或 revision=0 的空配置；项目不存在抛 BusinessError。
def get(session, pid):
    if project.get_project(session, pid) is None:
        raise BusinessError(404, '项目不存在')
    row = dao.get(session, pid)
    return row.data if row else {'revision': 0, 'fields': []}


# 用途：按配置修订号保存字段列表。
# 参数：session/pid 为会话及项目，request 含 revision 和字段定义。
# 返回及副作用：项目锁内验证名称、ID 和数量，归档移除项后提交并返回新配置；不合法或冲突抛 BusinessError。
def save(session, pid, request):
    if not project.lock_project(session, pid):
        raise BusinessError(404, '项目不存在')
    row = dao.get(session, pid, current=True)
    current = row.data if row else {'revision': 0, 'fields': []}
    if current['revision'] != request.revision:
        raise BusinessError(409, '自定义字段已变化，请刷新字段配置后重试')
    previous = {f['id']: f for f in current['fields']}
    fields, seen, names = [], set(), set()
    for item in request.fields:
        value = item.model_dump()
        key = value['id'] or uid()
        if key in seen or (value['id'] and key not in previous):
            raise BusinessError(422, '自定义字段不存在或重复')
        name = value['name'].strip()
        if not name or name in RESERVED or (value['active'] and name in names):
            raise BusinessError(422, '字段名称为空、重复或与固定列同名')
        if value['active']:
            names.add(name)
        seen.add(key)
        fields.append({**value, 'id': key, 'name': name})
    # 删除仅归档，不丢失其他版本、未保存草稿中的字段值。
    fields.extend({**value, 'active': False} for key, value in previous.items() if key not in seen)
    if len(fields) > 50 or sum(f['active'] for f in fields) > 20:
        raise BusinessError(422, '最多20个启用字段，总字段数不超过50个')
    data = {'revision': current['revision'] + 1, 'fields': fields}
    dao.save(session, pid, row, data)
    session.commit()
    return data
