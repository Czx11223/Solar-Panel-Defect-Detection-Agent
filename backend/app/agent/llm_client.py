"""LLM 客户端封装：阿里云百炼 OpenAI 兼容模式。

- 端点/模型/推理强度全部环境变量化（见 core/config.py LLM 配置段）；
- 未配置 API Key 或未安装 openai SDK 时抛 50302，由全局异常处理器转 JSON 响应；
- 流式调用返回 chunk 迭代器，usage 通过 stream_options.include_usage 获取
  （百炼兼容模式支持；部分实现可能不回传 usage，按 0 处理）。
"""

from __future__ import annotations

from typing import Any, Iterator

from ..core.config import settings
from ..core.errors import CODE_LLM_UNAVAILABLE, biz_error


def _ensure_ready() -> None:
    """前置检查：API Key 已配置、openai SDK 已安装。"""
    if not settings.llm_api_key:
        raise biz_error(
            CODE_LLM_UNAVAILABLE,
            "大模型服务未配置：请设置环境变量 PV_LLM_API_KEY（或 DASHSCOPE_API_KEY）",
        )
    try:
        import openai  # noqa: F401
    except ImportError as e:
        raise biz_error(
            CODE_LLM_UNAVAILABLE,
            "服务端未安装 openai SDK（pip install -r requirements.txt）",
        ) from e


def get_client():
    """构建 OpenAI 兼容客户端（指向阿里云百炼）。"""
    _ensure_ready()
    from openai import OpenAI

    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=120.0,
        max_retries=1,
    )


def stream_chat(client, messages: list[dict], tools: list[dict] | None = None
                ) -> Iterator[Any]:
    """流式对话。tools 为 OpenAI function calling 声明列表（可空）。

    注意：K3.1 Pro 始终思考，reasoning_effort 经百炼兼容模式的
    chat.completions 请求体顶层字段传递（SDK 未知参数走 extra_body）。
    """
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "extra_body": {"reasoning_effort": settings.llm_reasoning_effort},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)
