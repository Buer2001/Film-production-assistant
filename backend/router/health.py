# 提供服务存活和模型配置合法性检查，不进行模型网络探测。
from fastapi import APIRouter
from backend.ai.llm.config import is_configured

router = APIRouter()


# 接口：返回服务状态及模型配置是否合法，不验证网络。
# 返回对应业务服务结果。
@router.get('/api/health')
def health():
    return {'status': 'ok', 'agent_configured': is_configured()}


