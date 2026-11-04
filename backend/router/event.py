# 提供项目事件历史查询接口。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.service.event import list_events

router = APIRouter()


# 接口：查询项目历史事件。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/api/projects/{pid}/events')
def events(pid: str, s=Depends(get_session)):
    return list_events(s, pid)


