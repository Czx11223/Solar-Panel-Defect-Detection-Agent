"""记录与统计工具：list_records / get_statistics。

时间过滤在 SQL 完成，类别过滤在应用层完成（detect_result 为 JSON 文本，
跨 SQLite 版本保证行为一致；用户级记录量小，应用层过滤开销可忽略）。
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any

from ...repositories import record_repo
from . import tool

_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "start": {"type": "string", "description": "开始日期 YYYY-MM-DD（可选）"},
        "end": {"type": "string", "description": "结束日期 YYYY-MM-DD（可选）"},
        "class_name": {
            "type": "string",
            "description": "按缺陷类名过滤：积灰/鸟粪/电损伤/物理损伤/积雪（可选）",
        },
        "limit": {"type": "integer", "description": "返回条数上限，默认 10，最大 50"},
    },
    "additionalProperties": False,
}

_STATS_SCHEMA = {
    "type": "object",
    "properties": {
        "start": {"type": "string", "description": "开始日期 YYYY-MM-DD（可选）"},
        "end": {"type": "string", "description": "结束日期 YYYY-MM-DD（可选）"},
    },
    "additionalProperties": False,
}


def _parse_summary(row: sqlite3.Row) -> tuple[dict, dict]:
    try:
        detect_result = json.loads(row["detect_result"]) if row["detect_result"] else {}
        summary = json.loads(row["defect_summary"]) if row["defect_summary"] else {}
    except (ValueError, TypeError):
        detect_result, summary = {}, {}
    return detect_result, summary


@tool(
    "list_records",
    "查询当前用户的历史检测记录（含缺陷汇总），可按日期范围与缺陷类别过滤。",
    _RECORD_SCHEMA,
)
def list_records(conn: sqlite3.Connection, user: dict,
                 start: str | None = None, end: str | None = None,
                 class_name: str | None = None,
                 limit: int = 10) -> dict[str, Any]:
    limit = max(1, min(int(limit or 10), 50))
    rows = record_repo.list_export_rows(conn, user["id"], start, end)
    items: list[dict[str, Any]] = []
    for row in rows:
        _dr, summary = _parse_summary(row)
        if class_name and not summary.get(class_name):
            continue
        items.append({
            "record_id": row["id"],
            "image_name": row["image_name"],
            "created_at": row["created_at"],
            "defect_summary": summary,
            "model_version": row["model_version"],
            "inference_time_ms": row["inference_time_ms"],
        })
    return {"total_matched": len(items), "returned": items[:limit],
            "note": "按 created_at 倒序" if items else None}


@tool(
    "get_statistics",
    "聚合统计当前用户的检测记录：缺陷类别分布、按日期分布、检出率等。",
    _STATS_SCHEMA,
)
def get_statistics(conn: sqlite3.Connection, user: dict,
                   start: str | None = None, end: str | None = None
                   ) -> dict[str, Any]:
    rows = record_repo.list_export_rows(conn, user["id"], start, end)
    class_counts: dict[str, int] = defaultdict(int)
    date_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    record_count = len(rows)
    defect_record_count = 0
    for row in rows:
        _dr, summary = _parse_summary(row)
        if summary:
            defect_record_count += 1
        day = str(row["created_at"])[:10]
        for name, n in summary.items():
            class_counts[name] += int(n)
            date_counts[day][name] += int(n)
    by_date = [
        {"date": d, "total": sum(v.values()), "counts": dict(v)}
        for d, v in sorted(date_counts.items())
    ]
    return {
        "record_count": record_count,
        "defect_record_count": defect_record_count,
        "defect_record_ratio": round(defect_record_count / record_count, 4)
        if record_count else 0.0,
        "class_counts": dict(class_counts),
        "by_date": by_date[-30:],
    }
