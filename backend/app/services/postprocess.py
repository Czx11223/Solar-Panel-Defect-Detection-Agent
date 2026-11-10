"""YOLOv8 ONNX 输出后处理（纯 numpy，与 algorithm/export.py 口径严格一致）。

输出形状 (1, 4+nc, N)：前 4 行为 xywh（letterbox 640 系像素坐标，含填充），
后 nc 行为已 sigmoid 的类别概率。

处理流程：置信度阈值 → **逐类 NMS**（与 Ultralytics class_agnostic=False 一致）
→ letterbox 坐标映射回原图像素系 → 裁剪到图内。

本模块只依赖 numpy，不依赖 onnxruntime / cv2 / torch，便于在算法侧与后端侧
共享同一份判定口径，并由 tests_light 的一致性测试锁定。
"""

from __future__ import annotations

import numpy as np


def nms_numpy(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """标准贪心 NMS；boxes 为 xyxy，返回按分数降序保留的**局部**索引。"""
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        ious = inter / np.maximum(areas[i] + areas[order[1:]] - inter, 1e-12)
        order = order[1:][ious <= iou_thr]
    return keep


def decode_detections(out: np.ndarray, meta: dict, conf_thr: float,
                      iou_thr: float, id_to_zh: dict) -> list[dict]:
    """原始输出 → 目标列表（原图坐标）。meta = {ratio, pad:(dw,dh), orig:(h,w)}。"""
    pred = out[0].T  # (N, 4+nc)
    if pred.size == 0:
        return []
    boxes_xywh, class_probs = pred[:, :4], pred[:, 4:]
    conf = class_probs.max(axis=1)
    cls = class_probs.argmax(axis=1)

    keep = conf >= conf_thr
    if not keep.any():
        return []
    boxes, scores, classes = boxes_xywh[keep], conf[keep], cls[keep]
    cx, cy, bw, bh = boxes.T
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)

    ratio, (dw, dh) = meta["ratio"], meta["pad"]
    h, w = meta["orig"]
    targets: list[dict] = []
    for cid in np.unique(classes):
        mask = classes == cid
        indices = np.flatnonzero(mask)
        for i in nms_numpy(xyxy[mask], scores[mask], iou_thr):
            x1, y1, x2, y2 = (float(v) for v in xyxy[indices[i]])
            class_id = int(cid)
            targets.append({
                "class_id": class_id,
                "class_name": id_to_zh.get(class_id, str(class_id)),
                "confidence": round(float(scores[indices[i]]), 4),
                "bbox": [round(max(0.0, (x1 - dw) / ratio), 1),
                         round(max(0.0, (y1 - dh) / ratio), 1),
                         round(min(float(w), (x2 - dw) / ratio), 1),
                         round(min(float(h), (y2 - dh) / ratio), 1)],
            })
    return targets
