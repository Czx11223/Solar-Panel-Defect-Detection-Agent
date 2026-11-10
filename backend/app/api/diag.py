"""鉴权链路诊断（仅 `PV_DIAG=1` 时挂载）。

用于排查"云端登录后被踢出"这类跨越网关 / 前后端的问题：返回本次请求实际到达
后端的令牌长度与哈希指纹（不返回令牌原文）、自定义头是否被保留、云端自省结果。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.request

from fastapi import APIRouter, Request

from ..core import cloud_auth
from ..core.config import settings
from ..core.security import create_access_token, decode_token
from ..db.database import DB_PATH

router = APIRouter()

TOKEN_HEADER = "x-pv-token"


def _fp(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""


@router.get("/auth", summary="鉴权链路诊断", tags=["diag"])
def auth_diag(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    custom = request.headers.get(TOKEN_HEADER, "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else auth.strip()
    token = custom.strip() or bearer

    out: dict = {
        "request_headers": sorted(k.lower() for k in request.headers.keys()),
        "authorization": {
            "present": bool(auth),
            "scheme": auth.split(" ", 1)[0] if auth else "",
            "len": len(bearer),
            "fp": _fp(bearer),
        },
        "x_pv_token": {"present": bool(custom), "len": len(custom), "fp": _fp(custom.strip())},
        "effective": {"source": "x-pv-token" if custom.strip() else ("authorization" if bearer else "none"),
                      "len": len(token), "fp": _fp(token)},
        "jwt_ok": bool(decode_token(token)) if token else False,
        "cloud": {
            "enabled": cloud_auth.enabled(),
            "endpoint": settings.cloud_endpoint,
            "app_key_len": len(settings.cloud_app_key),
        },
    }
    if token and not out["jwt_ok"]:
        try:
            ident = cloud_auth.resolve(token)
            out["introspect"] = {
                "ok": True,
                "uid_len": len(ident["uid"]),
                "has_name": bool(ident.get("name")),
                "has_email": bool(ident.get("email")),
            }
        except Exception as e:  # noqa: BLE001
            out["introspect"] = {"ok": False, "message": getattr(e, "message", str(e))}
    return out


@router.get("/selftest", summary="应用令牌链路自检", tags=["diag"])
def selftest() -> dict:
    """用服务端自签的应用 JWT 走一次真实 HTTP 回环，验证 X-PV-Token 通道。

    只探测本机端口，不发起任何外部请求；返回中不含令牌原文。
    """
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        row = conn.execute(
            "SELECT id, token_version FROM user ORDER BY id LIMIT 1").fetchone()
        conn.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "db", "error": str(e)}
    if not row:
        return {"ok": False, "stage": "db", "error": "user 表为空"}

    token = create_access_token(int(row[0]), int(row[1]))
    port = os.getenv("PORT") or os.getenv("PV_PORT") or "8000"
    url = f"http://127.0.0.1:{port}/api/user/profile"
    req = urllib.request.Request(url, headers={TOKEN_HEADER: token})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        return {"ok": body.get("code") == 0, "status": resp.status,
                "user_id": row[0], "code": body.get("code")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code,
                "body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "http", "error": str(e)}
