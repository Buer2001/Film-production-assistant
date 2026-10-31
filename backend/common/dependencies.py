from fastapi import Request


def get_session(request: Request):
    """接口层共用 Session 生命周期；提交仍由业务层决定。"""
    with request.app.state.sessions() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
