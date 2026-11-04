# 提供记录、资源及待审草稿的只读影响分析入口。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.service.impact import ImpactInput, analyze_impact

router = APIRouter()


# 接口：按 request 指定目标执行只读影响分析。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects/{pid}/impact')
def impact(pid: str, request: ImpactInput, s=Depends(get_session)):
    return analyze_impact(s, pid, request)


