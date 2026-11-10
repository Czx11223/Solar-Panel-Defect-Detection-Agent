"""光伏面板缺陷检测系统 · 模型导出脚本（阶段2交付，阶段3部署前置）。

功能：
    1. ONNX导出（默认执行，决策D21）：FP32、opset=12、simplify图优化、
       静态batch=1（匹配单图检测场景）；
    2. INT8动态量化（--int8）：onnxruntime动态量化，无需校准集；
       仅量化MatMul/Gemm（卷积量化产生ConvInteger节点，CPU运行时不支持），
       YOLOv8纯卷积结构故产物体积与FP32基本相同（如实呈现；
       升级路径为静态量化QDQ格式，需校准数据集）；
    3. FP16半精度导出（--half，需CUDA导出环境，文件约减半）；
    4. 结构化剪枝（--prune，决策D20，默认关闭）：torch-pruning按L1范数裁剪
       安全集合层（下采样Conv、SPPF、C2f出口；避开C2f内部与检测头），
       剪后可--finetune-epochs微调恢复精度；CNN剪枝存在掉点风险，
       任务书定位为"尝试"项，量化为主要压缩手段；
    5. ONNX精度核对（默认执行）：YOLO(onnx).val() 与pt基线对比mAP@0.5，
       降幅>2%时告警并不建议部署该产物（--skip-eval跳过）；
    6. 推理延迟基准（--benchmark）：onnxruntime CPU会话，
       端到端计时（letterbox预处理 + session推理 + NMS后处理），
       warmup N次后测M次，输出mean/p50/p95毫秒；同时测pt基线对比；
       核对单图≤200ms目标（测试硬件随报告记录，决策D6）；
    7. 导出报告 models/export_report.md + manifest.json：
       各产物体积/精度/延迟对比表与部署建议。

前置条件：训练完成（runs/下存在best.pt）；--int8/--benchmark需要onnxruntime；
--prune需要torch-pruning（未安装时给出提示）。

数据集下载地址（注册后免费下载，人工步骤）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+；依赖见 algorithm/requirements.txt。

运行示例：
    python export.py                                    # FP32 ONNX + 精度核对
    python export.py --int8 --benchmark                 # INT8量化 + 延迟基准
    python export.py --half                             # FP16（需CUDA导出环境）
    python export.py --prune --prune-ratio 0.2 --finetune-epochs 10   # 剪枝+微调
    python export.py --weights runs/detect/train3/weights/best.pt --skip-eval
"""

import argparse
import json
import platform
import shutil
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
MAP50_DROP_WARN = 0.02      # ONNX产物mAP@0.5允许降幅（>2%不建议部署）
LATENCY_TARGET_MS = 200.0   # 验收线：单图推理 ≤200ms（决策D6硬件）


def resolve_default_data() -> Path:
    """定位精度核对用的数据集配置（与 train.py 口径一致）。"""
    candidates = (
        BASE_DIR / "datasets" / "data.yaml",
        BASE_DIR / "datasets_final" / "data_final.yaml",
        BASE_DIR / "datasets_fixed" / "data.yaml",
    )
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


