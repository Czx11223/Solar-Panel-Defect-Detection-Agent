"""认证模块请求/响应模型。

密码规则：8–64字符，须同时包含字母与数字（前后端一致的最终防线）。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{2,30}$")


class RegisterRequest(BaseModel):
    username: str = Field(description="用户名，2–30字符（字母/数字/下划线/中文/连字符）")
    password: str = Field(description="密码，8–64字符，须含字母与数字")
    email: EmailStr | None = Field(default=None, description="邮箱，选填（D8），填写时须唯一")
    nickname: str | None = Field(default=None, max_length=50, description="昵称，选填")

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("用户名须为2–30字符，仅限字母/数字/下划线/中文/连字符")
        return v

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if not (8 <= len(v) <= 64):
            raise ValueError("密码长度须为8–64字符")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密码须同时包含字母与数字")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CloudSessionRequest(BaseModel):
    """云端票据换取应用令牌的入参；票据也可只放在 X-PV-Ticket 头里。"""
    ticket: str | None = Field(default=None, description="云端签发的短期票据（base64url）")


class RegisterResponse(BaseModel):
    user_id: int
    username: str
