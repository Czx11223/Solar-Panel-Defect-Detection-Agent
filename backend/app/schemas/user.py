"""用户信息模块请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator

import re


class ProfileUpdateRequest(BaseModel):
    nickname: str | None = Field(default=None, max_length=50, description="昵称，不传则不修改")
    email: EmailStr | None = Field(default=None, description="邮箱，不传则不修改；传null清空")

    @field_validator("nickname")
    @classmethod
    def _check_nickname(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            raise ValueError("昵称不能为空字符串")
        return v


class PasswordUpdateRequest(BaseModel):
    old_password: str
    new_password: str = Field(description="新密码，8–64字符，须含字母与数字")

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        if not (8 <= len(v) <= 64):
            raise ValueError("密码长度须为8–64字符")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密码须同时包含字母与数字")
        return v


class ProfileResponse(BaseModel):
    user_id: int
    username: str
    email: str | None
    nickname: str | None
    created_at: str
