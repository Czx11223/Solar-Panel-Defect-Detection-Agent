"""detect_record表数据访问层（DAO，原生sqlite3）。

查询均以user_id为过滤条件，属主隔离在DAO层即生效；
detect_result与defect_summary以JSON字符串存取，应用层负责序列化/反序列化。
"""

from __future__ import annotations

import sqlite3
from typing import Any


def create_record(conn: sqlite3.Connection, *, user_id: int, image_name: str,
                  image_path: str, result_image_path: str, detect_result: str,
                  defect_summary: str, inference_time_ms: float | None,
                  model_version: str) -> int:
    cur = conn.execute(
        """INSERT INTO detect_record
           (user_id, image_name, image_path, result_image_path, detect_result,
            defect_summary, inference_time_ms, model_version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, image_name, image_path, result_image_path, detect_result,
         defect_summary, inference_time_ms, model_version),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_by_user(conn: sqlite3.Connection, user_id: int, page: int, page_size: int
                 ) -> tuple[int, list[sqlite3.Row]]:
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM detect_record WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    rows = conn.execute(
        """SELECT id, image_name, defect_summary, inference_time_ms, model_version,
                  result_image_path, created_at
           FROM detect_record WHERE user_id = ?
           ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
        (user_id, page_size, (page - 1) * page_size),
    ).fetchall()
    return int(total), rows


def get_by_id(conn: sqlite3.Connection, record_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM detect_record WHERE id = ?", (record_id,)
    ).fetchone()


def get_by_user_and_id(conn: sqlite3.Connection, user_id: int, record_id: int
                       ) -> sqlite3.Row | None:
    """属主查询：记录存在但非本人返回None，由路由层区分404/403。"""
    return conn.execute(
        "SELECT * FROM detect_record WHERE id = ? AND user_id = ?", (record_id, user_id)
    ).fetchone()


def list_export_rows(conn: sqlite3.Connection, user_id: int,
                     start: str | None, end: str | None) -> list[sqlite3.Row]:
    sql = """SELECT id, created_at, image_name, image_path, result_image_path,
                    detect_result, defect_summary, inference_time_ms, model_version
             FROM detect_record WHERE user_id = ?"""
    params: list[Any] = [user_id]
    # created_at为文本时间串（YYYY-MM-DD HH:MM:SS），日期范围用前缀匹配
    if start:
        sql += " AND created_at >= ?"
        params.append(start + " 00:00:00")
    if end:
        sql += " AND created_at <= ?"
        params.append(end + " 23:59:59")
    sql += " ORDER BY created_at DESC, id DESC"
    return conn.execute(sql, params).fetchall()


def find_by_image_filename(conn: sqlite3.Connection, user_id: int, kind: str,
                           filename: str) -> sqlite3.Row | None:
    """按图像文件名反查记录（图像访问属主校验用）。

    kind取值 "uploads"（原图）或 "results"（结果图）；匹配对应路径列以 filename 结尾。
    """
    col = "image_path" if kind == "uploads" else "result_image_path"
    # 转义 LIKE 通配符，避免文件名中的 % / _ 匹配到非目标记录
    escaped = filename.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return conn.execute(
        f"SELECT * FROM detect_record WHERE user_id = ? AND {col} LIKE ? ESCAPE '\\'",
        (user_id, "%/" + escaped),
    ).fetchone()
