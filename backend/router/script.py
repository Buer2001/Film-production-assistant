from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import Response, StreamingResponse
from backend.schemas.script import ScriptInput, RevisionInput, SaveInput, ConfirmInput
from backend.service.script import version as script, breakdown

router = APIRouter(prefix='/api/projects/{pid}/script-workspace', tags=['剧本拆解 V1'])


@router.get('')
def versions(pid: str, request: Request, db=Depends(get_session)):
    result = []
    for row in script.versions(db, pid):
        item = breakdown.header(row)
        draft = request.app.state.parse_jobs.store.load(pid, row.id)
        if draft:
            item.update({key: draft.get(key, item[key]) for key in ('status', 'revision', 'confirmed_at', 'parse_error')})
        result.append(item)
    return result


@router.post('')
def create(pid: str, payload: ScriptInput, request: Request, db=Depends(get_session)):
    row = script.create(db, pid, payload)
    return breakdown.detail(db, pid, row.id, request.app.state.parse_jobs.store)


@router.get('/{sid}')
def detail(pid: str, sid: str, request: Request, db=Depends(get_session)):
    jobs = request.app.state.parse_jobs
    return breakdown.detail(db, pid, sid, jobs.store, jobs)


@router.post('/{sid}/parse')
async def parse(pid: str, sid: str, payload: RevisionInput, request: Request, db=Depends(get_session)):
    return await breakdown.parse(db, pid, sid, payload.revision, request.app.state.parse_jobs)


@router.get('/{sid}/events')
async def events(pid: str, sid: str, request: Request, after: int = Query(default=0, ge=0), db=Depends(get_session)):
    jobs = request.app.state.parse_jobs
    breakdown.detail(db, pid, sid, jobs.store, jobs)
    db.rollback()
    return StreamingResponse(jobs.events(pid, sid, after), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.post('/{sid}/scenes/{scene_id}/retry')
async def retry(pid: str, sid: str, scene_id: str, payload: RevisionInput, request: Request, db=Depends(get_session)):
    return await breakdown.retry(db, pid, sid, scene_id, payload.revision, request.app.state.parse_jobs)


@router.post('/{sid}/recover')
async def recover(pid: str, sid: str, payload: RevisionInput, request: Request, db=Depends(get_session)):
    return await breakdown.recover(db, pid, sid, payload.revision, request.app.state.parse_jobs)


@router.put('/{sid}')
def save(pid: str, sid: str, payload: SaveInput, request: Request, db=Depends(get_session)):
    return breakdown.save(db, pid, sid, payload, request.app.state.parse_jobs.store)


@router.post('/{sid}/confirm')
def confirm(pid: str, sid: str, payload: ConfirmInput, request: Request, db=Depends(get_session)):
    return breakdown.confirm(db, pid, sid, payload, request.app.state.parse_jobs.store)


@router.get('/{sid}/export')
def export(pid: str, sid: str, request: Request, db=Depends(get_session)):
    filename, content = breakdown.export(db, pid, sid, request.app.state.parse_jobs.store)
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
