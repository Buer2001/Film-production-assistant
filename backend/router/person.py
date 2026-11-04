# 提供项目人员资料增删改查，写入请求携带项目版本。
"""人员 HTTP 接口，仅解析请求并调用业务服务。"""
from fastapi import APIRouter, Depends, Query
from backend.common.dependencies import get_session
from backend.schemas.person import PersonInput
from backend.service import person

router = APIRouter(prefix='/api/projects/{pid}/people', tags=['项目人员'])


# 接口：读取人员列表。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('')
def read(pid: str, s=Depends(get_session)):
    return person.read(s, pid)


# 接口：按 request.person 新增人员并校验项目 revision。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('')
def create(pid: str, request: PersonInput, s=Depends(get_session)):
    return person.save(s, pid, request.revision, request.person)


# 接口：按 person_id 更新人员并校验项目 revision。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.put('/{person_id}')
def update(pid: str, person_id: str, request: PersonInput, s=Depends(get_session)):
    return person.save(s, pid, request.revision, request.person, person_id)


# 接口：按 person_id 删除人员，校验查询参数 revision 和引用限制。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.delete('/{person_id}')
def delete(pid: str, person_id: str, revision: int = Query(ge=0), s=Depends(get_session)):
    return person.save(s, pid, revision, person_id=person_id, delete=True)
