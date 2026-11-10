"""Agent 轻量回归：mock LLM 客户端（不依赖真实百炼 API）。

覆盖：SSE 事件序列、工具循环回灌、会话属主隔离、知识库工具、无 Key 降级。
运行：cd backend && python -m pytest tests_light/test_agent_light.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from .conftest import make_test_image, make_user


def _login(client, username: str) -> str:
    resp = client.post("/api/auth/login",
                       json={"username": username, "password": "Test1234!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _register(client, username: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Test1234!",
              "email": f"{username}@t.co"},
    )
    assert resp.status_code == 200, resp.text


def _detect_record(client, token: str) -> int:
    files = {"file": ("panel.jpg", make_test_image(), "image/jpeg")}
    resp = client.post("/api/detect/image",
                       headers={"Authorization": f"Bearer {token}"}, files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["record_id"]


# ---------- mock LLM chunk 构造 ----------

def _chunk(content=None, reasoning=None, tool_calls=None, finish=None, usage=None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning,
                            tool_calls=tool_calls)
    return SimpleNamespace(
        usage=SimpleNamespace(**usage) if usage else None,
        choices=[SimpleNamespace(finish_reason=finish, delta=delta)],
    )


def _tool_call_delta(index=0, call_id="call_1", name=None, args=None):
    return SimpleNamespace(
        index=index, id=call_id,
        function=SimpleNamespace(name=name, arguments=args),
    )


def _patch_llm(monkeypatch, rounds: list[list]):
    """把 loop.stream_chat 替换为按轮次返回预设 chunk 序列。"""
    from app.agent import loop as agent_loop
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "test-key", raising=False)
    it = iter(rounds)
    monkeypatch.setattr(agent_loop, "get_client", lambda: object())
    monkeypatch.setattr(agent_loop, "stream_chat",
                        lambda client, messages, tools=None: next(it))


def _parse_sse(text: str) -> list[dict]:
    events = []
    for frame in text.split("\n\n"):
        for line in frame.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


# ---------- 无 Key 降级 ----------

def test_agent_status_and_chat_without_key(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "", raising=False)
    _register(client, "agent_u1")
    resp = client.get("/api/agent/status",
                      headers={"Authorization": f"Bearer {_login(client, 'agent_u1')}"})
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["llm_ready"] is False and "PV_LLM_API_KEY" in body["message"]

    resp = client.post("/api/agent/chat", json={"message": "hi"},
                       headers={"Authorization": f"Bearer {_login(client, 'agent_u1')}"})
    assert resp.status_code == 503 and resp.json()["code"] == 50302


# ---------- 纯对话流式 ----------

def test_chat_pure_stream(client, monkeypatch):
    _patch_llm(monkeypatch, [
        [
            _chunk(reasoning="用户在打招呼"),
            _chunk(content="你好"),
            _chunk(content="，我是光伏检测助手。"),
            _chunk(finish="stop",
                   usage={"prompt_tokens": 100, "completion_tokens": 20}),
        ],
    ])
    _register(client, "agent_u2")
    token = _login(client, "agent_u2")
    resp = client.post("/api/agent/chat", json={"message": "你好"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "meta" and types[-1] == "done"
    assert "reasoning" in types and types.count("delta") == 2
    done = events[-1]
    assert done["usage"]["prompt_tokens"] == 100

    # 消息已落库：会话列表 1 条，消息历史含 user + assistant
    sessions = client.get("/api/agent/sessions",
                          headers={"Authorization": f"Bearer {token}"}).json()["data"]["sessions"]
    assert len(sessions) == 1 and sessions[0]["message_count"] == 2
    sid = sessions[0]["id"]
    msgs = client.get(f"/api/agent/sessions/{sid}/messages",
                      headers={"Authorization": f"Bearer {token}"}).json()["data"]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "你好，我是光伏检测助手。"
    assert msgs[1]["reasoning"] == "用户在打招呼"


# ---------- 工具循环 ----------

def test_chat_tool_loop_detect_image(client, monkeypatch):
    _register(client, "agent_u3")
    token = _login(client, "agent_u3")
    record_id = _detect_record(client, token)

    _patch_llm(monkeypatch, [
        [
            _chunk(tool_calls=[_tool_call_delta(name="detect_image", args='{"record_')]),
            _chunk(tool_calls=[_tool_call_delta(call_id="call_1", args='id": %d}' % record_id)]),
            _chunk(finish="tool_calls"),
        ],
        [
            _chunk(content="检测完成"),
            _chunk(finish="stop", usage={"prompt_tokens": 300, "completion_tokens": 10}),
        ],
    ])

    resp = client.post("/api/agent/chat", json={"message": f"看看 #{record_id}"},
                       headers={"Authorization": f"Bearer {token}"})
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    # 两轮工具事件 + 第二轮正文 + done
    assert types.count("tool_call") == 1 and types.count("tool_result") == 1
    tr = next(e for e in events if e["type"] == "tool_result")
    assert tr["ok"] is True and tr["name"] == "detect_image"
    # 分片 arguments 正确拼接（"{"record_" + 'id": N}'）
    call = next(e for e in events if e["type"] == "tool_call")
    assert json.loads(call["arguments"])["record_id"] == record_id
    assert types[-1] == "done"

    # tool 消息已落库且上下文包含结果
    msgs = client.get(f"/api/agent/sessions/{next(
        s['id'] for s in client.get('/api/agent/sessions',
        headers={'Authorization': f'Bearer {token}'}).json()['data']['sessions'])}/messages",
        headers={"Authorization": f"Bearer {token}"}).json()["data"]["messages"]
    roles = [m["role"] for m in msgs]
    assert "tool" in roles
    assistant = next(m for m in msgs if m["role"] == "assistant" and m["tool_calls"])
    assert assistant["tool_calls"][0]["function"]["name"] == "detect_image"


def test_chat_tool_error_roundtrip(client, monkeypatch):
    """工具失败时错误回灌、模型仍能作答（不中断循环）。"""
    _register(client, "agent_u4")
    token = _login(client, "agent_u4")
    _patch_llm(monkeypatch, [
        [
            _chunk(tool_calls=[_tool_call_delta(name="detect_image", args='{"record_id": 99999}')]),
            _chunk(finish="tool_calls"),
        ],
        [_chunk(content="该记录不存在"), _chunk(finish="stop")],
    ])
    resp = client.post("/api/agent/chat", json={"message": "查 99999"},
                       headers={"Authorization": f"Bearer {token}"})
    tr = next(e for e in _parse_sse(resp.text) if e["type"] == "tool_result")
    assert tr["ok"] is False and "不存在" in tr["error"]


# ---------- 会话管理与属主隔离 ----------

def test_session_isolation_and_delete(client, monkeypatch):
    _patch_llm(monkeypatch, [[
        _chunk(content="ok"), _chunk(finish="stop"),
    ]])
    _register(client, "agent_a")
    _register(client, "agent_b")
    ta, tb = _login(client, "agent_a"), _login(client, "agent_b")

    resp = client.post("/api/agent/chat", json={"message": "m1"},
                       headers={"Authorization": f"Bearer {ta}"})
    sid = next(e["session_id"] for e in _parse_sse(resp.text) if e["type"] == "meta")

    # 用户 B 访问 A 的会话 → 40401
    assert client.get(f"/api/agent/sessions/{sid}/messages",
                      headers={"Authorization": f"Bearer {tb}"}).status_code == 404
    assert client.get(f"/api/agent/sessions/{sid}/messages",
                      headers={"Authorization": f"Bearer {ta}"}).status_code == 200

    # 删除（B 删 A 的 → 404；A 自己删 → 成功且消息级联清空）
    assert client.delete(f"/api/agent/sessions/{sid}",
                         headers={"Authorization": f"Bearer {tb}"}).status_code == 404
    assert client.delete(f"/api/agent/sessions/{sid}",
                         headers={"Authorization": f"Bearer {ta}"}).status_code == 200
    assert client.get(f"/api/agent/sessions/{sid}/messages",
                      headers={"Authorization": f"Bearer {ta}"}).status_code == 404


# ---------- 知识库工具 ----------

def test_kb_tool_empty_and_hit(client, monkeypatch, _env):
    from app.agent import tools as T

    import sqlite3
    conn = sqlite3.connect(_env["db"])
    conn.row_factory = sqlite3.Row

    r = T.execute(conn, {"id": 1}, "search_knowledge", '{"query": "上传限制"}')
    assert r["ok"] and r["data"].get("empty") is True

    conn.execute(
        "INSERT INTO kb_chunk (source, heading, content, keywords) VALUES (?,?,?,?)",
        ("t.md", "上传限制", "# 上传限制\n\n上传图片上限 10MB，格式 jpg/png/bmp。",
         "上传 图片 上限 10mb 格式 jpg png bmp"),
    )
    conn.execute(
        "INSERT INTO kb_chunk (source, heading, content, keywords) VALUES (?,?,?,?)",
        ("t.md", "推理引擎", "# 推理引擎\n\nONNX 优先，pt 回退。",
         "onnx 推理 引擎 pt 回退"),
    )
    # BM25 的 IDF = ln((N-f+0.5)/(f+0.5))：N=2 时单文档词 IDF 恰为 0，
    # 必须补足语料量（≥6 篇）才能产生正得分，此为数学特性而非实现缺陷。
    for i in range(4):
        conn.execute(
            "INSERT INTO kb_chunk (source, heading, content, keywords) VALUES (?,?,?,?)",
            ("t.md", f"填充章节{i}", f"填充内容{i}。",
             f"填充 词汇{i} 光伏 组件 巡检 方案"),
        )
    conn.commit()
    # 行数变化触发索引重建
    r = T.execute(conn, {"id": 1}, "search_knowledge", '{"query": "上传图片大小"}')
    assert r["ok"] and not r["data"].get("empty")
    hits = r["data"]["results"]
    assert hits[0]["heading"] == "上传限制"
    conn.close()


# ---------- 云服务接入：工具清单与工具执行端点 ----------

def test_tool_endpoints_require_auth(client):
    assert client.get("/api/agent/tools").status_code == 401
    assert client.post("/api/agent/tools/get_statistics", json={"arguments": {}}).status_code == 401


def test_tool_listing_matches_registry(client):
    _register(client, "cloud_tool_user")
    token = _login(client, "cloud_tool_user")
    resp = client.get("/api/agent/tools", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    tools = resp.json()["data"]["tools"]
    names = {t["function"]["name"] for t in tools}
    assert {"detect_image", "list_records", "get_statistics",
            "search_knowledge", "interpret_image"} <= names
    for t in tools:
        assert t["type"] == "function"
        assert t["function"]["parameters"]["type"] == "object"


def test_tool_invoke_returns_ok_envelope(client):
    _register(client, "cloud_invoke_user")
    token = _login(client, "cloud_invoke_user")
    headers = {"Authorization": f"Bearer {token}"}
    _detect_record(client, token)

    resp = client.post("/api/agent/tools/get_statistics",
                       json={"arguments": {}}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["ok"] is True
    assert body["data"]["record_count"] >= 1

    # 未知工具：不抛 500，转成 ok=false 回灌模型
    bad = client.post("/api/agent/tools/not_a_tool",
                      json={"arguments": {}}, headers=headers)
    assert bad.status_code == 200
    assert bad.json()["data"]["ok"] is False


# ---------- 自定义令牌头（绕过网关对 Authorization 的干预） ----------

def test_custom_token_header_accepted(client):
    _register(client, "custom_hdr_user")
    token = _login(client, "custom_hdr_user")

    ok = client.get("/api/agent/tools", headers={"X-PV-Token": token})
    assert ok.status_code == 200

    # 自定义头优先：Authorization 放个无效值也不影响
    ok2 = client.get("/api/agent/tools",
                     headers={"X-PV-Token": token, "Authorization": "Bearer broken"})
    assert ok2.status_code == 200

    bad = client.get("/api/agent/tools", headers={"X-PV-Token": "not-a-token"})
    assert bad.status_code == 401


# ---------- 云端票据通道（后端不持有云端密钥） ----------

def test_ticket_header_authenticates(client, monkeypatch):
    from app.core import cloud_auth

    def fake_resolve(ticket: str):
        if ticket == "good-ticket":
            return {"uid": "cloud-77", "name": "云用户", "email": "c@example.com"}
        return None

    monkeypatch.setattr(cloud_auth, "resolve_ticket", fake_resolve)

    ok = client.get("/api/agent/tools", headers={"X-PV-Ticket": "good-ticket"})
    assert ok.status_code == 200

    bad = client.get("/api/agent/tools", headers={"X-PV-Ticket": "bad-ticket"})
    assert bad.status_code == 401


def test_ticket_not_sent_to_cloud_when_absent(client, monkeypatch):
    """没有票据时不应触发票据校验（避免每次请求白跑一趟云端）。"""
    from app.core import cloud_auth

    called = {"n": 0}

    def fake_resolve(ticket: str):
        called["n"] += 1
        return None

    monkeypatch.setattr(cloud_auth, "resolve_ticket", fake_resolve)
    resp = client.get("/api/agent/tools")
    assert resp.status_code == 401
    assert called["n"] == 0
