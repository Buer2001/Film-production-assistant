# 提供项目日程、任务、模型建议和草稿确认接口。
"""项目日程接口；业务、事务及模型调用交给 Service。"""
from fastapi import APIRouter, Depends, Request
from backend.common.dependencies import get_session
from backend.schemas.planning import SettingsInput, TaskInput, PatchInput, GenerateInput, DraftInput, ConfirmInput, Revision
from backend.service import planning

router = APIRouter(prefix='/api/projects/{pid}/planning', tags=['项目日程 V2'])


# 接口：读取项目日程。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('')
def read(pid: str, session=Depends(get_session)):
    return planning.read(session, pid)


# 接口：按 request 保存计划设置。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.put('/settings')
def settings(pid: str, request: SettingsInput, session=Depends(get_session)):
    return planning.save_settings(session, pid, request)


# 接口：按 request 新建正式任务。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/tasks')
def create_task(pid: str, request: TaskInput, session=Depends(get_session)):
    return planning.save_task(session, pid, request)


# 接口：按 task_id 和 request 局部更新任务。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.patch('/tasks/{task_id}')
def update_task(pid: str, task_id: str, request: PatchInput, session=Depends(get_session)):
    return planning.save_task(session, pid, request, task_id)


# 接口：按 body 调用模型生成待审日程草稿。
# pid 为路径项目 ID；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('/generate')
async def generate(pid: str, body: GenerateInput, request: Request):
    return await planning.generate(request.app.state.sessions, pid, body)


# 接口：按 request 编辑待审建议。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.put('/draft')
def edit_draft(pid: str, request: DraftInput, session=Depends(get_session)):
    return planning.edit_draft(session, pid, request)


# 接口：按 request 校验版本并确认日程草稿。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/draft/confirm')
def confirm(pid: str, request: ConfirmInput, session=Depends(get_session)):
    return planning.confirm(session, pid, request)


# 接口：按 request 废弃指定草稿。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.delete('/draft')
def discard(pid: str, request: ConfirmInput, session=Depends(get_session)):
    return planning.discard(session, pid, request)


# 接口：读取 task_id 引用的 script_id/scene_id 原文证据。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/tasks/{task_id}/evidence')
def evidence(pid: str, task_id: str, script_id: str, scene_id: str, session=Depends(get_session)):
    return planning.task_evidence(session, pid, task_id, script_id, scene_id)


# 接口：按 body 中的 revision 生成部门建议。
# pid 为路径项目 ID；request 用于访问应用级任务或会话工厂；返回对应业务服务结果。
@router.post('/departments')
async def departments(pid: str, body: Revision, request: Request):
    return await planning.suggest_departments(request.app.state.sessions, pid, body)
