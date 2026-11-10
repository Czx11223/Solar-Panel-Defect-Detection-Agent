"""Agent API：智能体对话（SSE 流式）与会话管理。

- POST /api/agent/chat            SSE 流式对话（text/event-stream，
                                  绕过统一响应包装——中间件只包装 application/json）
- GET  /api/agent/sessions        会话列表
- GET  /api/agent/sessions/{id}/messages  会话消息历史
- DELETE /api/agent/sessions/{id} 删除会话（级联消息）
- GET  /api/agent/status          LLM 就绪状态（前端用于禁用入口/提示配置）

对话限流：按 user_id 滑动窗口（PV_AGENT_CHAT_RATE_LIMIT，默认 20 次/60s）。
SSE 生成器在响应开始后执行，其内部异常转为 error 事件而非 HTTP 错误；
HTTP 层错误（未登录/超限/会话不存在/未配置Key）仍是标准 {code,message,data} JSON。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent.llm_client import _ensure_ready
from ..agent.loop import run_agent_stream
from ..core.config import settings
from ..core.errors import CODE_NOT_FOUND, CODE_RATE_LIMIT, biz_error
from ..core.rate_limit import RateLimiter
from ..db import database as db_module
from ..db.database import get_conn
from ..repositories import agent_repo
from .deps import get_current_user

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]

_chat_limiter = RateLimiter(settings.agent_chat_rate_limit,
                            settings.rate_limit_window)


class ChatRequest(BaseModel):
    message: str = Field(description="用户消息", min_length=1, max_length=4000)
    session_id: int | None = Field(default=None, description="会话ID；缺省新建会话")


@router.post("/chat", summary="智能体对话（SSE 流式）", tags=["agent"])
def agent_chat(
    body: ChatRequest,
    user: CurrentUser,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> StreamingResponse:
    # HTTP 层校验：限流、Key、会话属主；错误以标准 JSON 返回（流开始前）
    if not _chat_limiter.check(f"user:{user['id']}"):
        raise biz_error(CODE_RATE_LIMIT,
                        f"对话过于频繁，每 {settings.rate_limit_window} 秒内最多 "
                        f"{settings.agent_chat_rate_limit} 次")
    _ensure_ready()

    if body.session_id is not None:
        row = agent_repo.get_session(conn, user["id"], body.session_id)
        if row is None:
            raise biz_error(CODE_NOT_FOUND, "会话不存在")
        session_id = int(row["id"])
    else:
        title = body.message.strip().replace("\n", " ")[:20] or "新会话"
        session_id = agent_repo.create_session(conn, user["id"], title)

    agent_repo.add_message(conn, session_id, role="user", content=body.message)

    return StreamingResponse(
        _chat_stream(user, session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chat_stream(user: dict, session_id: int):
    """独立数据库连接执行 Agent 循环（生成器生命周期长于请求依赖）。

    DB_PATH 经模块属性运行时读取，兼容测试环境的路径重定向。
    """
    conn = sqlite3.connect(db_module.DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield from run_agent_stream(conn, user, session_id)
    finally:
        conn.close()


@router.get("/sessions", summary="会话列表", tags=["agent"])
def list_sessions(
    user: CurrentUser,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> dict:
    rows = agent_repo.list_sessions(conn, user["id"])
    return {"sessions": [dict(r) for r in rows]}


@router.get("/sessions/{session_id}/messages", summary="会话消息历史", tags=["agent"])
def list_messages(
    session_id: int,
    user: CurrentUser,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> dict:
    if agent_repo.get_session(conn, user["id"], session_id) is None:
        raise biz_error(CODE_NOT_FOUND, "会话不存在")
    rows = agent_repo.get_messages(conn, session_id, 1000)
    return {"messages": [_message_view(r) for r in rows]}


@router.delete("/sessions/{session_id}", summary="删除会话", tags=["agent"])
def delete_session(
    session_id: int,
    user: CurrentUser,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> dict:
    if not agent_repo.delete_session(conn, user["id"], session_id):
        raise biz_error(CODE_NOT_FOUND, "会话不存在")
    return {"deleted": True}


class ToolInvokeRequest(BaseModel):
    arguments: dict = Field(default_factory=dict,
                            description="工具参数（JSON 对象，来自模型 tool_calls）")


@router.get("/tools", summary="工具清单（供前端 Agent 循环使用）", tags=["agent"])
def list_tools(_user: CurrentUser) -> dict:
    """返回全部工具的 OpenAI function calling 声明。

    前端把工具声明交给云端大模型，模型发起调用时再回打 /tools/{name} 执行，
    因此工具实现只保留在服务端一份，前端不需要复制 JSON Schema。
    """
    from ..agent.tools import to_openai_tools

    return {"tools": to_openai_tools()}


@router.post("/tools/{name}", summary="执行单个工具", tags=["agent"])
def invoke_tool(
    name: str,
    body: ToolInvokeRequest,
    user: CurrentUser,
    conn: Annotated[sqlite3.Connection, Depends(get_conn)],
) -> dict:
    """按名称执行工具，返回 {ok, data, error}；工具内部异常转成 ok=false 回灌模型。"""
    from ..agent.tools import execute

    return execute(conn, user, name, json.dumps(body.arguments, ensure_ascii=False))


@router.get("/status", summary="LLM 就绪状态", tags=["agent"])
def agent_status() -> dict:
    try:
        _ensure_ready()
        ready = True
        message = "ok"
    except Exception as e:  # noqa: BLE001
        ready = False
        message = str(e)
    return {
        "llm_ready": ready,
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "message": message,
    }


def _message_view(r: sqlite3.Row) -> dict:
    """消息 → 前端展示结构（含工具调用摘要与思维链）。"""
    return {
        "id": r["id"],
        "role": r["role"],
        "content": r["content"],
        "reasoning": r["reasoning"],
        "tool_calls": json.loads(r["tool_calls_json"]) if r["tool_calls_json"] else None,
        "tool_name": r["tool_name"],
        "created_at": r["created_at"],
    }
