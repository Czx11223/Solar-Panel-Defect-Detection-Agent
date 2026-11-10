"""检测工具：detect_image——对已上传的巡检图像返回检测结果与运维建议。

数据来源为 detect_record 已入库的检测结果（不重复推理），
属主校验走 record_repo.get_by_user_and_id。
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ...core.errors import CODE_NOT_FOUND, biz_error
from ...repositories import record_repo
from ...services.advice import build_advice
from . import tool

_DETECT_SCHEMA = {
    "type": "object",
    "properties": {
        "record_id": {
            "type": "integer",
            "description": "检测记录ID（用户消息中的 record_id 或 #编号）",
        },
    },
    "required": ["record_id"],
    "additionalProperties": False,
}


@tool(
    "detect_image",
    "获取指定检测记录的图像缺陷检测结果：缺陷目标列表（类别/置信度/框位置）、"
    "缺陷汇总与运维建议。record_id 来自用户上传图像后返回的记录编号。",
    _DETECT_SCHEMA,
)
def detect_image(conn: sqlite3.Connection, user: dict, record_id: int) -> dict[str, Any]:
    row = record_repo.get_by_user_and_id(conn, user["id"], int(record_id))
    if row is None:
        raise biz_error(CODE_NOT_FOUND, f"记录 {record_id} 不存在（或非本人记录）")
    try:
        detect_result = json.loads(row["detect_result"])
        summary = json.loads(row["defect_summary"]) if row["defect_summary"] else {}
    except (ValueError, TypeError):
        return {"error": f"记录 {record_id} 的检测结果数据损坏"}
    targets = detect_result.get("targets", [])
    filename = row["result_image_path"].rsplit("/", 1)[-1] if row["result_image_path"] else None
    return {
        "record_id": row["id"],
        "image_name": row["image_name"],
        "created_at": row["created_at"],
        "model_version": row["model_version"],
        "inference_time_ms": row["inference_time_ms"],
        "image_size": detect_result.get("image_size"),
        "targets": targets,
        "defect_summary": summary,
        "advice": build_advice(targets),
        "result_image_url": f"/api/files/results/{filename}" if filename else None,
    }
