# 接收项目对话请求，把模型配置或通信失败转换为 HTTP 响应。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends, HTTPException
from backend.common.errors import BusinessError
from backend.agent.schemas import AgentInput
from backend.service.project import get_project
from backend.agent.runner import run

router = APIRouter()


# 接收路径 pid 和 AgentInput 请求，调用对话循环并返回回答及工具轨迹；配置失败转 503，其他模型失败转 502。
@router.post('/api/projects/{pid}/agent')
async def agent(pid: str, request: AgentInput, s=Depends(get_session)):
    get_project(s, pid)
    try:
        return await run(s, pid, request)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (HTTPException, BusinessError):
        raise
    except Exception as exc:
        raise HTTPException(502, '模型调用失败，请检查服务地址、模型配置和网络；已生成草稿可刷新查看') from exc


