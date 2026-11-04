# 定义不依赖 Web 框架的业务异常，携带接口边界需要的状态码和详情。
# 携带 status_code/detail 的业务失败，接口边界负责转换响应。
class BusinessError(Exception):
    """业务失败信息；不依赖 FastAPI，由接口边界统一转换为响应。"""

    # 用 status_code 和 detail 初始化业务异常，供接口边界转换响应；不依赖 FastAPI。
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
