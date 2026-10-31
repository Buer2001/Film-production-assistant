from time import perf_counter
from uuid import uuid4
from starlette.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
from backend.common.logging.context import request_id
from backend.common.logging.config import logger
from backend.common.errors import BusinessError


def error_fields(error):
    # 只记录异常类型和栈位置，不输出异常文本、SQL 参数或模型响应。
    trace, tb = [], error.__traceback__
    while tb:
        trace.append({'file': tb.tb_frame.f_code.co_filename, 'line': tb.tb_lineno,
                      'function': tb.tb_frame.f_code.co_name})
        tb = tb.tb_next
    return {'error_type': type(error).__name__, 'trace': trace}


async def capture_http_error(request, error):
    # HTTPException 会被框架转成响应；把原始异常留给外层中间件统一记录。
    original = error
    seen = set()
    while original.__cause__ is not None and id(original) not in seen:
        seen.add(id(original))
        original = original.__cause__
    request.scope['log_error'] = error_fields(original)
    if isinstance(error, BusinessError):
        return JSONResponse({'detail': error.detail}, status_code=error.status_code)
    return await http_exception_handler(request, error)


class RequestLoggingMiddleware:
    """ASGI 中间件统一记录请求结果，不读取请求体、查询参数或认证头。"""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        rid = uuid4().hex
        token = request_id.set(rid)
        start, status, started, failure = perf_counter(), 500, False, {}
        async def send_response(message):
            nonlocal status, started
            if message['type'] == 'http.response.start':
                status, started = message['status'], True
                headers = list(message.get('headers', []))
                headers.append((b'x-request-id', rid.encode('ascii')))
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception as error:
            failure = error_fields(error)
            if started:
                raise
            # 普通未处理异常在这里统一返回 500，仍带可检索的请求 ID。
            response = JSONResponse({'detail': '服务内部错误，请按请求 ID 查询日志',
                                     'request_id': rid}, status_code=500)
            await response(scope, receive, send_response)
        finally:
            failure = failure or scope.get('log_error', {})
            fields = {'method': scope['method'], 'path': scope['path'], 'status': status,
                      'duration_ms': round((perf_counter() - start) * 1000, 2), **failure}
            write = logger.error if failure or status >= 500 else logger.warning if status >= 400 else logger.info
            write('http.complete', extra=fields)
            request_id.reset(token)
