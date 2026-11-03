"""项目日程接口；业务、事务及模型调用交给 Service。"""
from fastapi import APIRouter, Depends, Request
from backend.common.dependencies import get_session
from backend.schemas.planning import SettingsInput, TaskInput, PatchInput, GenerateInput, DraftInput, ConfirmInput, Revision
from backend.service import planning

router = APIRouter(prefix='/api/projects/{pid}/planning', tags=['项目日程 V2'])


@router.get('')
def read(pid: str, session=Depends(get_session)):
    return planning.read(session, pid)


@router.put('/settings')
def settings(pid: str, request: SettingsInput, session=Depends(get_session)):
    return planning.save_settings(session, pid, request)


@router.post('/tasks')
def create_task(pid: str, request: TaskInput, session=Depends(get_session)):
    return planning.save_task(session, pid, request)


@router.patch('/tasks/{task_id}')
def update_task(pid: str, task_id: str, request: PatchInput, session=Depends(get_session)):
    return planning.save_task(session, pid, request, task_id)


@router.post('/generate')
async def generate(pid: str, body: GenerateInput, request: Request):
    return await planning.generate(request.app.state.sessions, pid, body)


@router.put('/draft')
def edit_draft(pid: str, request: DraftInput, session=Depends(get_session)):
    return planning.edit_draft(session, pid, request)


@router.post('/draft/confirm')
def confirm(pid: str, request: ConfirmInput, session=Depends(get_session)):
    return planning.confirm(session, pid, request)


@router.delete('/draft')
def discard(pid: str, request: ConfirmInput, session=Depends(get_session)):
    return planning.discard(session, pid, request)


@router.get('/tasks/{task_id}/evidence')
def evidence(pid: str, task_id: str, script_id: str, scene_id: str, session=Depends(get_session)):
    return planning.task_evidence(session, pid, task_id, script_id, scene_id)


@router.post('/departments')
async def departments(pid: str, body: Revision, request: Request):
    return await planning.suggest_departments(request.app.state.sessions, pid, body)
