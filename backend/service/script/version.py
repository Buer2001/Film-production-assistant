# 文件职责：管理剧本导入版本和只允许最新版本编辑的规则。
from backend.common.errors import BusinessError
from backend.dao.script import version as dao
from backend.tools.script.importer import normalize_text


# 用途：读取指定项目剧本版本。
# 参数：session/pid/sid 为会话、项目及版本 ID。
# 返回及副作用：返回版本模型；不存在或归属不符抛 BusinessError(404)。
def require(session, pid, sid):
    row = dao.get(session, pid, sid)
    if row is None:
        raise BusinessError(404, '剧本版本不存在')
    return row


# 用途：列出项目剧本版本。
# 参数：session/pid 为会话及项目 ID。
# 返回及副作用：返回 DAO 排序的版本列表；项目不存在抛 BusinessError。
def versions(session, pid):
    if not dao.project(session, pid):
        raise BusinessError(404, '项目不存在')
    return dao.list_versions(session, pid)


# 用途：检查版本是否为当前最新版本。
# 参数：session 为会话，row 为已有版本模型。
# 返回及副作用：无返回值；历史版本抛 BusinessError(409)，不提交。
def require_editable(session, row):
    latest = dao.list_versions(session, row.project_id, current=True)
    if latest[0].id != row.id:
        raise BusinessError(409, '历史版本只读，请在最新版本操作')


# 用途：基于已确认的最新版导入新剧本。
# 参数：session/pid 为会话及项目，request 含标题、来源、原文及前版 ID。
# 返回及副作用：项目锁内规范原文、创建版本和事件后提交，返回模型；前版不匹配或未确认抛 BusinessError。
def create(session, pid, request):
    if not dao.lock_project(session, pid):
        raise BusinessError(404, '项目不存在')
    latest = dao.list_versions(session, pid, current=True)
    expected = latest[0].id if latest else None
    if request.previous_script_id != expected:
        raise BusinessError(409, '新版必须基于当前最新版本，请刷新')
    if latest:
        from backend.tools.script.draft_store import DraftStore
        draft = DraftStore().load(pid, latest[0].id)
        if draft and draft.get('progress', {}).get('state') != 'confirmed':
            raise BusinessError(409, '请先确认当前草稿，再导入新版')
    if latest and latest[0].status == 'parsing':
        raise BusinessError(409, '上一版仍在解析，请等待完成或恢复后再导入')
    if latest and latest[0].status != 'confirmed':
        raise BusinessError(409, '请先确认当前版本，再导入新版')
    row = dao.add(session, project_id=pid, version_number=(latest[0].version_number + 1 if latest else 1),
                  title=request.title.strip(), version_label=request.version_label,
                  source_name=request.source_name, content=normalize_text(request.content),
                  previous_script_id=request.previous_script_id)
    dao.log(session, pid, 'import', {'script_id': row.id, 'version': row.version_number})
    session.commit()
    return row


# 用途：领取数据库修订版本以开始编辑。
# 参数：session 为会话，row 为版本模型，revision 为预期修订号。
# 返回及副作用：检查最新版本及解析状态后刷新 row，不提交；领取失败回滚并抛 BusinessError。
def claim_edit(session, row, revision):
    # 锁住项目行，使“创建新版”和“修改旧版”不能并发穿透只读检查。
    dao.lock_project(session, row.project_id)
    require_editable(session, row)
    if row.status == 'parsing':
        raise BusinessError(409, '解析中暂不可编辑')
    if not dao.claim(session, row.id, revision):
        session.rollback()
        raise BusinessError(409, '版本已变化，请刷新；本地修改尚未覆盖服务器')
    session.refresh(row)
