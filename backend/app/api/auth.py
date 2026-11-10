"""认证路由：注册、登录。

- POST /api/auth/register：用户名/密码/邮箱（选填）/昵称（选填）→ 创建用户；
  用户名与邮箱查重（40901/40902），密码仅存加盐哈希。
- POST /api/auth/login：校验凭据 → 签发JWT（24h，D27）。
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request

from ..core.config import settings
from ..core import cloud_auth
from ..core.errors import (CODE_BAD_CRED, CODE_EMAIL_EXISTS, CODE_FORBIDDEN,
                           CODE_RATE_LIMIT, CODE_UNAUTH, CODE_USER_EXISTS, biz_error)
from ..core.rate_limit import RateLimiter
from ..core.security import create_access_token, hash_password, verify_password
from ..db.database import get_conn
from ..repositories import user_repo
from ..schemas.auth import (CloudSessionRequest, LoginRequest, RegisterRequest,
                            RegisterResponse, TokenResponse)

router = APIRouter()

_login_limiter = RateLimiter(settings.login_rate_limit, settings.rate_limit_window)
_register_limiter = RateLimiter(settings.register_rate_limit, settings.rate_limit_window)
# 合法格式的固定哈希：用户不存在时也做一次 PBKDF2，抹平用户名枚举的时序差
_DUMMY_HASH = "pbkdf2$600000$" + "0" * 32 + "$" + "0" * 64


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=RegisterResponse,
             summary="用户注册", tags=["auth"])
def register(
    body: RegisterRequest,
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> RegisterResponse:
    """注册新用户。用户名唯一、邮箱选填且填写时须唯一；密码不落明文。"""
    if not settings.allow_register:
        raise biz_error(CODE_FORBIDDEN, "注册已关闭，请联系管理员开通账号")
    if not _register_limiter.check(f"reg:{_client_ip(request)}"):
        raise biz_error(CODE_RATE_LIMIT, "注册过于频繁，请稍后再试")
    username = body.username.strip()
    if user_repo.get_by_username(conn, username) is not None:
        raise biz_error(CODE_USER_EXISTS, "用户名已存在")
    if body.email and user_repo.get_by_email(conn, body.email) is not None:
        raise biz_error(CODE_EMAIL_EXISTS, "邮箱已被使用")
    user_id = user_repo.create_user(
        conn, username, hash_password(body.password),
        body.email, (body.nickname or "").strip() or None,
    )
    return RegisterResponse(user_id=user_id, username=username)


@router.post("/login", response_model=TokenResponse,
             summary="用户登录", tags=["auth"])
def login(
    body: LoginRequest,
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> TokenResponse:
    """校验用户名密码，成功返回 JWT 访问令牌（置于 Authorization: Bearer 头）。"""
    username = body.username.strip()
    if not _login_limiter.check(f"login:{_client_ip(request)}:{username}"):
        raise biz_error(CODE_RATE_LIMIT, "登录尝试过于频繁，请稍后再试")
    row = user_repo.get_by_username(conn, username)
    if row is None:
        verify_password(body.password, _DUMMY_HASH)  # 抹平「用户不存在」的时序差
        raise biz_error(CODE_BAD_CRED, "用户名或密码错误")
    if not verify_password(body.password, row["password_hash"]):
        raise biz_error(CODE_BAD_CRED, "用户名或密码错误")
    token = create_access_token(int(row["id"]), int(row["token_version"]))
    return TokenResponse(access_token=token,
                         expires_in=settings.token_expire_minutes * 60)


@router.post("/cloud-session", response_model=TokenResponse,
             summary="云端票据换取应用令牌", tags=["auth"])
def cloud_session(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
    body: Annotated[CloudSessionRequest | None, Body()] = None,
) -> TokenResponse:
    """云端登录后的一次性兑换：票据 → 应用 JWT。

    业务请求此后一律用应用 JWT 本地验签（24h），不再每次携带 15 分钟票据，
    避免票据过期或云端查询抖动把用户踢回登录页。票据从 X-PV-Ticket 头读取，
    兼容放在请求体的 ticket 字段。
    """
    ticket = (request.headers.get("x-pv-ticket") or (body.ticket if body else "") or "").strip()
    if not ticket:
        raise biz_error(CODE_UNAUTH, "缺少云端票据，请重新登录")
    identity = cloud_auth.resolve_ticket(ticket)
    if identity is None:
        raise biz_error(CODE_UNAUTH, "云端票据无效或已过期，请重新登录")
    row = user_repo.get_or_create_by_cloud(
        conn, identity["uid"], identity.get("name"), identity.get("email"))
    token = create_access_token(int(row["id"]), int(row["token_version"]))
    return TokenResponse(access_token=token,
                         expires_in=settings.token_expire_minutes * 60)
