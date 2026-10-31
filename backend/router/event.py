from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.service.event import list_events

router = APIRouter()


@router.get('/api/projects/{pid}/events')
def events(pid: str, s=Depends(get_session)):
    return list_events(s, pid)


