# 向路由提供请求级数据库会话，异常时回滚；业务服务负责提交。
from fastapi import Request


# 从 request 对应应用创建并 yield 数据库会话；异常回滚后重抛，退出上下文时关闭会话。
def get_session(request: Request):
    """接口层共用 Session 生命周期；提交仍由业务层决定。"""
    with request.app.state.sessions() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
