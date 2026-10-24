import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, update
from backend.common.database.store import database, Project, Change, Notice, Event
from backend.production.project.schemas import ProjectInput, ChangeInput, NoticeInput, AgentInput
from backend.production.service import state, propose, confirm, publish, get_project, rows
from backend.agent.runtime.runner import run
from backend.production.analysis import ScriptInput, ImpactInput, parse_script, script_draft, analyze_impact


def create_app(database_url=None):
    url = database_url or os.getenv('DATABASE_URL', 'sqlite:///./film_production.db')
    @asynccontextmanager
    async def lifespan(app):
        engine, app.state.sessions = database(url)
        yield
        engine.dispose()

    app = FastAPI(title='学生制片工作台', lifespan=lifespan)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'agent_configured': bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL'))}

    @app.get('/api/projects')
    def projects():
        with app.state.sessions() as s:
            return [{'id': p.id, 'name': p.name, 'revision': p.revision} for p in s.scalars(select(Project))]

    @app.post('/api/projects')
    def create(request: ProjectInput):
        with app.state.sessions() as s:
            p = Project(name=request.name)
            s.add(p)
            s.commit()
            return {'id': p.id, 'name': p.name, 'revision': p.revision}

    @app.get('/api/projects/{pid}')
    def detail(pid: str):
        with app.state.sessions() as s:
            return state(s, pid)

    @app.post('/api/projects/{pid}/changes')
    def draft(pid: str, request: ChangeInput):
        with app.state.sessions() as s:
            return propose(s, pid, request)

    @app.post('/api/projects/{pid}/changes/{cid}/confirm')
    def accept(pid: str, cid: str):
        with app.state.sessions() as s:
            return confirm(s, pid, cid)

    @app.post('/api/projects/{pid}/changes/{cid}/reject')
    def reject(pid: str, cid: str):
        with app.state.sessions() as s:
            c = s.get(Change, cid)
            if not c or c.project_id != pid:
                raise HTTPException(404, '草稿不存在')
            if c.status != 'pending':
                raise HTTPException(409, '草稿已处理')
            result = s.execute(update(Change).where(Change.id == cid, Change.project_id == pid,
                               Change.status == 'pending').values(status='rejected'))
            if result.rowcount != 1:
                s.rollback()
                raise HTTPException(409, '草稿已处理，请刷新')
            s.commit()
            return {'status': c.status}

    @app.get('/api/projects/{pid}/checks')
    def checks(pid: str):
        with app.state.sessions() as s:
            return state(s, pid)['checks']

    @app.get('/api/projects/{pid}/events')
    def events(pid: str):
        with app.state.sessions() as s:
            get_project(s, pid)
            return [{'id': e.id, 'type': e.type, 'data': e.data, 'created_at': e.created_at}
                    for e in sorted(rows(s, Event, pid), key=lambda e: e.created_at, reverse=True)[:100]]

    @app.post('/api/projects/{pid}/notices')
    def notice(pid: str, request: NoticeInput):
        with app.state.sessions() as s:
            return publish(s, pid, request)

    @app.get('/api/projects/{pid}/notices/{nid}/export')
    def export(pid: str, nid: str):
        with app.state.sessions() as s:
            n = s.get(Notice, nid)
            if not n or n.project_id != pid:
                raise HTTPException(404, '通告不存在')
            snap = n.snapshot
            lines = [f"{snap['project']} | {n.date} 通告 V{n.version}",
                     f'发布时间：{n.created_at}', f'计划版本：{n.revision}', '', snap['notes'], '']
            for r in snap['schedule']:
                d = r['data']
                lines.append(f"{d['start'] or '待定'} | {d['title']} | {d['minutes']}分钟 | {'、'.join(d['resources'])}\n{d['notes']}")
            return Response('\n'.join(lines), media_type='text/plain; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename="notice-{n.date}-v{n.version}.txt"'})

    @app.post('/api/projects/{pid}/scripts/parse')
    async def parse(pid: str, request: ScriptInput):
        with app.state.sessions() as s:
            get_project(s, pid)
            try:
                return await parse_script(s, pid, request)
            except RuntimeError as exc:
                raise HTTPException(503, str(exc)) from exc
            except HTTPException:
                raise
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('Script parsing failed')
                raise HTTPException(502, '剧本解析服务调用失败，请检查模型配置和网络') from exc

    @app.get('/api/projects/{pid}/scripts')
    def scripts(pid: str):
        with app.state.sessions() as s:
            get_project(s, pid)
            return [{'id': e.id, **e.data} for e in sorted(rows(s, Event, pid),
                key=lambda e: e.created_at, reverse=True) if e.type == 'script_parse'][:20]

    @app.post('/api/projects/{pid}/scripts/{eid}/draft')
    def import_script(pid: str, eid: str):
        with app.state.sessions() as s:
            return script_draft(s, pid, eid)

    @app.post('/api/projects/{pid}/impact')
    def impact(pid: str, request: ImpactInput):
        with app.state.sessions() as s:
            return analyze_impact(s, pid, request)

    @app.post('/api/projects/{pid}/agent')
    async def agent(pid: str, request: AgentInput):
        with app.state.sessions() as s:
            get_project(s, pid)
            try:
                return await run(s, pid, request)
            except RuntimeError as exc:
                raise HTTPException(503, str(exc)) from exc
            except HTTPException:
                raise
            except Exception as exc:
                import logging
                logging.getLogger(__name__).exception('Agent request failed')
                raise HTTPException(502, '模型调用失败，请检查服务地址、模型配置和网络；已生成草稿可刷新查看') from exc

    return app


app = create_app()
