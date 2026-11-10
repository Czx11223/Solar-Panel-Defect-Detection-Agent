"""云服务令牌校验（app.core.cloud_auth）的离线回归。

不访问网络：用假的 urlopen 捕获请求头并返回构造的响应。

核心防回归点：
1. 校验走应用自己的 Auth 数据面（PostgREST `whoami` RPC），而不是手写 `/auth/**`；
2. 数据面未通过时再用 auth 端点取具体原因（invalid_client=配置错，invalid_grant=登录态失效）；
3. 两种请求都必须携带 `x-wb-webapp-access-key` 应用凭据头，缺失会让所有云登录用户被踢出；
4. 匿名身份（whoami 返回 'anon' / 空 uid）不能当成登录用户。
"""

from __future__ import annotations

import io
import json
import time
import urllib.error

import pytest

from app.core import cloud_auth
from app.core.config import settings

APP_KEY = "wbpk_test_key"


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Capture:
    """替身 urlopen：记录请求头，按脚本返回响应或 HTTPError。"""

    def __init__(self, responses):
        self.responses = responses
        self.calls: list[dict] = []

    def __call__(self, req, timeout=None):
        headers = {k.lower(): v for k, v in req.header_items()}
        self.calls.append({"url": req.full_url, "headers": headers})
        outcome = self.responses[len(self.calls) - 1]
        if isinstance(outcome, urllib.error.HTTPError):
            raise outcome
        return _FakeResponse(json.dumps(outcome).encode())


@pytest.fixture
def cloud_settings(monkeypatch):
    monkeypatch.setattr(settings, "cloud_endpoint", "https://cloud.example.com")
    monkeypatch.setattr(settings, "cloud_app_key", APP_KEY)
    monkeypatch.setattr(settings, "cloud_auth_enabled", True)
    monkeypatch.setattr(settings, "cloud_auth_timeout", 2.0)
    cloud_auth._CACHE.clear()
    return settings


def _whoami(uid: str, email: str = "", name: str = "") -> dict:
    """数据面 whoami() 的返回（jsonb）。"""
    return {"uid": uid, "email": email, "name": name}


def _anon() -> dict:
    return _whoami("anon")


def _identity_payload() -> dict:
    return {"data": {"user": {"uid": "u-123", "nickname": "测试", "email": "t@example.com"}}}


def _http_error(body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        cloud_auth._ME_PATH, 401, "Unauthorized", {},
        io.BytesIO(body.encode()))  # type: ignore[arg-type]


def test_resolve_uses_data_plane_first(cloud_settings, monkeypatch):
    """主路径是数据面 whoami RPC，且必须带应用凭据头与令牌。"""
    cap = _Capture([_whoami("u-123", "t@example.com", "测试")])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    identity = cloud_auth.resolve("some-cloud-token")

    assert identity["uid"] == "u-123"
    assert identity["email"] == "t@example.com"
    assert identity["name"] == "测试"
    call = cap.calls[0]
    assert call["url"] == "https://cloud.example.com" + cloud_auth._RPC_PATH
    assert call["headers"]["x-wb-webapp-access-key"] == APP_KEY
    assert call["headers"]["authorization"] == "Bearer some-cloud-token"


def test_resolve_requires_app_key(cloud_settings, monkeypatch):
    monkeypatch.setattr(settings, "cloud_app_key", "")
    assert cloud_auth.enabled() is False
    with pytest.raises(Exception, match="未启用"):
        cloud_auth.resolve("t")


def test_invalid_client_maps_to_config_error(cloud_settings, monkeypatch):
    """数据面未通过 + auth 端点报 invalid_client → 部署配置问题。"""
    cap = _Capture([_anon(), _http_error('{"error":"invalid_client"}')])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    with pytest.raises(Exception, match="配置错误"):
        cloud_auth.resolve("t")
    # 兜底请求同样要带应用凭据头
    assert cap.calls[1]["headers"]["x-wb-webapp-access-key"] == APP_KEY


def test_invalid_grant_maps_to_relogin(cloud_settings, monkeypatch):
    cap = _Capture([_anon(), _http_error('{"error":"invalid_grant"}')])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    with pytest.raises(Exception, match="重新登录"):
        cloud_auth.resolve("t")