def find_latest_best() -> Path | None:
    """定位 runs/ 下最新 best.pt（按文件修改时间）。"""
    cands = [p for p in (BASE_DIR / "runs").rglob("best.pt") if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def model_mb(p: Path) -> float:
    """文件大小（MB）。"""
    return round(p.stat().st_size / 1048576, 2)


def eval_map50(weights: Path, data: Path, split: str, imgsz: int):
    """调用Ultralytics val得到mAP@0.5（ONNX产物亦可，AutoBackend加载）；nan→None。"""
    m = YOLO(str(weights))
    r = m.val(data=str(data), split=split, imgsz=imgsz, plots=False, verbose=False)
    v = float(r.box.map50)
    return None if v != v else round(v, 6)


def prune_model(pt_path: Path, ratio: float, imgsz: int, out_dir: Path) -> Path:
    """L1结构化通道剪枝（决策D20）。

    规则：按输出通道L1范数从小到大裁剪，比例ratio；
    剪枝范围限"安全集合"，规避结构雷区（已通过冒烟验证，ultralytics 8.4 + torch-pruning 1.6）：
      - Conv下采样层（backbone/neck串行conv，依赖链简单）；
      - SPPF入口cv1与出口cv2（cat四路同源，对齐安全）；
      - C2f出口cv2（出口剪枝不触碰内部split/cat/残差结构）；
    明确不剪：C2f内部conv（动态split+残差add，torch-pruning依赖对齐易破坏结构）、
    Detect检测头（类别输出维度不可剪）。
    DependencyGraph自动同步耦合层（BN、下游in_channels、concat对齐）；
    torch-pruning 1.6.0移除check_dependency接口，group.prune()直接执行对齐剪枝，
    单层异常时跳过该层不影响其余层。
    剪枝后自检：检测输出shape须与剪枝前一致，否则中止（防止结构破坏）。
    产物：models/pruned_<stem>.pt（Ultralytics可加载格式）。
    """
    try:
        import torch_pruning as tp
    except ImportError:
        raise SystemExit("[剪枝] 缺少依赖：pip install torch-pruning>=1.6.0"
                         "（或去掉--prune）")
    from ultralytics.nn.modules.conv import Conv
    from ultralytics.nn.modules.block import C2f, SPPF

    yolo = YOLO(str(pt_path))
    model = yolo.model.cpu().eval()
    example = torch.randn(1, 3, imgsz, imgsz)
    with torch.no_grad():
        out_before = model(example)
    dg = tp.DependencyGraph().build_dependency(model, example_inputs=example)

    roots: list[torch.nn.Module] = []
    for block in model.model:
        if isinstance(block, Conv):
            roots.append(block.conv)              # 下采样串行conv
        elif isinstance(block, SPPF):
            roots += [block.cv1.conv, block.cv2.conv]
        elif isinstance(block, C2f):
            roots.append(block.cv2.conv)          # C2f出口

    params_before = sum(p.numel() for p in model.parameters())
    n_pruned, n_skip = 0, 0
    for m in roots:
        if m.out_channels < 16:                   # 通道过少的层不剪，保留最小宽度
            continue
        keep = max(8, int(round(m.out_channels * (1.0 - ratio))))
        if keep >= m.out_channels:
            continue
        # 输出通道L1重要性：|W|按(out,in,kh,kw)的(1,2,3)维求和
        importance = m.weight.data.abs().sum(dim=(1, 2, 3))
        idxs = torch.argsort(importance)[: m.out_channels - keep].tolist()
        try:
            group = dg.get_pruning_group(m, tp.prune_conv_out_channels, idxs=idxs)
            group.prune()                         # 自动同步耦合层
            n_pruned += 1
        except Exception:
            n_skip += 1

    with torch.no_grad():
        out_after = model(example)
    if tuple(out_before[0].shape) != tuple(out_after[0].shape):
        raise SystemExit("[剪枝] 自检失败：检测输出shape改变，结构被破坏，中止导出")
    params_after = sum(p.numel() for p in model.parameters())

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"pruned_{pt_path.stem}.pt"
    torch.save({"model": model, "train_args": {}, "date": datetime.now().isoformat(),
                "version": "pruned", "description": f"L1 structured pruning ratio={ratio}"},
               out)
    print(f"[剪枝] 裁剪{n_pruned}层（跳过{n_skip}层，ratio={ratio}），参数量 "
          f"{params_before / 1e6:.2f}M → {params_after / 1e6:.2f}M"
          f"（{100 * params_after / params_before:.1f}%），产物：{out}")
    return out


def finetune_pruned(pruned_pt: Path, args) -> Path:
    """剪枝后微调恢复精度：小学习率、少轮数、更紧的早停。"""
    yolo = YOLO(str(pruned_pt))
    yolo.train(
        data=str(args.data),
        epochs=args.finetune_epochs,  # 微调轮数（远小于完整训练）
        imgsz=args.imgsz,
        batch=args.batch,
        lr0=1e-4,                     # 微调用小学习率，避免破坏已收敛权重
        lrf=0.1,
        cos_lr=True,                  # 余弦退火
        patience=5,                   # 更紧的早停
        device=args.device,
        workers=args.workers,
        project=str(args.project),
        name="finetune_pruned",
        exist_ok=True,
        plots=False,
        verbose=False,
    )
    best = Path(yolo.trainer.save_dir) / "weights" / "best.pt"
    if best.is_file():
        print(f"[微调] 完成，最优权重：{best}")
        return best
    print("[微调] 未产出best.pt，使用剪枝原始权重")
    return pruned_pt


def export_onnx(pt_path: Path, imgsz: int, opset: int, half: bool) -> Path:
    """Ultralytics ONNX导出（返回产物路径，位于pt同目录）。"""
    yolo = YOLO(str(pt_path))
    path = yolo.export(format="onnx", imgsz=imgsz, opset=opset, simplify=True,
                       dynamic=False, batch=1, half=half)
    return Path(path)


def quantize_int8(onnx_path: Path, out_path: Path) -> None:
    """onnxruntime动态INT8量化（权重量化+激活动态量化，无需校准集）。

    仅量化MatMul/Gemm算子：卷积动态量化会产生ConvInteger节点，
    多数onnxruntime CPU构建未实现该算子（NOT_IMPLEMENTED），导致无法推理；
    限定量化算子类型后产物可在标准CPU运行时稳定执行。
    已知局限（如实呈现）：YOLOv8为纯CNN结构，计算图几乎全为Conv，
    可量化的MatMul/Gemm极少，故产物体积与FP32基本相同属预期现象；
    体积压缩请依赖--prune剪枝；如需真正的INT8卷积压缩，
    后续可升级为静态量化（QDQ格式，需校准数据集，CPU运行时支持）。
    """
    from onnxruntime.quantization import quantize_dynamic, QuantType
    quantize_dynamic(str(onnx_path), str(out_path), weight_type=QuantType.QInt8,
                     op_types_to_quantize=["MatMul", "Gemm"])
    src_mb, dst_mb = model_mb(onnx_path), model_mb(out_path)
    note = "" if dst_mb < src_mb * 0.95 else \
        "（纯卷积网络无可量化算子，产物与FP32等价，属预期，详见函数说明）"
    print(f"[INT8] 量化完成：{out_path}（{dst_mb}MB）{note}")


def letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, tuple]:
    """BGR 原图 → (RGB 填充图, ratio, (dw,dh))。

    与 backend/app/services/preprocess.py:prepare_onnx_input 完全一致：
    等比缩放 + 114 灰边填充 + BGR→RGB，并返回坐标还原所需的 ratio/pad。
    """
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    dw, dh = (size - nw) / 2, (size - nh) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return cv2.cvtColor(padded, cv2.COLOR_BGR2RGB), r, (dw, dh)


