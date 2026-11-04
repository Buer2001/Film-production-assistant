# 提供项目资源增删改查，写入使用项目 revision 进行并发校验。
from fastapi import APIRouter, Depends, Query
from backend.common.dependencies import get_session
from backend.schemas.resource import ResourceInput
from backend.service import resource

router = APIRouter(prefix='/api/projects/{pid}/resources', tags=['项目资源'])


# 接口：读取资源列表。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('')
def read(pid: str, s=Depends(get_session)):
    return resource.read(s, pid)


# 接口：按 request.resource 新增资源并校验项目 revision。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('')
def create(pid: str, request: ResourceInput, s=Depends(get_session)):
    return resource.save(s, pid, request.revision, request.resource)


# 接口：按 rid 更新资源并校验项目 revision。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.put('/{rid}')
def update(pid: str, rid: str, request: ResourceInput, s=Depends(get_session)):
    return resource.save(s, pid, request.revision, request.resource, rid)


# 接口：按 rid 删除资源，校验查询参数 revision 和引用限制。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.delete('/{rid}')
def delete(pid: str, rid: str, revision: int = Query(ge=0), s=Depends(get_session)):
    return resource.save(s, pid, revision, rid=rid, delete=True)
