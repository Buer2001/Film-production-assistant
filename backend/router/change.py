from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.schemas.change import ChangeInput
from backend.service.change import propose, confirm, reject as reject_change

router = APIRouter()


@router.post('/api/projects/{pid}/changes')
def draft(pid: str, request: ChangeInput, s=Depends(get_session)):
    return propose(s, pid, request)


@router.post('/api/projects/{pid}/changes/{cid}/confirm')
def accept(pid: str, cid: str, s=Depends(get_session)):
    return confirm(s, pid, cid)


@router.post('/api/projects/{pid}/changes/{cid}/reject')
def reject(pid: str, cid: str, s=Depends(get_session)):
    return reject_change(s, pid, cid)


