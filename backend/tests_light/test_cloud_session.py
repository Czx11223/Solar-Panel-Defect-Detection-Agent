"""云端票据兑换应用令牌（POST /api/auth/cloud-session）的离线回归。

核心防回归点：
1. 有效票据 → 返回应用 JWT，且该 JWT 能直接通过受保护接口的本地验签；
2. 票据缺失/无效 → 40101（前端据此提示重新登录，而不是静默被踢）；
3. 同一云端 uid 重复兑换命中同一应用用户（不重复建档）。
"""

from __future__ import annotations

import pytest

from app.core import cloud_auth


def _fake_resolve(uid: str = "uid-abc", name: str = "云用户", email: str = "c@test.com"):
    def _inner(_ticket: str):
        return {"uid": uid, "name": name, "email": email}
    return _inner


@pytest.fixture()
def ticket_ok(monkeypatch):
    monkeypatch.setattr(cloud_auth, "resolve_ticket", _fake_resolve())


def test_cloud_session_issues_usable_app_token(client, ticket_ok):
    resp = client.post("/api/auth/cloud-session", json={"ticket": "dummy-ticket"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    assert token

    # 应用 JWT 走本地验签通道，后续业务请求不再依赖票据
    profile = client.get("/api/user/profile", headers={"X-PV-Token": token})
    assert profile.status_code == 200, profile.text
    assert profile.json()["data"]["username"].startswith("wb_uid-abc")


def test_cloud_session_reuses_same_user(client, ticket_ok):
    first = client.post("/api/auth/cloud-session", json={"ticket": "t1"}).json()["data"]
    second = client.post("/api/auth/cloud-session", json={"ticket": "t2"}).json()["data"]
    p1 = client.get("/api/user/profile", headers={"X-PV-Token": first["access_token"]})
    p2 = client.get("/api/user/profile", headers={"X-PV-Token": second["access_token"]})
    assert p1.json()["data"]["user_id"] == p2.json()["data"]["user_id"]


def test_cloud_session_rejects_missing_ticket(client, monkeypatch):
    monkeypatch.setattr(cloud_auth, "resolve_ticket", lambda _t: None)
    resp = client.post("/api/auth/cloud-session", json={})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


def test_cloud_session_rejects_invalid_ticket(client, monkeypatch):
    monkeypatch.setattr(cloud_auth, "resolve_ticket", lambda _t: None)
    resp = client.post("/api/auth/cloud-session", json={"ticket": "bad"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 40101
