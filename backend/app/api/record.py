"""历史记录路由：列表、详情、CSV导出、原图/结果图访问。

- 全部查询以当前登录用户user_id为过滤（属主隔离在DAO层生效）；
- 详情与图像访问对"记录不存在"与"非本人"区分错误码（40401/40301）；
- 图像访问按文件名反查记录归属，杜绝越权访问（spec.md第8章）。
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse

from ..core.config import CLASS_NAMES_ZH, RESULT_DIR, UPLOAD_DIR
from ..core.errors import CODE_FORBIDDEN, CODE_NOT_FOUND, CODE_PARAM, biz_error
from ..db.database import get_conn
from ..repositories import record_repo
from ..schemas.record import (RecordDetailResponse, RecordListItem,
                              RecordListResponse)
from .deps import get_current_user

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]
ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not _DATE_RE.match(value):
        raise biz_error(CODE_PARAM, f"参数{name}须为 YYYY-MM-DD 格式")
    return value


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _csv_safe(value: object) -> str:
    """CSV 公式注入防护：以公式前缀开头的字段前置单引号。"""
    s = "" if value is None else str(value)
    return "'" + s if s and s[0] in "=+-@\t\r" else s


@router.get("/record/list", response_model=RecordListResponse,
            summary="检测历史列表", tags=["record"])
def list_records(
    user: CurrentUser,
    conn: ConnDep,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=50, description="每页条数（1–50）"),
) -> RecordListResponse:
    """当前用户检测历史，按检测时间倒序分页。"""
    total, rows = record_repo.list_by_user(conn, user["id"], page, page_size)
    items = [
        RecordListItem(
            record_id=r["id"],
            image_name=r["image_name"],
            defect_summary=json.loads(r["defect_summary"] or "{}"),
            inference_time_ms=r["inference_time_ms"],
            model_version=r["model_version"],
            result_image_url=(f"/api/files/results/{_basename(r['result_image_path'])}"
                              if r["result_image_path"] else None),
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return RecordListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/record/export", summary="导出检测历史记录（CSV）", tags=["record"])
def export_records(
    user: CurrentUser,
    conn: ConnDep,
    start: str | None = Query(None, description="起始日期 YYYY-MM-DD，可选"),
    end: str | None = Query(None, description="结束日期 YYYY-MM-DD，可选"),
) -> StreamingResponse:
    """导出当前用户检测记录为CSV（utf-8-sig，Excel直接打开不乱码）。

    注意：本路由须先于 /record/{record_id} 注册，否则 "export" 会被解析为记录ID。
    """
    start = _check_date(start, "start")
    end = _check_date(end, "end")
    rows = record_repo.list_export_rows(conn, user["id"], start, end)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["记录ID", "检测时间", "文件名", *CLASS_NAMES_ZH,
                     "总目标数", "推理耗时ms", "模型版本", "原图路径", "结果图路径"])
    for r in rows:
        summary = json.loads(r["defect_summary"] or "{}")
        counts = [summary.get(name, 0) for name in CLASS_NAMES_ZH]
        targets = json.loads(r["detect_result"] or "{}").get("targets", [])
        writer.writerow([
            r["id"], _csv_safe(r["created_at"]), _csv_safe(r["image_name"]),
            *counts, len(targets),
            r["inference_time_ms"] if r["inference_time_ms"] is not None else "",
            _csv_safe(r["model_version"]), _csv_safe(r["image_path"]),
            _csv_safe(r["result_image_path"] or ""),
        ])

    today = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="detect_records_{today}.csv"'},
    )


@router.get("/record/{record_id}", response_model=RecordDetailResponse,
            summary="检测记录详情", tags=["record"])
def record_detail(user: CurrentUser, conn: ConnDep, record_id: int) -> RecordDetailResponse:
    """单条检测记录详情（含完整目标列表与原图地址）。"""
    row = record_repo.get_by_user_and_id(conn, user["id"], record_id)
    if row is None:
        if record_repo.get_by_id(conn, record_id) is None:
            raise biz_error(CODE_NOT_FOUND, "检测记录不存在")
        raise biz_error(CODE_FORBIDDEN, "无权访问该记录")
    detect_result = json.loads(row["detect_result"] or "{}")
    return RecordDetailResponse(
        record_id=row["id"],
        image_name=row["image_name"],
        defect_summary=json.loads(row["defect_summary"] or "{}"),
        inference_time_ms=row["inference_time_ms"],
        model_version=row["model_version"],
        result_image_url=(f"/api/files/results/{_basename(row['result_image_path'])}"
                          if row["result_image_path"] else None),
        created_at=row["created_at"],
        image_url=f"/api/files/uploads/{_basename(row['image_path'])}",
        targets=detect_result.get("targets", []),
        image_size=detect_result.get("image_size", {}),
    )


def _serve_image(user: dict, conn: sqlite3.Connection, kind: str, filename: str):
    """图像访问公共逻辑：文件名校验 → 反查归属（属主隔离）→ 返回文件。"""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise biz_error(CODE_NOT_FOUND, "图像不存在或无权访问")
    row = record_repo.find_by_image_filename(conn, user["id"], kind, filename)
    # 不存在或非本人统一返回404，避免文件名探测（不泄露他人资源是否存在）
    if row is None:
        raise biz_error(CODE_NOT_FOUND, "图像不存在或无权访问")
    base = UPLOAD_DIR if kind == "uploads" else RESULT_DIR
    rel = row["image_path"] if kind == "uploads" else row["result_image_path"]
    path = base / rel
    if not path.is_file():
        raise biz_error(CODE_NOT_FOUND, "图像文件已不存在")
    return FileResponse(path)


@router.get("/files/uploads/{filename}", summary="上传原图访问", tags=["files"])
def get_upload_image(user: CurrentUser, conn: ConnDep, filename: str) -> FileResponse:
    """访问本人检测记录的上传原图。"""
    return _serve_image(user, conn, "uploads", filename)


@router.get("/files/results/{filename}", summary="标注结果图访问", tags=["files"])
def get_result_image(user: CurrentUser, conn: ConnDep, filename: str) -> FileResponse:
    """访问本人检测记录的标注结果图。"""
    return _serve_image(user, conn, "results", filename)
