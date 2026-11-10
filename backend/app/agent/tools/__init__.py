"""工具注册表：Tool Calling 工具的声明、注册与安全执行。

设计要点：
- @tool 装饰器注册：name/description/parameters(JSON Schema) 与本地执行函数绑定；
- execute() 为唯一执行入口：白名单校验 → 参数解析 → 异常捕获 → 结构化结果，
  工具内部异常不中断 Agent 循环，错误信息回灌给模型自行处理；
- 属主隔离：执行函数统一接收 (conn, user) 上下文，SQL 过滤 user_id 由 DAO 保证，
  模型传入的任何 user_id 参数一律忽略（防越权）。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

from ...core.errors import CODE_PARAM, BizError, biz_error

# 工具结果回灌给模型时的文本长度上限（超出截断，防止上下文膨胀）
TOOL_RESULT_MAX_CHARS = 8000


class Tool:
    def __init__(self, name: str, description: str,
                 parameters: dict, func: Callable[..., Any]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, parameters: dict):
    """注册工具。parameters 为 JSON Schema（additionalProperties 必须 false）。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if name in _REGISTRY:
            raise RuntimeError(f"工具重复注册: {name}")
        _REGISTRY[name] = Tool(name, description, parameters, func)
        return func

    return decorator


def to_openai_tools() -> list[dict]:
    """全部工具的 OpenAI function calling 声明。"""
    return [t.to_openai_schema() for t in _REGISTRY.values()]


def get(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def execute(conn: sqlite3.Connection, user: dict, name: str,
            arguments_json: str) -> dict:
    """执行工具并返回统一结构 {ok, data, error}。

    任何异常（参数非法/业务错误/内部错误）都转为 ok=False 的结果回灌，
    不向模型抛出未处理异常。
    """
    t = _REGISTRY.get(name)
    if t is None:
        return {"ok": False, "data": None, "error": f"未知工具: {name}"}
    try:
        args = json.loads(arguments_json or "{}")
        if not isinstance(args, dict):
            raise ValueError("参数必须是 JSON 对象")
        # 模型不可伪造身份：强制覆盖 user_id
        args.pop("user_id", None)
        data = t.func(conn, user, **args)
        return {"ok": True, "data": data, "error": None}
    except BizError as e:
        return {"ok": False, "data": None, "error": e.message}
    except TypeError as e:
        return {"ok": False, "data": None,
                "error": f"参数不匹配: {e}; 期望参数: {list(t.parameters.get('properties', {}))}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "data": None, "error": f"工具执行失败: {e}"}


def clip_result_text(text: str) -> str:
    if len(text) <= TOOL_RESULT_MAX_CHARS:
        return text
    return text[:TOOL_RESULT_MAX_CHARS] + f"\n…（结果过长已截断，原长度 {len(text)} 字符）"


def result_to_message(result: dict) -> str:
    """工具结果 → 回灌给模型的 tool 消息文本。"""
    payload = {"ok": result["ok"]}
    if result["ok"]:
        payload["data"] = result["data"]
    else:
        payload["error"] = result["error"]
    return clip_result_text(json.dumps(payload, ensure_ascii=False, default=str))


def raise_bad_params(msg: str) -> None:
    raise biz_error(CODE_PARAM, msg)


# ---- 注册内置工具（import 即注册）----
from . import detect_tools, record_tools, kb_tools, vision_tools  # noqa: E402,F401
