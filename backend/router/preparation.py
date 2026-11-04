# 提供筹备事实检查报告，不保存另一套筹备状态。
"""筹备检查只读入口；规则和事务边界均由业务层维护。"""
from fastapi import APIRouter, Depends
from backend.common.dependencies import get_session
from backend.schemas.preparation import PreparationReport
from backend.service import preparation

router = APIRouter(prefix='/api/projects/{pid}/preparation', tags=['筹备检查'])


# 接口：只读计算筹备检查，按 PreparationReport 返回问题列表及检查任务数。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.get('', response_model=PreparationReport)
def read(pid: str, session=Depends(get_session)):
    return preparation.read(session, pid)
