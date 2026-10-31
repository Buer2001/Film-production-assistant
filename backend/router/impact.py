from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.service.impact import ImpactInput, analyze_impact

router = APIRouter()


@router.post('/api/projects/{pid}/impact')
def impact(pid: str, request: ImpactInput, s=Depends(get_session)):
    return analyze_impact(s, pid, request)


