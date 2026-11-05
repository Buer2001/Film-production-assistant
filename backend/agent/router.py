# 文件职责：V5 工作发起、恢复、审阅和确认接口；旧的对话入口继续保留。
from fastapi import APIRouter, Depends, HTTPException
from backend.common.dependencies import get_session
from backend.common.errors import BusinessError
from backend.agent import state_machine
from backend.agent.schemas import (AgentInput, RunInput, ResumeInput, DraftEditInput,
                                   DraftConfirmInput, DraftDiscardInput)
from backend.agent.state import new_state
from backend.agent.runner import advance, run
from backend.dao import agent as dao
from backend.service import agent_work
from backend.service.project import get_project

router = APIRouter(prefix='/api/projects/{pid}/agent', tags=['V5 Agent'])


# 旧对话入口：受限工具循环，写操作仍只生成待确认草稿，不参与 V5 联合执行。
@router.post('')
async def assistant(pid: str, request: AgentInput, s=Depends(get_session)):
    get_project(s, pid)
    try:
        return await run(s, pid, request)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (HTTPException, BusinessError):
        raise
    except Exception as exc:
        raise HTTPException(502, '模型调用失败，请检查服务地址、模型配置和网络；已生成草稿可刷新查看') from exc


# 发起一次编排或重排；候选为空时先理解要求，信息不足则停在等待补充。
@router.post('/runs')
async def create_run(pid: str, request: RunInput, s=Depends(get_session)):
    state = new_state(message=request.message,
                      scope=request.scope.model_dump(mode='json') if request.scope else None,
                      candidate=request.candidate.model_dump(mode='json') if request.candidate else None)
    run = agent_work.create_run(s, pid, mode=request.mode or 'compose', message=request.message, state=state)
    return agent_work.run_dict(s, await advance(s, pid, run))


# 列出项目最近的工作记录，只用于入口展示，不代替运行状态。
@router.get('/runs')
def list_runs(pid: str, s=Depends(get_session)):
    get_project(s, pid)
    return [agent_work.run_dict(s, run) for run in dao.list_runs(s, pid)]


# 读取一次工作的当前步骤、问题和待审草稿。
@router.get('/runs/{run_id}')
def read_run(pid: str, run_id: str, s=Depends(get_session)):
    run = dao.get_run(s, pid, run_id)
    if run is None:
        raise BusinessError(404, '工作记录不存在')
    return agent_work.run_dict(s, run)


# 恢复暂停的工作；expected_version 防止两个请求同时推进同一次工作。
@router.post('/runs/{run_id}/resume')
async def resume_run(pid: str, run_id: str, request: ResumeInput, s=Depends(get_session)):
    run = dao.get_run(s, pid, run_id)
    if run is None:
        raise BusinessError(404, '工作记录不存在')
    if run.version != request.expected_version:
        raise BusinessError(409, '工作已被推进，请刷新后重试')
    if run.status not in ('waiting_input', 'waiting_review'):
        raise BusinessError(409, '该工作没有等待人工处理')
    if request.decision == 'discard':
        return agent_work.run_dict(s, agent_work.discard_run(s, pid, run))
    if run.status == 'waiting_review':
        raise BusinessError(409, '审阅阶段请直接修改、确认或放弃草稿')
    state_machine.check(run.current_step, 'understand')
    state = dict(run.state_json or {})
    if request.message:
        state['message'] = request.message
    if request.scope:
        state['scope'] = request.scope.model_dump(mode='json')
    if request.candidate:
        state['candidate'] = request.candidate.model_dump(mode='json')
    # 补充信息后回到理解步骤重新检查门槛，旧问题和旧检查结果不沿用。
    state['questions'] = []
    state['validation'] = None
    if dao.claim_run(s, run.id, request.expected_version, fields={
            'state_json': state, 'current_step': 'understand', 'status': 'running'}) != 1:
        raise BusinessError(409, '工作已被推进，请刷新后重试')
    s.commit()
    s.refresh(run)
    return agent_work.run_dict(s, await advance(s, pid, run))


# 人工修改草稿；revision 必须匹配，旧检查和旧确认随之失效。
@router.put('/runs/{run_id}/draft')
def edit_draft(pid: str, run_id: str, request: DraftEditInput, s=Depends(get_session)):
    run = dao.get_run(s, pid, run_id)
    if run is None:
        raise BusinessError(404, '工作记录不存在')
    return agent_work.draft_dict(agent_work.edit_draft(s, pid, run, request))


# 确认草稿并统一执行；仍有未排场次时必须显式知情保留。
@router.post('/drafts/{draft_id}/confirm')
def confirm_draft(pid: str, draft_id: str, request: DraftConfirmInput, s=Depends(get_session)):
    return agent_work.confirm(s, pid, draft_id, request)


# 放弃草稿；不改动任何正式数据。
@router.delete('/drafts/{draft_id}')
def discard_draft(pid: str, draft_id: str, request: DraftDiscardInput, s=Depends(get_session)):
    return agent_work.discard_draft(s, pid, draft_id, request)
