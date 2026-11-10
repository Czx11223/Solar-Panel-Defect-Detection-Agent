"""标注结果图渲染：绘制检测框、类别与置信度标签，并编码为base64。

渲染在内存完成（D29）：OpenCV直接绘制到原图副本，imencode编码JPEG后
base64返回，不写临时文件。检测框颜色与algorithm侧可视化一致（BOX_COLORS_BGR）。
"""

from __future__ import annotations

import base64

import cv2
import numpy as np

from ..core.pv_classes import BOX_COLORS_BGR

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_detections(img_bgr: np.ndarray, targets: list[dict]) -> np.ndarray:
    """在原图副本上绘制检测框与"类别 置信度"标签，返回标注图。"""
    out = img_bgr.copy()
    for t in targets:
        class_id = t["class_id"]
        x1, y1, x2, y2 = (int(v) for v in t["bbox"])
        color = BOX_COLORS_BGR[class_id] if class_id < len(BOX_COLORS_BGR) else (0, 255, 0)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        label = f"{t['class_name']} {t['confidence']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, _FONT, 0.55, 1)
        # 标签底色块（防文字被背景淹没），文字置于框上方
        cv2.rectangle(out, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
        cv2.putText(out, label, (x1 + 3, max(th + 3, y1 - 4)), _FONT, 0.55,
                    (0, 0, 0), 1, cv2.LINE_AA)
    return out


def encode_result_jpeg(img_bgr: np.ndarray, quality: int = 90) -> bytes:
    """标注图 → JPEG 字节；只编码一次，供落盘与 data URL 复用。"""
    ok, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("标注图编码失败")
    return buf.tobytes()


def to_base64_jpeg(jpeg_bytes: bytes) -> str:
    """已编码的 JPEG 字节 → data URL（不重复编码）。"""
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
