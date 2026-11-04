# 组装 FastAPI 应用、启动数据库迁移和后台解析任务，并注册统一异常边界。
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from backend.common.database.store import database, configured_url
from backend.common.errors import BusinessError
from backend.common.logging.config import configure_logging
from backend.common.logging.middleware import RequestLoggingMiddleware, capture_http_error
from backend.common.database.migrations.script_v1 import upgrade as upgrade_scripts
from backend.common.database.migrations.planning_v2 import upgrade as upgrade_planning
from backend.router.planning import router as planning_router
from backend.router.script import router as script_router
from backend.router.project import router as project_router
from backend.router.change import router as change_router
from backend.router.notice import router as notice_router
from backend.router.event import router as event_router
from backend.router.legacy_script import router as legacy_script_router
from backend.router.impact import router as impact_router
from backend.agent.router import router as agent_router
from backend.router.health import router as health_router
from backend.router.resource import router as resource_router
from backend.router.person import router as person_router
from backend.router.preparation import router as preparation_router
from backend.common.database.migrations.preparation_v3 import upgrade as upgrade_preparation
from backend.common.database.migrations.shooting_v4 import upgrade as upgrade_shooting
from backend.router.shooting import router as shooting_router

routers = (shooting_router, preparation_router, person_router, resource_router, planning_router, script_router, health_router, project_router, change_router, notice_router,
           event_router, legacy_script_router, impact_router, agent_router)


# 按可选 database_url 创建应用并返回 FastAPI；生命周期负责迁移、解析任务关闭和引擎释放。
def create_app(database_url=None):
    url = database_url or configured_url()
    # 启动时配置日志、连接和解析任务；退出时先等待任务关闭，再释放引擎。
    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        engine, app.state.sessions = database(url)
        try:
            upgrade_scripts(engine)
            upgrade_planning(engine)
            upgrade_preparation(engine)
            upgrade_shooting(engine)
            from backend.service.script.jobs import ParseJobs
            app.state.parse_jobs = ParseJobs(app.state.sessions)
            yield
        finally:
            if hasattr(app.state, "parse_jobs"):
                await app.state.parse_jobs.shutdown()
            engine.dispose()

    app = FastAPI(title='学生制片工作台', lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(StarletteHTTPException, capture_http_error)
    app.add_exception_handler(BusinessError, capture_http_error)
    for router in routers:
        app.include_router(router)

    return app


app = create_app()