def nms_numpy(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """numpy实现的NMS（boxes为xyxy）。"""
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


def postprocess_onnx(output: np.ndarray, conf_thr: float, iou_thr: float,
                     meta: dict | None = None) -> list[tuple]:
    """ONNX 输出 (1,4+nc,N) → [(x1,y1,x2,y2,cls,conf)]。

    与 backend/app/services/postprocess.py:decode_detections 口径一致：
    阈值过滤 → 逐类 NMS → 传入 meta 时映射回原图像素坐标。
    """
    pred = output[0].T
    if pred.size == 0:
        return []
    boxes_xywh, class_probs = pred[:, :4], pred[:, 4:]
    confs = class_probs.max(axis=1)
    cls_ids = class_probs.argmax(axis=1)
    keep = confs >= conf_thr
    if not keep.any():
        return []
    boxes, scores, classes = boxes_xywh[keep], confs[keep], cls_ids[keep]
    cx, cy, bw, bh = boxes.T
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
    out: list[tuple] = []
    for cid in np.unique(classes):
        mask = classes == cid
        indices = np.flatnonzero(mask)
        for i in nms_numpy(xyxy[mask], scores[mask], iou_thr):
            x1, y1, x2, y2 = xyxy[indices[i]]
            if meta is not None:
                r, (dw, dh) = meta["ratio"], meta["pad"]
                x1, y1, x2, y2 = ((x1 - dw) / r, (y1 - dh) / r,
                                  (x2 - dw) / r, (y2 - dh) / r)
            out.append((float(x1), float(y1), float(x2), float(y2),
                        int(cid), float(scores[indices[i]])))
    return out


def lat_stats(times_ms: list[float]) -> dict:
    """延迟统计：mean/p50/p95（毫秒）。"""
    arr = np.asarray(times_ms)
    return {"mean": round(float(arr.mean()), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2)}


def benchmark_onnx(onnx_path: Path, img: np.ndarray, imgsz: int, conf: float,
                   nms_iou: float, n: int, warmup: int) -> dict:
    """ONNX端到端延迟：letterbox预处理 + session推理 + NMS后处理。"""
    import onnxruntime as ort
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    times = []
    meta: dict = {"ratio": 1.0, "pad": (0.0, 0.0), "orig": img.shape[:2]}
    for _ in range(warmup + n):
        t0 = time.perf_counter()
        rgb, ratio, pad = letterbox(img, imgsz)                 # 与部署侧同为 BGR→RGB
        x = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))[None]
        out = sess.run(None, {name: x})
        meta["ratio"], meta["pad"] = ratio, pad
        postprocess_onnx(out[0], conf, nms_iou, meta)
        times.append((time.perf_counter() - t0) * 1000)
    return lat_stats(times[warmup:])


