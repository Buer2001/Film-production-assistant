from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException
from backend.common.errors import BusinessError
from backend.service.project import get_project
from backend.schemas.legacy_script import ScriptInput
from backend.service.legacy_script import parse_script, script_draft, script_history

router = APIRouter()


@router.post('/api/projects/{pid}/scripts/parse')
async def parse(pid: str, request: ScriptInput, s=Depends(get_session)):
    get_project(s, pid)
    try:
        return await parse_script(s, pid, request)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (HTTPException, BusinessError):
        raise
    except Exception as exc:
        raise HTTPException(502, '剧本解析服务调用失败，请检查模型配置和网络') from exc


@router.get('/api/projects/{pid}/scripts')
def scripts(pid: str, s=Depends(get_session)):
    return script_history(s, pid)


@router.post('/api/projects/{pid}/scripts/{eid}/draft')
def import_script(pid: str, eid: str, s=Depends(get_session)):
    return script_draft(s, pid, eid)


