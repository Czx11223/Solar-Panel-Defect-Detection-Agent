"""共享 FastAPI 依赖：身份认证。

三条身份通道，按代价从低到高依次尝试：
1. 应用自有 JWT（账号密码登录，HS256 + PV_SECRET_KEY）——本地验签，零网络开销；
2. 云端票据 `X-PV-Ticket`——云端数据库依据 `auth.uid()` 签发并签名，后端转交云端复核；
3. 云端 access token——直接拿用户令牌去云端做身份自省（最慢，作为兜底）。

令牌读取顺序：自定义头 `X-PV-Token` → 标准 `Authorization: Bearer`。
原因：发布平台的网关会用自己的会话凭据覆盖客户端传入的 Authorization，导致后端拿到
的不是用户令牌；自定义头不参与网关的凭据处理，可以稳定送达。令牌一律不进 URL。

三条通道最终都落到同一张 user 表（云端用户建成 `wb_<uid>`），属主隔离逻辑不变。
"""

from __future__ import annotations

import base64
import json
import sqlite3
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core import cloud_auth
from ..core.config import settings
from ..core.errors import CODE_UNAUTH, BizError, biz_error
from ..core.security import decode_token
from ..db.database import get_conn
from ..repositories import user_repo

_bearer = HTTPBearer(auto_error=False)

TOKEN_HEADER = "x-pv-token"
TICKET_HEADER = "x-pv-ticket"


def _read_token(
    request: Request, credentials: HTTPAuthorizationCredentials | None
) -> tuple[str, str]:
    """返回 (令牌, 来源)。自定义头优先，其次标准 Bearer。"""
    custom = (request.headers.get(TOKEN_HEADER) or "").strip()
    if custom:
        return custom, "x-pv-token"
    if credentials is None:
        return "", "none"
    return credentials.credentials.strip(), "authorization"


def _decode_segment(seg: str) -> dict:
    try:
        pad = "=" * (-len(seg) % 4)
        data = json.loads(base64.urlsafe_b64decode(seg + pad))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _digest(token: str, source: str) -> str:
    """令牌特征摘要：只描述形状与声明名，不含任何令牌内容或用户标识。"""
    parts = token.split(".")
    alg = "-"
    claims = ""
    if len(parts) == 3:
        head = _decode_segment(parts[0])
        body = _decode_segment(parts[1])
        alg = str(head.get("alg") or "-")
        names = sorted(k for k in body if k in (
            "sub", "uid", "email", "aud", "iss", "azp", "client_id", "scope",
            "exp", "iat", "role", "app_metadata", "user_metadata"))
        claims = f" claims={','.join(names)}"
    return f"来源={source} 长度={len(token)} 段={len(parts)} alg={alg}{claims}"


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> dict:
    """解析并校验身份凭据，返回当前用户信息（不含密码哈希）。"""
    token, source = _read_token(request, credentials)

    # 1) 应用 JWT：本地验签
    if token:
        payload = decode_token(token)
        if payload is not None:
            row = user_repo.get_by_id(conn, payload["user_id"])
            if row is None:
                raise biz_error(CODE_UNAUTH, "用户不存在或已注销")
            # 改密码后 token_version 递增，旧令牌立即失效
            if int(row["token_version"]) != payload["ver"]:
                raise biz_error(CODE_UNAUTH, "登录状态已失效，请重新登录")
            return _public(row)

    # 2) 云端票据：由云端数据库签发，后端只复核签名（不持有云端密钥）
    ticket = (request.headers.get(TICKET_HEADER) or "").strip()
    if ticket:
        identity = cloud_auth.resolve_ticket(ticket)
        if identity is not None:
            return _public(_bind_cloud_user(conn, identity))

    if not token:
        raise biz_error(CODE_UNAUTH, "缺少认证令牌")
    if source != "x-pv-token":
        # 标准 Authorization 在发布环境里会被网关替换成平台凭据（claims 只有 exp/iat/iss），
        # 拿它去自省必定失败还多打一次云端；前端始终走自定义头，这里直接判未认证。
        raise biz_error(CODE_UNAUTH, "缺少认证令牌")

    # 3) 云端 access token：直接自省（兼容无票据的旧会话）
    if not cloud_auth.enabled():
        raise biz_error(CODE_UNAUTH, "令牌无效或已过期")
    try:
        identity = cloud_auth.resolve(token)
    except BizError as exc:
        # 诊断模式：把令牌来源与形状附在提示后面，便于判断"头是否送达"，
        # 而不是只能看到一句笼统的登录失效。默认关闭。
        if settings.diag_enabled:
            raise BizError(exc.code, f"{exc.message} [{_digest(token, source)}]",
                           exc.status_code) from exc
        raise
    return _public(_bind_cloud_user(conn, identity))


def _bind_cloud_user(conn: sqlite3.Connection, identity: dict) -> sqlite3.Row:
    return user_repo.get_or_create_by_cloud(
        conn, identity["uid"], identity.get("name"), identity.get("email"))


def _public(row: sqlite3.Row) -> dict:
    user = dict(row)
    user.pop("password_hash", None)
    return user
