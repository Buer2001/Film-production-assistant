# 提供项目创建、列表、详情和排期检查接口。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from backend.schemas.project import ProjectInput
from backend.service.project import state, list_projects, create_project

router = APIRouter()


# 接口：返回项目列表。
# 会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/api/projects')
def projects(s=Depends(get_session)):
    return list_projects(s)


# 接口：按 request.name 创建项目。
# 会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects')
def create(request: ProjectInput, s=Depends(get_session)):
    return create_project(s, request.name)


# 接口：读取 pid 项目完整状态。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/api/projects/{pid}')
def detail(pid: str, s=Depends(get_session)):
    return state(s, pid)


# 接口：返回 pid 项目状态中的排期及筹备检查。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/api/projects/{pid}/checks')
def checks(pid: str, s=Depends(get_session)):
    return state(s, pid)['checks']