def benchmark_pt(pt_path: Path, img: np.ndarray, imgsz: int, n: int, warmup: int) -> dict:
    """PyTorch基线端到端延迟（predict含预处理与后处理，CPU）。"""
    model = YOLO(str(pt_path))
    times = []
    for _ in range(warmup + n):
        t0 = time.perf_counter()
        model.predict(img, imgsz=imgsz, device="cpu", verbose=False)
        times.append((time.perf_counter() - t0) * 1000)
    return lat_stats(times[warmup:])


def write_export_report(out_dir: Path, artifacts: list[dict], baseline: dict,
                        args, prune_note: str) -> None:
    """生成 models/export_report.md 与 manifest.json。"""
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "无（CPU）"
    hardware = f"CPU: {platform.processor() or platform.machine()}；GPU: {gpu}；" \
               f"基准运行时: onnxruntime CPU / torch CPU"
    has_lat = any(a.get("latency") for a in artifacts)

    lines = [
        "# 模型导出报告（Export Report）",
        "",
        f"- 导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 基线权重：{baseline.get('weights')}",
        f"- 基线mAP@0.5：{baseline.get('map50') if baseline.get('map50') is not None else '未测（--skip-eval）'}",
        f"- 导出参数：imgsz={args.imgsz}, opset={args.opset}, batch=1, simplify=True",
        f"- 运行环境：{hardware}",
        f"- 剪枝：{prune_note}",
        "",
        "## 产物对比",
        "",
        "| 产物 | 精度 | 体积(MB) | mAP@0.5 | 相对基线降幅 | 延迟mean/p95(ms) | ≤200ms | 结论 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for a in artifacts:
        lat = a.get("latency")
        lat_txt = f"{lat['mean']} / {lat['p95']}" if lat else "未测"
        lat_ok = "—" if not lat else ("达标" if lat["mean"] <= LATENCY_TARGET_MS else "超标")
        if a.get("map50") is None:
            drop_txt, verdict = "未测", "精度未核对"
        else:
            drop = round(baseline["map50"] - a["map50"], 4) if baseline.get("map50") is not None else None
            drop_txt = "—" if drop is None else f"{drop:+.4f}"
            acc_ok = drop is None or drop <= MAP50_DROP_WARN
            verdict = "可用于部署" if (acc_ok and (lat_ok in ("—", "达标"))) else \
                      "精度降幅超限，不建议部署" if not acc_ok else "延迟超标，不建议部署"
        lines.append(f"| {a['name']} | {a['precision']} | {a['size_mb']} | "
                     f"{a.get('map50', '—') if a.get('map50') is not None else '—'} | "
                     f"{drop_txt} | {lat_txt} | {lat_ok} | {verdict} |")

    deployable = [a for a in artifacts if a.get("map50_ok")
                  and (not a.get("latency") or a["latency"]["mean"] <= LATENCY_TARGET_MS)]
    if deployable:
        rec = min(deployable, key=lambda a: a["latency"]["mean"] if a.get("latency")
                  else a["size_mb"])
        lines += ["", f"**部署建议**：{rec['name']}（{rec['path']}）——在精度达标前提下"
                      + (f"延迟最低（{rec['latency']['mean']}ms）" if rec.get("latency")
                         else "体积最小") + "；拷贝至 backend/app/ml/weights/ 并登记 model_version。"]
    else:
        lines += ["", "**部署建议**：暂无同时满足精度与延迟要求的产物；"
                      "可尝试--int8量化、降低imgsz或降级模型规模（yolov8s→n）后重新导出。"]
    if not has_lat:
        lines += ["", "注：延迟未测（未指定--benchmark）。"]
    lines += ["", "## 目标阈值核对",
              "",
              "| 指标 | 目标 | 结果 |",
              "|---|---|---|",
              f"| 单图推理延迟 | ≤{LATENCY_TARGET_MS:.0f}ms | "
              f"{'见上表（基准硬件：' + hardware.split('；')[0] + '）' if has_lat else '未测'} |",
              f"| ONNX精度降幅 | ≤{MAP50_DROP_WARN * 100:.0f}% | 见上表 |"]

    (out_dir / "export_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "date": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "baseline": baseline, "hardware": hardware,
        "targets": {"latency_ms": LATENCY_TARGET_MS, "map50_drop": MAP50_DROP_WARN},
        "artifacts": artifacts,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YOLOv8模型导出：剪枝/量化/ONNX/延迟基准（阶段2）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--weights", type=Path, default=None,
                        help="待导出权重；留空自动选取 runs/ 下最新best.pt")
    parser.add_argument("--data", type=Path, default=resolve_default_data(),
                        help="数据集配置（精度核对用）；默认自动探测，同 train.py")
    parser.add_argument("--split", type=str, default="test", choices=["val", "test"],
                        help="精度核对split")
    parser.add_argument("--out", type=Path, default=BASE_DIR / "models",
                        help="导出产物输出目录")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="导出输入边长（与训练/部署一致）")
    parser.add_argument("--opset", type=int, default=12, help="ONNX opset版本")
    parser.add_argument("--half", action="store_true",
                        help="FP16半精度ONNX导出（需CUDA导出环境）")
    parser.add_argument("--int8", action="store_true",
                        help="INT8动态量化（onnxruntime，无需校准集）")
    parser.add_argument("--prune", action="store_true",
                        help="L1结构化剪枝（默认关闭，D20；需torch-pruning）")
    parser.add_argument("--prune-ratio", type=float, default=0.2,
                        help="剪枝通道比例（0–1，过大易掉点）")
    parser.add_argument("--finetune-epochs", type=int, default=10,
                        help="剪枝后微调轮数（0为不微调）")
    parser.add_argument("--skip-eval", action="store_true",
                        help="跳过mAP精度核对（快速导出）")
    parser.add_argument("--benchmark", action="store_true",
                        help="执行推理延迟基准（onnxruntime CPU，含pt基线对比）")
    parser.add_argument("--benchmark-runs", type=int, default=100,
                        help="延迟基准测量次数（前warmup次不计）")
    parser.add_argument("--warmup", type=int, default=10,
                        help="延迟基准预热次数")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="基准后处理置信度阈值（与部署一致，D7）")
    parser.add_argument("--nms-iou", type=float, default=0.45,
                        help="基准后处理NMS IoU阈值（与部署一致）")
    parser.add_argument("--batch", type=int, default=16, help="微调批大小")
    parser.add_argument("--device", type=str, default=None,
                        help="微调设备（留空自动）；延迟基准固定CPU保证可比")
    parser.add_argument("--workers", type=int, default=8, help="微调数据加载进程数")
    parser.add_argument("--project", type=Path, default=BASE_DIR / "runs",
                        help="微调输出根目录")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    weights = args.weights or find_latest_best()
    if weights is None or not weights.is_file():
        raise SystemExit("未指定--weights且 runs/ 下未找到 best.pt；请先运行 train.py 训练")
    if not args.skip_eval and not args.data.is_file():
        raise SystemExit(f"数据集配置不存在：{args.data}（精度核对需要；"
                         "或加--skip-eval跳过）")

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[导出] 基线权重：{weights}（{model_mb(weights)}MB）")

    # ---- 1. 剪枝（可选，D20）----
    prune_note = "未启用（默认关闭）"
    work_pt = weights
    if args.prune:
        pruned = prune_model(weights, args.prune_ratio, args.imgsz, out_dir)
        if args.finetune_epochs > 0:
            work_pt = finetune_pruned(pruned, args)
        else:
            work_pt = pruned
        prune_note = f"ratio={args.prune_ratio}" + ("，已微调" if args.finetune_epochs > 0 else "，未微调")

    # ---- 2. pt基线mAP ----
    baseline_map50 = None
    if not args.skip_eval:
        baseline_map50 = eval_map50(work_pt, args.data, args.split, args.imgsz)
        print(f"[基线] pt mAP@0.5 = {baseline_map50}")

    # ---- 3. ONNX导出（FP32默认 + FP16可选）----
    # ONNX产物默认落在pt同目录；若pt已在out目录（剪枝产物场景）则路径重合，跳过拷贝
    def into_out(src: Path, dst: Path) -> None:
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)

    artifacts: list[dict] = []
    fp32_tmp = export_onnx(work_pt, args.imgsz, args.opset, half=False)
    fp32 = out_dir / f"{work_pt.stem}.onnx"
    into_out(fp32_tmp, fp32)
    artifacts.append({"name": fp32.name, "path": str(fp32), "precision": "FP32",
                      "size_mb": model_mb(fp32), "map50": None, "map50_ok": None})
    print(f"[ONNX] FP32导出完成：{fp32}（{model_mb(fp32)}MB）")

    if args.half:
        try:
            fp16_tmp = export_onnx(work_pt, args.imgsz, args.opset, half=True)
            fp16 = out_dir / f"{work_pt.stem}_fp16.onnx"
            into_out(fp16_tmp, fp16)
            artifacts.append({"name": fp16.name, "path": str(fp16), "precision": "FP16",
                              "size_mb": model_mb(fp16), "map50": None, "map50_ok": None})
            print(f"[ONNX] FP16导出完成：{fp16}（{model_mb(fp16)}MB）")
        except Exception as e:  # FP16导出需CUDA环境
            print(f"[FP16] 导出失败（半精度导出需要CUDA环境）：{e}")

    # ---- 4. INT8动态量化（可选）----
    if args.int8:
        int8 = out_dir / f"{work_pt.stem}_int8.onnx"
        quantize_int8(fp32, int8)
        artifacts.append({"name": int8.name, "path": str(int8), "precision": "INT8",
                          "size_mb": model_mb(int8), "map50": None, "map50_ok": None})

    # ---- 5. ONNX产物精度核对（默认执行）----
    if not args.skip_eval:
        for a in artifacts:
            try:
                a["map50"] = eval_map50(Path(a["path"]), args.data, args.split, args.imgsz)
                drop = None if (a["map50"] is None or baseline_map50 is None) \
                    else round(baseline_map50 - a["map50"], 4)
                a["map50_ok"] = True if drop is None else drop <= MAP50_DROP_WARN
                print(f"[核对] {a['name']} mAP@0.5 = {a['map50']}（"
                      f"{'降幅' + format(drop, '+.4f') if drop is not None else '基线未测'}）")
            except Exception as e:
                a["map50_ok"] = False
                print(f"[核对] {a['name']} 精度核对失败：{e}")

    # ---- 6. 延迟基准（可选，CPU口径）----
    if args.benchmark:
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        pt_lat = benchmark_pt(work_pt, img, args.imgsz, args.benchmark_runs, args.warmup)
        print(f"[基准] pt基线（CPU）：mean {pt_lat['mean']}ms / p95 {pt_lat['p95']}ms")
        for a in artifacts:
            try:
                a["latency"] = benchmark_onnx(Path(a["path"]), img, args.imgsz, args.conf,
                                              args.nms_iou, args.benchmark_runs, args.warmup)
                print(f"[基准] {a['name']}：mean {a['latency']['mean']}ms / "
                      f"p50 {a['latency']['p50']}ms / p95 {a['latency']['p95']}ms")
            except Exception as e:
                a["latency"] = None
                print(f"[基准] {a['name']} 基准失败：{e}")

    # ---- 7. 导出报告 ----
    write_export_report(out_dir, artifacts,
                        {"weights": str(work_pt), "map50": baseline_map50,
                         "size_mb": model_mb(work_pt)},
                        args, prune_note)

    print("=" * 64)
    print(f"导出完成，产物目录：{out_dir}")
    for a in artifacts:
        print(f"  {a['name']:<24}{a['precision']:<6}{a['size_mb']:>8}MB")
    print(f"报告：{out_dir / 'export_report.md'}")
    print("=" * 64)


if __name__ == "__main__":
    main()
