"""Agent 执行循环：流式对话 + Tool Calling 多轮回灌。

事件协议（SSE data 载荷，逐条 yield dict，由路由层序列化）：
- meta        会话信息（session_id / model）
- reasoning   思维链增量（K3.1 Pro 始终思考）
- delta       正文增量
- tool_call   模型发起工具调用（name / arguments）
- tool_result 工具执行完成（name / ok / 预览）
- done        本轮回答完成（message_id / usage）
- error       流式过程中的错误（中断流）

集成要点（百炼/Moonshot 官方文档明确要求）：
多轮工具循环必须把 SDK 返回的完整 assistant message 原样回传
（含 reasoning_content 与 tool_calls），只复制 content 会破坏后续调用上下文。
每轮 assistant / tool 消息即时落库，断连后历史不丢。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Iterator

from ..core.config import settings
from ..repositories import agent_repo
from .llm_client import get_client, stream_chat
from .prompt import build_system_prompt
from .tools import execute, result_to_message, to_openai_tools

logger = logging.getLogger("pv.agent")

MAX_TOOL_RESULT_PREVIEW = 200  # tool_result 事件中给前端的预览长度


def _rebuild_history(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    rows = agent_repo.get_messages(conn, session_id, settings.agent_history_limit)
    for r in rows:
        role = r["role"]
        if role == "user":
            messages.append({"role": "user", "content": r["content"]})
        elif role == "assistant":
            m: dict[str, Any] = {"role": "assistant", "content": r["content"] or ""}
            # 完整回传：思维链与工具调用必须原样保留
            if r["reasoning"]:
                m["reasoning_content"] = r["reasoning"]
            if r["tool_calls_json"]:
                m["tool_calls"] = json.loads(r["tool_calls_json"])
            messages.append(m)
        elif role == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": r["tool_call_id"] or "",
                "content": r["content"],
            })
    return messages


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def run_agent_stream(conn: sqlite3.Connection, user: dict, session_id: int
                     ) -> Iterator[str]:
    """执行 Agent 循环，逐段产出 SSE 文本。调用方负责：登录校验、限流、
    会话属主校验、user 消息已入库。生成器内使用独立数据库连接。

    注意：生成器在响应开始后才执行，此处的 BizError 需转为 error 事件。
    """
    try:
        yield from _run(conn, user, session_id)
    except Exception as e:  # noqa: BLE001
        logger.exception("Agent 流式执行异常: session=%s", session_id)
        yield _sse({"type": "error", "code": 50000,
                    "message": f"智能体处理失败：{e}"})


def _run(conn: sqlite3.Connection, user: dict, session_id: int) -> Iterator[str]:
    client = get_client()
    tools = to_openai_tools()
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
    last_assistant_id: int | None = None

    yield _sse({"type": "meta", "session_id": session_id,
                "model": settings.llm_model})

    for _round in range(settings.agent_max_rounds):
        messages = _rebuild_history(conn, session_id)
        stream = stream_chat(client, messages, tools=tools)

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
        finish_reason = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

        for chunk in stream:
            if getattr(chunk, "usage", None):
                u = chunk.usage
                usage = {
                    "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                }
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning_parts.append(rc)
                yield _sse({"type": "reasoning", "content": rc})
            dc = getattr(delta, "content", None)
            if dc:
                content_parts.append(dc)
                yield _sse({"type": "delta", "content": dc})
            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = tc.index if tc.index is not None else 0
                acc = tool_calls_acc.setdefault(
                    idx, {"id": "", "type": "function",
                          "function": {"name": "", "arguments": ""}})
                if getattr(tc, "id", None):
                    acc["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if fn.name:
                        acc["function"]["name"] += fn.name
                    if fn.arguments:
                        acc["function"]["arguments"] += fn.arguments

        usage_total["prompt_tokens"] += usage["prompt_tokens"]
        usage_total["completion_tokens"] += usage["completion_tokens"]

        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts) or None
        tool_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)] \
            if tool_calls_acc else None

        # assistant 消息即时落库（含完整 tool_calls 与思维链）
        last_assistant_id = agent_repo.add_message(
            conn, session_id, role="assistant", content=content,
            reasoning=reasoning,
            tool_calls_json=json.dumps(tool_calls, ensure_ascii=False)
            if tool_calls else None,
            tokens_in=usage["prompt_tokens"],
            tokens_out=usage["completion_tokens"],
        )

        if finish_reason != "tool_calls" or not tool_calls:
            agent_repo.touch_session(conn, session_id)
            yield _sse({"type": "done", "message_id": last_assistant_id,
                        "rounds": _round + 1, "usage": usage_total})
            return

        # ---- 执行全部工具调用，结果逐条回灌 ----
        for tc in tool_calls:
            name = tc["function"]["name"]
            args_json = tc["function"]["arguments"] or "{}"
            yield _sse({"type": "tool_call", "name": name,
                        "arguments": args_json})
            result = execute(conn, user, name, args_json)
            preview = json.dumps(result.get("data"), ensure_ascii=False,
                                 default=str)[:MAX_TOOL_RESULT_PREVIEW]
            yield _sse({"type": "tool_result", "name": name, "ok": result["ok"],
                        "error": result["error"], "preview": preview})
            agent_repo.add_message(
                conn, session_id, role="tool",
                content=result_to_message(result),
                tool_call_id=tc["id"] or f"call_{name}",
                tool_name=name,
            )

        # 工具执行完继续下一轮（模型基于结果继续回答）

    # 达到最大轮次：追加提示并做一次无工具总结，避免无限循环
    agent_repo.add_message(
        conn, session_id, role="user",
        content="（系统提示：已达单次回答工具调用上限，请基于以上信息直接给出最终回答，"
                "不再调用工具。）",
    )
    messages = _rebuild_history(conn, session_id)
    stream = stream_chat(client, messages, tools=None)
    content_parts, usage = [], {"prompt_tokens": 0, "completion_tokens": 0}
    for chunk in stream:
        if getattr(chunk, "usage", None):
            u = chunk.usage
            usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                     "completion_tokens": getattr(u, "completion_tokens", 0) or 0}
        if not getattr(chunk, "choices", None):
            continue
        delta = getattr(chunk.choices[0], "delta", None)
        if delta is None:
            continue
        rc = getattr(delta, "reasoning_content", None)
        if rc:
            yield _sse({"type": "reasoning", "content": rc})
        if getattr(delta, "content", None):
            content_parts.append(delta.content)
            yield _sse({"type": "delta", "content": delta.content})
    usage_total["prompt_tokens"] += usage["prompt_tokens"]
    usage_total["completion_tokens"] += usage["completion_tokens"]
    last_assistant_id = agent_repo.add_message(
        conn, session_id, role="assistant", content="".join(content_parts),
        tokens_in=usage["prompt_tokens"], tokens_out=usage["completion_tokens"],
    )
    agent_repo.touch_session(conn, session_id)
    yield _sse({"type": "done", "message_id": last_assistant_id,
                "rounds": settings.agent_max_rounds + 1, "usage": usage_total})
