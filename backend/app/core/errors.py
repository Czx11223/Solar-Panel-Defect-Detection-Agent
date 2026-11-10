"""业务错误码与统一业务异常。

统一响应结构：{code, message, data}
- code=0 成功；非0为业务错误码（见下表）；
- 路由层不散落try/except，业务校验直接抛BizError，由main.py全局异常处理器转HTTP响应。
"""

from __future__ import annotations


class BizError(Exception):
    """业务异常：携带业务错误码、可读信息与HTTP状态码。

    status_code与code分离：status_code表达HTTP语义（400/401/403/404/409/503），
    code表达系统内业务编号，前端可据此做精确分支。
    """

    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ---- 业务错误码定义 ----
CODE_OK = 0
CODE_PARAM = 40001            # 参数校验失败（字段缺失/格式错误/图像解码失败）
CODE_SIZE = 40002             # 文件大小超限
CODE_FORMAT = 40003           # 文件格式不支持（扩展名或魔数不符）
CODE_UNAUTH = 40101           # 未认证（token缺失/无效/过期）
CODE_BAD_CRED = 40102         # 用户名或密码错误
CODE_FORBIDDEN = 40301        # 无权限（访问他人记录/图像）
CODE_NOT_FOUND = 40401        # 资源不存在
CODE_USER_EXISTS = 40901      # 用户名已存在
CODE_EMAIL_EXISTS = 40902     # 邮箱已存在
CODE_MODEL_UNAVAILABLE = 50301  # 模型服务未就绪
CODE_LLM_UNAVAILABLE = 50302    # 大模型服务未就绪（未配置 API Key 或调用失败）
CODE_RATE_LIMIT = 42901       # 请求过于频繁（登录/注册限流）
CODE_INTERNAL = 50000         # 服务器内部错误（未预期异常）

# 错误码 -> 默认HTTP状态码（业务未显式指定时使用）
DEFAULT_STATUS = {
    CODE_PARAM: 400,
    CODE_SIZE: 400,
    CODE_FORMAT: 400,
    CODE_UNAUTH: 401,
    CODE_BAD_CRED: 401,
    CODE_FORBIDDEN: 403,
    CODE_NOT_FOUND: 404,
    CODE_USER_EXISTS: 409,
    CODE_EMAIL_EXISTS: 409,
    CODE_MODEL_UNAVAILABLE: 503,
    CODE_LLM_UNAVAILABLE: 503,
    CODE_RATE_LIMIT: 429,
    CODE_INTERNAL: 500,
}


def biz_error(code: int, message: str) -> BizError:
    return BizError(code, message, DEFAULT_STATUS.get(code, 400))
