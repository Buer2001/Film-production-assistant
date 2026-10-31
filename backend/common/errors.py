class BusinessError(Exception):
    """业务失败信息；不依赖 FastAPI，由接口边界统一转换为响应。"""

    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
