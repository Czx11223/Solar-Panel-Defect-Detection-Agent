"""检测路由：POST /api/detect/image。

流程编排：上传校验（格式/大小/魔数）→ 内存解码 → 推理（计时）→
运维建议 → 标注图渲染（base64）→ 原图/结果图持久化 → 检测记录入库 → 统一返回。

图片全程内存处理（D29）：解码、预处理、推理、渲染均在内存完成；
原图按原始字节、结果图按JPEG写入 storage/（按日期子目录），供历史记录展示。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from ..core.config import RESULT_DIR, UPLOAD_DIR
from ..core.errors import CODE_INTERNAL, CODE_MODEL_UNAVAILABLE, biz_error
from ..db.database import get_conn
from ..repositories import record_repo
from ..schemas.detect import DetectResponse
from ..services.advice import build_advice
from ..services.inference import BaseEngine
from ..services.render import draw_detections, encode_result_jpeg, to_base64_jpeg
from ..services.upload_check import check_upload, decode_image
from .deps import get_current_user

logger = logging.getLogger("pv.detect")
router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]
ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]


def get_engine(request: Request) -> BaseEngine:
    """从应用状态取推理引擎；模型未加载时返回50301。"""
    engine = getattr(request.app.state, "engine", None)
    if engine is None or not engine.available:
        raise biz_error(CODE_MODEL_UNAVAILABLE, "模型服务未就绪，请稍后重试")
    return engine


def _sanitize_filename(name: str) -> str:
    """清洗原始文件名：去除路径分隔符与危险字符，保留安全字符集。"""
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r"[^\w\u4e00-\u9fa5.-]", "_", name)
    return name or "image"


@router.post("/detect/image", response_model=DetectResponse,
             summary="上传图片执行缺陷检测", tags=["detect"])
def detect_image(
    user: CurrentUser,
    request: Request,
    conn: ConnDep,
    file: UploadFile = File(..., description="图片文件（jpg/jpeg/png/bmp，≤10MB）"),
) -> DetectResponse:
    """同步路由：FastAPI 自动调度到线程池，避免 CPU 推理阻塞事件循环。"""
    engine = get_engine(request)

    # ---- 1. 上传校验 + 内存解码 ----
    data = check_upload(file)
    img_bgr = decode_image(data)
    h, w = img_bgr.shape[:2]

    # ---- 2. 推理（计时含引擎内部预处理，不含网络传输与渲染）----
    targets, elapsed_ms = engine.infer(img_bgr)

    # ---- 3. 运维建议（置信度三档分级，D28）----
    advice = build_advice(targets)

    # ---- 4. 标注图渲染（内存）→ 单次 JPEG 编码，落盘与 base64 复用 ----
    rendered = draw_detections(img_bgr, targets)
    jpeg_bytes = encode_result_jpeg(rendered)
    rendered_b64 = to_base64_jpeg(jpeg_bytes)

    # ---- 5. 持久化：原图原始字节 + 结果图JPEG（按日期子目录）----
    date_dir = datetime.now().strftime("%Y%m%d")
    ts = datetime.now().strftime("%H%M%S")
    uid = uuid.uuid4().hex[:8]
    orig_name = _sanitize_filename(file.filename or "image")
    rel_upload = f"{date_dir}/f{ts}_{uid}_{orig_name}"
    rel_result = f"{date_dir}/r{ts}_{uid}.jpg"

    (UPLOAD_DIR / date_dir).mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / date_dir).mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / rel_upload).write_bytes(data)
    (RESULT_DIR / rel_result).write_bytes(jpeg_bytes)

    # ---- 6. 检测记录入库 ----
    defect_summary: dict[str, int] = {}
    for t in targets:
        if t["class_id"] != 0:  # 清洁类不计入缺陷汇总
            defect_summary[t["class_name"]] = defect_summary.get(t["class_name"], 0) + 1
    detect_result = {"image_size": {"width": w, "height": h}, "targets": targets}

    try:
        record_id = record_repo.create_record(
            conn, user_id=user["id"], image_name=orig_name,
            image_path=rel_upload, result_image_path=rel_result,
            detect_result=json.dumps(detect_result, ensure_ascii=False),
            defect_summary=json.dumps(defect_summary, ensure_ascii=False),
            inference_time_ms=round(elapsed_ms, 2),
            model_version=engine.model_version,
        )
    except Exception as e:  # 入库失败时清理已落盘文件，避免孤儿图像
        logger.error("检测记录入库失败：%s", e)
        (UPLOAD_DIR / rel_upload).unlink(missing_ok=True)
        (RESULT_DIR / rel_result).unlink(missing_ok=True)
        raise biz_error(CODE_INTERNAL, "检测记录保存失败，请重试") from e

    return DetectResponse(
        record_id=record_id,
        model_version=engine.model_version,
        inference_time_ms=round(elapsed_ms, 2),
        image_size={"width": w, "height": h},
        targets=targets,
        defect_summary=defect_summary,
        advice=advice,
        rendered_image_base64=rendered_b64,
        result_image_url=f"/api/files/results/{rel_result.rsplit('/', 1)[-1]}",
    )
