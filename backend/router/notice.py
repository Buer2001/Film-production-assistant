# 提供通告发布及纯文本附件导出接口。
from backend.common.dependencies import get_session
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from backend.schemas.notice import NoticeInput
from backend.service.notice import publish, export_notice

router = APIRouter()


# 接口：按 request 发布通告快照。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理；返回对应业务服务结果。
@router.post('/api/projects/{pid}/notices')
def notice(pid: str, request: NoticeInput, s=Depends(get_session)):
    return publish(s, pid, request)


# 接口：导出 nid 通告为带文件名的纯文本附件。
# pid 为路径项目 ID；会话由请求依赖提供，事务由业务服务管理。
@router.get('/api/projects/{pid}/notices/{nid}/export')
def export(pid: str, nid: str, s=Depends(get_session)):
    content, filename = export_notice(s, pid, nid)
    return Response(content, media_type='text/plain; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'})


