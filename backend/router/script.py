# 提供剧本版本、文件草稿、逐场解析事件流和正式确认接口。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import Response, StreamingResponse
from backend.schemas.script import ScriptInput, RevisionInput, SaveInput, ConfirmInput, CustomFieldsInput
from backend.service.script import version as script, breakdown
from backend.service.script import fields

router = APIRouter(prefix='/api/projects/{pid}/script-workspace', tags=['剧本拆解 V1'])


# 接口：读取版本列表，并用文件草稿覆盖解析状态和草稿 revision。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.get('')
def versions(pid: str, request: Request, db=Depends(get_session)):
    result = []
    for row in script.versions(db, pid):
        item = breakdown.header(row)
        draft = request.app.state.parse_jobs.store.load(pid, row.id)
        # 列表展示采用文件草稿状态；正式表尚未确认写入时不能依赖数据库状态呈现解析进度。
        if draft:
            item.update({key: draft.get(key, item[key]) for key in ('status', 'revision', 'confirmed_at', 'parse_error')})
        result.append(item)
    return result


# 接口：按 payload 创建不可变原文版本并返回拆解详情。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('')
def create(pid: str, payload: ScriptInput, request: Request, db=Depends(get_session)):
    row = script.create(db, pid, payload)
    return breakdown.detail(db, pid, row.id, request.app.state.parse_jobs.store)


# 接口：读取项目自定义拆解字段。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/fields')
def custom_fields(pid: str, db=Depends(get_session)):
    return fields.get(db, pid)


# 接口：按 payload 保存自定义字段及字段版本。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.put('/fields')
def save_custom_fields(pid: str, payload: CustomFieldsInput, db=Depends(get_session)):
    return fields.save(db, pid, payload)


# 接口：返回 sid 正式版本及可用文件草稿的拆解详情。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.get('/{sid}')
def detail(pid: str, sid: str, request: Request, db=Depends(get_session)):
    jobs = request.app.state.parse_jobs
    return breakdown.detail(db, pid, sid, jobs.store, jobs)


# 接口：按 payload.revision 启动 sid 逐场后台解析。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('/{sid}/parse')
async def parse(pid: str, sid: str, payload: RevisionInput, request: Request, db=Depends(get_session)):
    return await breakdown.parse(db, pid, sid, payload.revision, request.app.state.parse_jobs)


# 接口：从 after 事件序号续传 sid 的 SSE 进度，检查归属后先回滚只读事务以释放连接状态。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂。
@router.get('/{sid}/events')
async def events(pid: str, sid: str, request: Request, after: int = Query(default=0, ge=0), db=Depends(get_session)):
    jobs = request.app.state.parse_jobs
    breakdown.detail(db, pid, sid, jobs.store, jobs)
    # 开始长连接事件流之前结束只读事务，避免全程持有快照或锁。
    db.rollback()
    return StreamingResponse(jobs.events(pid, sid, after), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# 接口：按 payload.revision 重试 scene_id 单场解析。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('/{sid}/scenes/{scene_id}/retry')
async def retry(pid: str, sid: str, scene_id: str, payload: RevisionInput, request: Request, db=Depends(get_session)):
    return await breakdown.retry(db, pid, sid, scene_id, payload.revision, request.app.state.parse_jobs)


# 接口：按 payload.revision 中止运行中的后台解析并恢复可编辑状态。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('/{sid}/recover')
async def recover(pid: str, sid: str, payload: RevisionInput, request: Request, db=Depends(get_session)):
    return await breakdown.recover(db, pid, sid, payload.revision, request.app.state.parse_jobs)


# 接口：按 payload 保存人工场次编辑到文件草稿。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.put('/{sid}')
def save(pid: str, sid: str, payload: SaveInput, request: Request, db=Depends(get_session)):
    return breakdown.save(db, pid, sid, payload, request.app.state.parse_jobs.store)


# 接口：按 payload 校验草稿和正式基准版本，再确认写入正式场次。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('/{sid}/confirm')
def confirm(pid: str, sid: str, payload: ConfirmInput, request: Request, db=Depends(get_session)):
    return breakdown.confirm(db, pid, sid, payload, request.app.state.parse_jobs.store)


# 接口：导出 sid 当前拆解为带文件名的 XLSX 附件。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；request 用于访问应用级任务或会话工厂。
@router.get('/{sid}/export')
def export(pid: str, sid: str, request: Request, db=Depends(get_session)):
    filename, content = breakdown.export(db, pid, sid, request.app.state.parse_jobs.store)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
