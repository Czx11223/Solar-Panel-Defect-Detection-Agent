"""文件上传校验与图像解码。

校验链路（服务端为最终防线，前端校验仅作体验优化）：
1. 大小 ≤ 10MB（D2，config.upload_max_mb）；
2. 格式：扩展名 + 文件魔数双重校验（防伪造扩展名），仅支持 jpg/jpeg/png/bmp；
3. 解码：OpenCV实际解码失败视为非法图片。

图片全程内存处理（D29）：读取到bytes后在内存完成校验/解码/预处理/渲染，
不写任何临时文件。
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from fastapi import UploadFile
from PIL import Image

from ..core.config import settings
from ..core.errors import CODE_FORMAT, CODE_PARAM, CODE_SIZE, biz_error


def _detect_magic(data: bytes) -> str | None:
    """按文件魔数（文件头字节）识别真实格式，返回归一化扩展名。"""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"BM":
        return ".bmp"
    return None


def _safe_ext(filename: str | None) -> str:
    """取文件名后缀并归一化为带点小写（如 .jpg），与allowed_extensions/魔数一致。"""
    if not filename:
        return ""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem, _, ext = name.rpartition(".")
    return f".{ext.lower()}" if stem and ext else ""


def validate_dimensions(width: int, height: int) -> None:
    """校验像素总量，防「小文件 → 超大位图」的解压炸弹。"""
    if width <= 0 or height <= 0:
        raise biz_error(CODE_PARAM, "图片尺寸非法")
    if width * height > settings.upload_max_pixels:
        limit_mp = settings.upload_max_pixels // 1_000_000
        raise biz_error(CODE_PARAM, f"图片像素数超过上限 {limit_mp}MP，请压缩后重试")


def check_upload(file: UploadFile) -> bytes:
    """同步校验上传文件，返回原始字节（供线程池中的同步路由调用）。

    校验顺序：截断读取 + 大小 → 扩展名 → 魔数 → 解码前像素总量。
    读取上限为 max_bytes+1，超大上传不会把整个文件读进内存。
    """
    max_bytes = settings.upload_max_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise biz_error(CODE_SIZE, f"文件大小超过上限 {settings.upload_max_mb}MB")
    if not data:
        raise biz_error(CODE_PARAM, "上传文件为空")

    ext = _safe_ext(file.filename)
    if ext not in settings.allowed_extensions:
        raise biz_error(CODE_FORMAT, "仅支持 jpg/jpeg/png/bmp 格式图片")

    magic_ext = _detect_magic(data)
    if magic_ext is None:
        raise biz_error(CODE_FORMAT, "文件内容不是有效图片")
    if (ext == ".jpeg" and magic_ext != ".jpg") or (ext != ".jpeg" and magic_ext != ext):
        raise biz_error(CODE_FORMAT, "文件扩展名与内容不符")

    # Pillow 只读头部拿尺寸，不解码像素，避免先分配超大位图
    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
    except (OSError, ValueError, Image.DecompressionBombError):
        raise biz_error(CODE_PARAM, "图片解码失败，请更换图片重试")
    validate_dimensions(width, height)
    return data


def decode_image(data: bytes) -> np.ndarray:
    """内存解码为BGR图像；解码失败抛40001（非图片/损坏）。"""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise biz_error(CODE_PARAM, "图片解码失败，请更换图片重试")
    h, w = img.shape[:2]
    validate_dimensions(w, h)  # 二次兜底，防头部尺寸与解码结果不一致
    return img
