from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from backend.schemas.notice import NoticeInput
from backend.service.notice import publish, export_notice

router = APIRouter()


@router.post('/api/projects/{pid}/notices')
def notice(pid: str, request: NoticeInput, s=Depends(get_session)):
    return publish(s, pid, request)


@router.get('/api/projects/{pid}/notices/{nid}/export')
def export(pid: str, nid: str, s=Depends(get_session)):
    content, filename = export_notice(s, pid, nid)
    return Response(content, media_type='text/plain; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


