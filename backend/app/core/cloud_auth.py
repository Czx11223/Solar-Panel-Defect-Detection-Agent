"""云服务身份校验：把 WorkBuddy Cloud Service 的 access token 换成应用内用户。

背景与边界
----------
前端用 `@tencent-ai/workbuddy-cloud-sdk` 完成登录（邮箱验证码等），拿到 access token；
后端不持有任何云端签密密钥，只按官方约定做"令牌自省"：
    GET {cloud_endpoint}/.cloud/auth/v1/user/me   Authorization: Bearer <token>
校验通过后把云端 uid 映射为应用内用户（username = wb_<uid>，首次访问自动建档），
这样检测记录、会话等既有数据模型完全不用改，权限仍由 user.id 做属主隔离。

设计要点
--------
- 结果按 token 做短 TTL 缓存，避免每张图/每条消息都打一次校验请求；
- 网络异常与 401 区分：前者报"认证服务不可用"，后者报"登录已过期"，
  避免把临时故障误判成登出；
- 只读 uid/name/email 三个展示字段，任何令牌原文都不写日志。
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .config import settings
from .errors import CODE_UNAUTH, biz_error

logger = logging.getLogger("pv.cloud_auth")

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()
_CACHE_MAX = 1000
_ME_PATH = "/.cloud/auth/v1/user/me"
# 数据面兜底：whoami() 在云端库里以 auth.uid() 返回当前身份（匿名时为 'anon'）。
# 走 PostgREST 的 RPC，与前端 SDK 访问数据库是同一条链路。
_RPC_PATH = "/.cloud/database/rest/rpc/whoami"
# 票据校验：前端从 issue_ticket() 拿到的短期票据，由本函数在云端复核签名。
_TICKET_PATH = "/.cloud/database/rest/rpc/verify_ticket"
# 与前端 SDK（createCloudFetch）一致：云端每个数据面请求都要求此头识别应用，
# 缺失时认证服务直接报 invalid_client，根本不会走到令牌校验。
_APP_KEY_HEADER = "x-wb-webapp-access-key"

_ID_KEYS = ("uid", "user_id", "userId", "id", "sub")
_NAME_KEYS = ("nickname", "name", "display_name", "displayName")
_EMAIL_KEYS = ("email",)
# 云端用户对象除 id 外通常还带这些字段；昵称/邮箱可能为空，靠它们确认"这就是用户对象"，
# 避免把 session、metadata 之类的兄弟节点误判成身份，也避免因缺昵称而解析失败。
_USERISH_KEYS = ("aud", "role", "created_at", "updated_at", "last_sign_in_at",
                 "user_metadata", "app_metadata", "identities", "phone")


def enabled() -> bool:
    return bool(settings.cloud_endpoint) and bool(settings.cloud_app_key) \
        and settings.cloud_auth_enabled


def _pick(node: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = node.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return v
    return None


def _find_identity(data: Any, depth: int = 0) -> dict[str, Any] | None:
    """在未知响应结构里定位用户对象（云端返回可能是 {data:{user:{...}}}）。"""
    if depth > 6:
        return None
    if isinstance(data, dict):
        uid = _pick(data, _ID_KEYS)
        if uid is not None and (
            _pick(data, _NAME_KEYS) is not None or _pick(data, _EMAIL_KEYS) is not None
            or "user" in data or any(k in data for k in _USERISH_KEYS)
        ):
            return {
                "uid": str(uid),
                "name": _pick(data, _NAME_KEYS),
                "email": _pick(data, _EMAIL_KEYS),
            }
        for key in ("data", "user", "result", "session"):
            if key in data:
                found = _find_identity(data[key], depth + 1)
                if found:
                    return found
        for value in data.values():
            if isinstance(value, (dict, list)):
                found = _find_identity(value, depth + 1)
                if found:
                    return found
    elif isinstance(data, list):
        for item in data:
            found = _find_identity(item, depth + 1)
            if found:
                return found
    return None


def _call_me(token: str) -> dict[str, Any]:
    url = f"{settings.cloud_endpoint}{_ME_PATH}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            _APP_KEY_HEADER: settings.cloud_app_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.cloud_auth_timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        if "invalid_client" in body or "invalid_grant" in body or e.code in (401, 403):
            # invalid_client = 应用凭据缺失/错误（部署配置问题），invalid_grant = 令牌本身失效
            if "invalid_client" in body:
                logger.error("云认证应用凭据被拒（检查 PV_CLOUD_APP_KEY）：%s", body[:200])
                raise biz_error(CODE_UNAUTH, "云服务认证配置错误，请联系管理员") from e
            raise biz_error(CODE_UNAUTH, "云服务登录态已失效，请重新登录") from e
        logger.warning("云认证校验失败 HTTP %s: %s", e.code, body[:200])
        raise biz_error(CODE_UNAUTH, "云服务认证暂不可用，请稍后重试") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("云认证请求异常: %s", e)
        raise biz_error(CODE_UNAUTH, "云服务认证暂不可用，请稍后重试") from e

    try:
        payload = json.loads(raw or "{}")
    except ValueError as e:
        raise biz_error(CODE_UNAUTH, "云服务认证响应异常") from e

    identity = _find_identity(payload)
    if not identity:
        # 只记字段名，不记取值：便于在不泄露用户信息的前提下排查响应结构变化
        keys = sorted(payload.keys())[:12] if isinstance(payload, dict) else type(payload).__name__
        logger.warning("云认证响应无法解析出身份，顶层字段=%s", keys)
        raise biz_error(CODE_UNAUTH, "云服务未返回有效身份")
    return identity


def _call_whoami(token: str) -> dict[str, Any] | None:
    """通过应用的 Auth 数据面校验令牌：调 PostgREST 的 whoami() RPC。

    官方约定的后端校验方式是"通过当前应用的 Auth 数据面"，而不是手写
    `/.cloud/auth/**` 请求；这条链路与前端 SDK 读写数据库完全相同，
    因此能通过 RLS 的令牌在这里同样有效。
    返回 {uid, name, email}；匿名（uid 为空或 anon）或请求失败时返回 None。
    """
    url = f"{settings.cloud_endpoint}{_RPC_PATH}"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            _APP_KEY_HEADER: settings.cloud_app_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.cloud_auth_timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        logger.info("数据面令牌校验未通过 HTTP %s", e.code)
        return None
    except Exception as e:  # noqa: BLE001  数据面异常不应打断主流程，交由调用方决定
        logger.warning("数据面令牌校验异常: %s", e)
        return None

    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    uid = str(payload.get("uid") or "").strip()
    if not uid or uid == "anon":
        return None
    return {
        "uid": uid,
        "name": (str(payload.get("name") or "").strip() or None),
        "email": (str(payload.get("email") or "").strip() or None),
    }


def resolve(token: str) -> dict[str, Any]:
    """校验云端 access token，返回 {uid, name, email}；失败抛 40101。

    主路径走应用自己的 Auth 数据面（whoami RPC）；数据面未通过时再请求
    auth 端点，用它返回的具体错误（invalid_client / invalid_grant）判断
    是部署配置问题还是登录态失效，给出更准确的提示。
    """
    if not enabled():
        raise biz_error(CODE_UNAUTH, "服务端未启用云服务登录")

    now = time.time()
    with _LOCK:
        hit = _CACHE.get(token)
        if hit and hit[0] > now:
            return hit[1]

    identity = _call_whoami(token)
    if identity is None:
        # 数据面未通过：用 auth 端点取具体原因（有则抛出对应提示）
        identity = _call_me(token)

    with _LOCK:
        if len(_CACHE) >= _CACHE_MAX:  # 简单容量保护：清掉过期项
            for k in [k for k, v in _CACHE.items() if v[0] <= now]:
                _CACHE.pop(k, None)
        _CACHE[token] = (now + settings.cloud_auth_ttl, identity)
    return identity


def _b64url_decode(value: str) -> bytes | None:
    try:
        pad = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + pad)
    except Exception:  # noqa: BLE001
        return None


def resolve_ticket(encoded: str) -> dict[str, Any] | None:
    """校验前端带来的云端票据，成功返回 {uid, name, email}，否则 None。

    票据由云端 `issue_ticket()` 依据 `auth.uid()` 生成并签名，后端只把它转交
    `verify_ticket()` 复核，因此后端不持有任何云端密钥，也不需要反向自省用户令牌。
    失败一律返回 None（由调用方决定报什么错），不抛异常。
    """
    if not enabled() or not encoded:
        return None
    raw = _b64url_decode(encoded.strip())
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    uid = str(data.get("uid") or "").strip()
    sig = str(data.get("sig") or "").strip()
    email = str(data.get("email") or "").strip()
    name = str(data.get("name") or "").strip()
    try:
        exp = int(data.get("exp") or 0)
    except (TypeError, ValueError):
        return None

    now = time.time()
    if not uid or not sig or exp <= now:
        return None

    cache_key = f"ticket::{uid}::{exp}::{sig[:16]}"
    with _LOCK:
        hit = _CACHE.get(cache_key)
        if hit and hit[0] > now:
            return hit[1]

    body = json.dumps({
        "p_uid": uid, "p_exp": exp, "p_email": email, "p_sig": sig,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.cloud_endpoint}{_TICKET_PATH}",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            _APP_KEY_HEADER: settings.cloud_app_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.cloud_auth_timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        logger.info("票据校验被云端拒绝 HTTP %s", e.code)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("票据校验请求异常: %s", e)
        return None

    if not isinstance(payload, dict) or str(payload.get("uid") or "") != uid:
        return None

    identity = {"uid": uid, "name": name or None, "email": email or None}
    with _LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            for k in [k for k, v in _CACHE.items() if v[0] <= now]:
                _CACHE.pop(k, None)
        _CACHE[cache_key] = (min(now + settings.cloud_auth_ttl, float(exp)), identity)
    return identity