def test_resolve_caches_by_token(cloud_settings, monkeypatch):
    cap = _Capture([_whoami("u-a"), _whoami("u-b")])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    cloud_auth.resolve("tok-a")
    cloud_auth.resolve("tok-a")  # 命中缓存，不再发请求
    cloud_auth.resolve("tok-b")  # 不同 token 必须重新校验

    assert len(cap.calls) == 2


def test_identity_without_name_or_email(cloud_settings, monkeypatch):
    """auth 端点返回的用户对象可能只有 id + aud（昵称为空），也要能解析出身份。"""
    payload = {"id": "u-9", "aud": "authenticated", "email": None}
    cap = _Capture([_anon(), payload])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    identity = cloud_auth.resolve("tok-notnamed")
    assert identity["uid"] == "u-9"
    assert identity["name"] is None


def test_identity_from_nested_session(cloud_settings, monkeypatch):
    """也覆盖 {session:{user:{...}}} 这类包装结构。"""
    payload = {"session": {"user": {"user_id": "u-7", "displayName": "巡检员"}}}
    cap = _Capture([_anon(), payload])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    identity = cloud_auth.resolve("tok-nested")
    assert identity["uid"] == "u-7"
    assert identity["name"] == "巡检员"


def test_anon_identity_is_rejected(cloud_settings, monkeypatch):
    """数据面返回匿名身份时不能被当成登录用户。"""
    cap = _Capture([_anon(), _http_error('{"error":"invalid_grant"}')])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    with pytest.raises(Exception, match="重新登录"):
        cloud_auth.resolve("tok-anon")


def test_empty_uid_is_rejected(cloud_settings, monkeypatch):
    cap = _Capture([_whoami(""), _http_error('{"error":"invalid_grant"}')])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    with pytest.raises(Exception, match="重新登录"):
        cloud_auth.resolve("tok-empty")


# ---------- 云端票据（issue_ticket / verify_ticket） ----------

def _ticket(uid="u-1", exp_offset=600, email="t@example.com", name="巡检员", sig="sig-ok") -> str:
    import base64
    payload = {"uid": uid, "exp": int(time.time()) + exp_offset,
               "email": email, "name": name, "sig": sig}
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_ticket_resolves_after_cloud_verification(cloud_settings, monkeypatch):
    cap = _Capture([{"uid": "u-1"}])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    identity = cloud_auth.resolve_ticket(_ticket())

    assert identity["uid"] == "u-1"
    assert identity["email"] == "t@example.com"
    assert identity["name"] == "巡检员"
    call = cap.calls[0]
    assert call["url"] == "https://cloud.example.com" + cloud_auth._TICKET_PATH
    assert call["headers"]["x-wb-webapp-access-key"] == APP_KEY
    # 票据校验走匿名数据面：不应带用户令牌
    assert "authorization" not in call["headers"]


def test_ticket_rejected_when_cloud_disagrees(cloud_settings, monkeypatch):
    cap = _Capture([_http_error('{"code":"DATABASE_28000"}')])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)
    assert cloud_auth.resolve_ticket(_ticket()) is None


def test_ticket_expired_is_rejected_locally(cloud_settings, monkeypatch):
    cap = _Capture([{"uid": "u-1"}])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)

    assert cloud_auth.resolve_ticket(_ticket(exp_offset=-10)) is None
    assert cap.calls == []  # 过期票据不必请求云端


def test_ticket_garbage_is_rejected(cloud_settings, monkeypatch):
    cap = _Capture([])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)
    assert cloud_auth.resolve_ticket("not-a-ticket") is None
    assert cloud_auth.resolve_ticket("") is None
    assert cap.calls == []


def test_ticket_uid_mismatch_is_rejected(cloud_settings, monkeypatch):
    """云端复核返回的 uid 与票据声明不一致时不能采信。"""
    cap = _Capture([{"uid": "someone-else"}])
    monkeypatch.setattr(cloud_auth.urllib.request, "urlopen", cap)
    assert cloud_auth.resolve_ticket(_ticket()) is None
