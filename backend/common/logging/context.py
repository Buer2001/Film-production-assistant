from contextvars import ContextVar

# 每个请求独立上下文；同步路由的线程池调用也会继承请求 ID。
request_id = ContextVar('film_request_id', default='-')
