"""安全模块：密码加盐哈希与JWT签发校验。

关键设计（决策D26/D27）：
- 密码哈希：标准库hashlib.pbkdf2_hmac（SHA-256、600000次迭代、16字节随机盐），
  存储格式 "pbkdf2$<迭代次数>$<盐hex>$<哈希hex>"，自描述可升级；
  校验用hmac.compare_digest防时序攻击。零第三方依赖，规避passlib与bcrypt版本兼容问题。
- JWT：PyJWT，HS256；payload含sub(user_id)、exp(24h)、iat；
  密钥来自config（环境变量PV_SECRET_KEY，缺省仅限开发）。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings
from .errors import CODE_UNAUTH, biz_error


# ---------- 密码哈希（pbkdf2） ----------

def hash_password(password: str) -> str:
    """计算密码加盐哈希，返回自描述字符串 pbkdf2$iter$salt_hex$hash_hex。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, settings.password_iterations
    )
    return f"pbkdf2${settings.password_iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码与存储哈希是否匹配；格式非法时直接返回False。"""
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---------- JWT ----------

def create_access_token(user_id: int, token_version: int = 0) -> str:
    """签发访问令牌：sub=user_id、ver=密码版本、exp=过期时间。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    """解析令牌，返回 {user_id, ver}；无效/过期返回 None（由调用方转 401）。"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return {"user_id": int(payload["sub"]), "ver": int(payload.get("ver", 0))}
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def unauthorized(message: str = "未认证或登录已过期") -> BizError:
    """统一未认证异常。"""
    return biz_error(CODE_UNAUTH, message)
