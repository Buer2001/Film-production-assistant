# 文件职责：V4 HTTP 边界；只做参数解析，事务及业务校验统一交给 Service。
from datetime import date
from fastapi import APIRouter, Depends
from backend.common.dependencies import get_session
from backend.schemas.shooting import ItemInput, LogInput, DraftInput, PublishInput
from backend.service import shooting, notice

router = APIRouter(prefix='/api/projects/{pid}/shooting', tags=['拍摄管理'])


# 读取正式安排、日志、选项及检查结果，不改变项目版本。
@router.get('')
def read(pid: str, s=Depends(get_session)):
    return shooting.read(s, pid)


@router.post('/items')
def create_item(pid: str, request: ItemInput, s=Depends(get_session)):
    return shooting.save_item(s, pid, request)


@router.put('/items/{iid}')
def update_item(pid: str, iid: str, request: ItemInput, s=Depends(get_session)):
    return shooting.save_item(s, pid, request, iid)


@router.post('/logs')
def create_log(pid: str, request: LogInput, s=Depends(get_session)):
    return shooting.save_log(s, pid, request)


@router.put('/logs/{lid}')
def update_log(pid: str, lid: str, request: LogInput, s=Depends(get_session)):
    return shooting.save_log(s, pid, request, lid)


# 日期使用标准 ISO 格式，非法日期由请求契约拒绝；跨午夜安排按日期交集纳入。
@router.get('/days/{day}')
def read_day(pid: str, day: date, s=Depends(get_session)):
    return notice.read_day(s, pid, day.isoformat())


@router.put('/days/{day}/draft')
def save_draft(pid: str, day: date, request: DraftInput, s=Depends(get_session)):
    return notice.save_draft(s, pid, day.isoformat(), request)


@router.post('/days/{day}/publish')
def publish(pid: str, day: date, request: PublishInput, s=Depends(get_session)):
    return notice.publish_shooting(s, pid, day.isoformat(), request)
