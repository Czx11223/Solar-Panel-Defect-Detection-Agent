"""推理引擎：ONNX优先（onnxruntime），pt回退（ultralytics）。

关键设计（D25）：
- 双引擎实现同一接口（infer(img_bgr) → (targets, inference_time_ms)），
  按weights目录内容自动选择：存在 *.onnx 加载ONNXEngine（满足单图≤200ms指标），
  否则回退 *.pt（ultralytics YOLO）；
- 模型在应用启动时加载一次、常驻内存，单请求不重复加载；
- 置信度阈值0.25（D7）、NMS IoU阈值0.45；
- 目标坐标统一映射回原图像素坐标系（bbox [x1,y1,x2,y2]）。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import numpy as np

from ..core.config import settings
from ..core.pv_classes import ID_TO_ZH
from .preprocess import prepare_onnx_input

logger = logging.getLogger("pv.inference")


class BaseEngine:
    """推理引擎基类：model_version标识部署权重，available标记是否可用。"""

    model_version: str = "unknown"
    available: bool = False

    def infer(self, img_bgr: np.ndarray) -> tuple[list[dict], float]:
        """对BGR原图执行推理。

        返回：(targets, inference_time_ms)
        targets元素: {"class_id", "class_name", "confidence", "bbox":[x1,y1,x2,y2]}
        inference_time_ms仅统计推理耗时（不含网络传输与渲染，与D6口径一致）。
        """
        raise NotImplementedError


class ONNXEngine(BaseEngine):
    """ONNX Runtime CPU推理引擎。"""

    def __init__(self, onnx_path: Path):
        import onnxruntime as ort

        self.available = True
        self.model_version = onnx_path.stem
        so = ort.SessionOptions()
        so.intra_op_num_threads = settings.ort_threads  # CPU线程数，平衡延迟与占用
        self.session = ort.InferenceSession(
            str(onnx_path), sess_options=so, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        # 输出形状 (1, 4+nc, N)，由模型维度推断类别数
        out_shape = self.session.get_outputs()[0].shape
        self.nc = out_shape[1] - 4 if out_shape[1] else 6
        logger.info("ONNX引擎就绪：%s（nc=%d）", onnx_path.name, self.nc)

    def infer(self, img_bgr: np.ndarray) -> tuple[list[dict], float]:
        blob, meta = prepare_onnx_input(img_bgr)
        t0 = time.perf_counter()
        out = self.session.run(None, {self.input_name: blob})[0]
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return self._postprocess(out, meta), elapsed_ms

    @staticmethod
    def _postprocess(out: np.ndarray, meta: dict) -> list[dict]:
        """ONNX 原始输出 → 目标列表（共享纯函数，与 algorithm/export.py 同口径）。"""
        from .postprocess import decode_detections
        return decode_detections(out, meta, settings.conf_threshold,
                                 settings.iou_threshold, ID_TO_ZH)


class PTEngine(BaseEngine):
    """Ultralytics YOLO pt权重推理引擎（回退方案）。"""

    def __init__(self, pt_path: Path):
        from ultralytics import YOLO

        self.available = True
        self.model_version = pt_path.stem
        self.yolo = YOLO(str(pt_path))
        logger.info("PT引擎就绪：%s", pt_path.name)

    def infer(self, img_bgr: np.ndarray) -> tuple[list[dict], float]:
        # ultralytics内部自带letterbox/归一化/NMS，直接传BGR原图
        t0 = time.perf_counter()
        results = self.yolo.predict(
            source=img_bgr, imgsz=settings.imgsz,
            conf=settings.conf_threshold, iou=settings.iou_threshold,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        targets: list[dict] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            class_id = int(box.cls[0])
            targets.append({
                "class_id": class_id,
                "class_name": ID_TO_ZH.get(class_id, str(class_id)),
                "confidence": round(float(box.conf[0]), 4),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            })
        return targets, elapsed_ms


def load_engine(model_dir: Path) -> BaseEngine | None:
    """扫描权重目录加载引擎；无可用模型返回None（detect接口返回50301）。

    优先级：ONNX > PT；单个引擎加载失败时降级尝试下一个。
    """
    if model_dir.is_dir():
        for onnx_path in sorted(model_dir.glob("*.onnx")):
            try:
                return ONNXEngine(onnx_path)
            except Exception as e:  # ONNX加载失败（格式/依赖问题）时降级
                logger.warning("ONNX加载失败 %s：%s", onnx_path.name, e)
        for pt_path in sorted(model_dir.glob("*.pt")):
            try:
                return PTEngine(pt_path)
            except Exception as e:
                logger.warning("PT加载失败 %s：%s", pt_path.name, e)
    return None
