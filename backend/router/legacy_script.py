# 保留旧剧本解析、历史查询及转修改草稿接口。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException
from backend.common.errors import BusinessError
from backend.service.project import get_project
from backend.schemas.legacy_script import ScriptInput
from backend.service.legacy_script import parse_script, script_draft, script_history

router = APIRouter()


# 接口：按 request 调用旧版解析，模型配置失败转 503、其他调用失败转 502。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
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


# 接口：查询旧版解析历史。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('/api/projects/{pid}/scripts')
def scripts(pid: str, s=Depends(get_session)):
    return script_history(s, pid)


# 接口：把 eid 解析事件转为待确认修改草稿。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects/{pid}/scripts/{eid}/draft')
def import_script(pid: str, eid: str, s=Depends(get_session)):
    return script_draft(s, pid, eid)


