"""视觉工具：interpret_image——调用 Kimi 原生视觉能力解读检测结果图。

与 Agent 主循环的区别：工具内部做一次【非流式】LLM 调用（vision 模式），
把标注结果图作为 image_url 输入，返回自然语言解读文本；
主循环拿到该文本后可继续综合其他工具结果作答。
"""

from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from typing import Any

from ...core import config as pv_config
from ...core.config import settings
from ...core.errors import CODE_LLM_UNAVAILABLE, CODE_NOT_FOUND, biz_error
from ...repositories import record_repo
from . import tool

_VISION_PROMPT = (
    "你是光伏电站巡检助手。请解读这张光伏面板缺陷检测结果图："
    "1. 描述图上可见的面板状态与标注框位置；"
    "2. 指出可疑区域的形态特征（如积灰分布、鸟粪附着、裂纹走向等，仅基于可见内容描述）；"
    "3. 提醒：这是 AI 辅助标注结果，置信度不等于缺陷确诊，重大缺陷须人工复核。"
    "回答使用简体中文，不超过 300 字。"
)


def _encode_image(path: Path) -> str:
    if not path.is_file():
        raise biz_error(CODE_NOT_FOUND, f"结果图文件缺失: {path.name}")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


@tool(
    "interpret_image",
    "用视觉模型解读指定检测记录的标注结果图（描述可见内容与可疑区域形态特征）。"
    "需要先有 record_id。",
    {
        "type": "object",
        "properties": {
            "record_id": {
                "type": "integer",
                "description": "检测记录ID",
            },
        },
        "required": ["record_id"],
        "additionalProperties": False,
    },
)
def interpret_image(conn: sqlite3.Connection, user: dict, record_id: int
                    ) -> dict[str, Any]:
    row = record_repo.get_by_user_and_id(conn, user["id"], int(record_id))
    if row is None:
        raise biz_error(CODE_NOT_FOUND, f"记录 {record_id} 不存在（或非本人记录）")
    rel = row["result_image_path"]
    if not rel:
        raise biz_error(CODE_NOT_FOUND, f"记录 {record_id} 没有结果图")

    data_url = _encode_image(pv_config.RESULT_DIR / rel)

    # 前置检查（Key/SDK）再调用
    from ..llm_client import get_client

    client = get_client()
    try:
        completion = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
            extra_body={"reasoning_effort": "low"},
        )
    except Exception as e:  # noqa: BLE001
        raise biz_error(CODE_LLM_UNAVAILABLE, f"视觉模型调用失败：{e}") from e

    text = (completion.choices[0].message.content or "").strip()
    return {
        "record_id": row["id"],
        "image_name": row["image_name"],
        "interpretation": text,
        "note": "解读基于标注图可见内容，须结合结构化检测结果综合判断",
    }
