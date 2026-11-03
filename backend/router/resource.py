from fastapi import APIRouter, Depends, Query
from backend.common.dependencies import get_session
from backend.schemas.resource import ResourceInput
from backend.service import resource

router = APIRouter(prefix='/api/projects/{pid}/resources', tags=['项目资源'])


@router.get('')
def read(pid: str, s=Depends(get_session)):
    return resource.read(s, pid)


@router.post('')
def create(pid: str, request: ResourceInput, s=Depends(get_session)):
    return resource.save(s, pid, request.revision, request.resource)


@router.put('/{rid}')
def update(pid: str, rid: str, request: ResourceInput, s=Depends(get_session)):
    return resource.save(s, pid, request.revision, request.resource, rid)


@router.delete('/{rid}')
def delete(pid: str, rid: str, revision: int = Query(ge=0), s=Depends(get_session)):
    return resource.save(s, pid, revision, rid=rid, delete=True)
