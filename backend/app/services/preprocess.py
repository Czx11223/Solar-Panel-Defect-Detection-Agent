"""图像预处理：letterbox等比缩放、RGB转换、归一化。

与算法训练侧（ultralytics）预处理口径保持一致：
- letterbox：保持宽高比缩放至 imgsz×imgsz，短边以114灰边填充，
  填充量按stride=32对齐（与训练一致，避免推理分布偏移）；
- 归一化：像素值 /255 至0–1，float32，NCHW排列（ONNX输入要求）。

pt引擎（ultralytics YOLO.predict）内部自带letterbox与归一化，直接传BGR原图即可；
本模块的letterbox/prepare_onnx_input仅供ONNX引擎使用。
"""

from __future__ import annotations

import cv2
import numpy as np

from ..core.config import settings


def letterbox(img: np.ndarray, new_shape: int = 640,
              color: tuple = (114, 114, 114)) -> tuple[np.ndarray, float, tuple]:
    """等比缩放+灰边填充至固定 new_shape×new_shape 方形。

    ONNX导出模型输入为固定方形（export dynamic=False），预处理必须输出
    imgsz×imgsz；此处不使用ultralytics auto模式的stride对齐矩形
    （该模式输出如640×480，与固定ONNX输入不匹配）。

    返回：(填充后图像, 缩放比例ratio, (填充量dw, dh))
    - dw/dh为letterbox坐标系相对原图坐标的偏移，坐标映射回原图时使用；
    - ratio = 缩放比例（新图/原图），还原时坐标除以ratio。
    """
    shape = img.shape[:2]  # (h, w)
    r = min(new_shape / shape[0], new_shape / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))  # (w, h)
    dw = (new_shape - new_unpad[0]) / 2
    dh = (new_shape - new_unpad[1]) / 2

    resized = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                cv2.BORDER_CONSTANT, value=color)
    return padded, r, (dw, dh)


def prepare_onnx_input(img_bgr: np.ndarray) -> tuple[np.ndarray, dict]:
    """BGR原图 → ONNX输入张量。

    返回：(blob[NCHW float32 0–1], meta)
    meta = {"ratio": 缩放比例, "pad": (dw, dh), "orig": (h, w)}
    """
    padded, ratio, pad = letterbox(img_bgr, settings.imgsz)
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    blob = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))[None]
    meta = {"ratio": ratio, "pad": pad, "orig": img_bgr.shape[:2]}
    return blob, meta
