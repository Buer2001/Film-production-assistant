# 提供修改草稿创建、确认和拒绝接口，具体校验和事务由修改服务处理。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.schemas.change import ChangeInput
from backend.service.change import propose, confirm, reject as reject_change

router = APIRouter()


# 接口：按 request 生成待确认修改草稿。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects/{pid}/changes')
def draft(pid: str, request: ChangeInput, s=Depends(get_session)):
    return propose(s, pid, request)


# 接口：确认 cid 草稿并应用经校验的修改。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects/{pid}/changes/{cid}/confirm')
def accept(pid: str, cid: str, s=Depends(get_session)):
    return confirm(s, pid, cid)


# 接口：拒绝 cid 草稿。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects/{pid}/changes/{cid}/reject')
def reject(pid: str, cid: str, s=Depends(get_session)):
    return reject_change(s, pid, cid)


