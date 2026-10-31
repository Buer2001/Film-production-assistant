from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.schemas.project import ProjectInput
from backend.service.project import state, list_projects, create_project

router = APIRouter()


@router.get('/api/projects')
def projects(s=Depends(get_session)):
    return list_projects(s)


@router.post('/api/projects')
def create(request: ProjectInput, s=Depends(get_session)):
    return create_project(s, request.name)


@router.get('/api/projects/{pid}')
def detail(pid: str, s=Depends(get_session)):
    return state(s, pid)


@router.get('/api/projects/{pid}/checks')
def checks(pid: str, s=Depends(get_session)):
    return state(s, pid)['checks']


