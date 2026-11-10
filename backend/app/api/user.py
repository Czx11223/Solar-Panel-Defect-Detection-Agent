"""用户信息路由：个人信息查看/修改、修改密码。

- GET /api/user/profile：返回当前登录用户信息（不含密码哈希）；
- PUT /api/user/profile：修改昵称/邮箱（邮箱选填，改为他人在用返回40902）；
- PUT /api/user/password：校验原密码后更新（原密码错误返回40102）。
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from ..core.errors import (CODE_BAD_CRED, CODE_EMAIL_EXISTS, biz_error)
from ..core.security import hash_password, verify_password
from ..db.database import get_conn
from ..repositories import user_repo
from ..schemas.user import (PasswordUpdateRequest, ProfileResponse,
                            ProfileUpdateRequest)
from .deps import get_current_user

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]
ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]


def _to_profile(row: sqlite3.Row) -> ProfileResponse:
    return ProfileResponse(
        user_id=row["id"], username=row["username"], email=row["email"],
        nickname=row["nickname"], created_at=row["created_at"],
    )


@router.get("/profile", response_model=ProfileResponse,
            summary="查看个人信息", tags=["user"])
def get_profile(user: CurrentUser, conn: ConnDep) -> ProfileResponse:
    """返回当前登录用户信息。"""
    row = user_repo.get_by_id(conn, user["id"])
    return _to_profile(row)


@router.put("/profile", response_model=ProfileResponse,
            summary="修改个人信息", tags=["user"])
def update_profile(body: ProfileUpdateRequest, user: CurrentUser,
                   conn: ConnDep) -> ProfileResponse:
    """修改昵称与邮箱；body中未传的字段保持不变。"""
    row = user_repo.get_by_id(conn, user["id"])
    nickname = body.nickname if body.nickname is not None else row["nickname"]
    # email的"未传"与"传null清空"需区分：Pydantic模型无法区分二者时统一按未传处理
    if body.email is not None:
        other = user_repo.get_by_email(conn, body.email)
        if other is not None and other["id"] != user["id"]:
            raise biz_error(CODE_EMAIL_EXISTS, "邮箱已被使用")
        email = body.email
    else:
        email = row["email"]
    user_repo.update_profile(conn, user["id"], nickname, email)
    return _to_profile(user_repo.get_by_id(conn, user["id"]))


@router.put("/password", summary="修改密码", tags=["user"])
def update_password(body: PasswordUpdateRequest, user: CurrentUser,
                    conn: ConnDep) -> dict:
    """校验原密码后更新为新密码。"""
    row = user_repo.get_by_id(conn, user["id"])
    if not verify_password(body.old_password, row["password_hash"]):
        raise biz_error(CODE_BAD_CRED, "原密码错误")
    user_repo.update_password(conn, user["id"], hash_password(body.new_password))
    return {"message": "密码修改成功"}
