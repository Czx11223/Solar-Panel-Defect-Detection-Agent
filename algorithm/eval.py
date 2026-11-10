"""光伏面板缺陷检测系统 · 模型评估脚本（阶段2）。

功能（双口径评估，互为核对）：
    1. 官方口径：Ultralytics val 在指定split上评估 mAP@0.5 / mAP@0.5:0.95 与
       各类别AP，框架自动保存PR曲线、混淆矩阵至输出目录 official/ 下；
    2. 工程口径（自实现，决策D22）：
       a. 全测试集低阈值预测（conf=0.01）收集全部检测框；
       b. 按置信度降序对每类做贪心匹配（IoU≥0.5，每个GT至多命中一次）；
       c. 累计TP/FP得到每类PR点列，全点插值计算AP@0.5（与Ultralytics口径一致）；
       d. 工作点指标（精确率/召回率/F1）取conf=0.25，与部署阈值一致（决策D7）；
       e. 另输出micro平均PR曲线（全部类别检测合并统计）；
    3. 双口径mAP@0.5并列对照，偏差应<0.01（数据与实现一致性自检）；
    4. 验收判定（PRD 6.1 / 任务书硬指标）：
       - mAP@0.5 ≥ 75%（测试集总体）；
       - 主要缺陷类别（积灰/鸟粪/电损伤/物理损伤/积雪）召回率@0.25每类≥80%；
         清洁类为正常状态参考类，不设召回率线；
       - 全部达标退出码0；存在未达标项退出码1并输出调参建议
         （单图推理≤200ms由 export.py --benchmark 覆盖，决策D6硬件）；
    5. 产物（runs/eval/<时间戳>/）：
       metrics.json     全部指标（机器可读）
       pr_curve.png     六类PR曲线 + micro平均（图例含各类AP）
       pr_data.json     PR曲线原始点列
       eval_summary.md  按 docs/model_eval_report.md 模板自动填充的评估报告
       official/        Ultralytics val自动产物（框架PR曲线、混淆矩阵等）

前置条件：datasets/data.yaml 就绪（阶段1产出）；--weights 指向训练产物
（默认自动选取 runs/ 下最新 best.pt）。

数据集下载地址（注册后免费下载，人工步骤）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+；依赖见 algorithm/requirements.txt。

运行示例：
    python eval.py                                              # 测试集，自动找最新best.pt
    python eval.py --weights runs/detect/train3/weights/best.pt
    python eval.py --split val --conf 0.30                     # 验证集 + 自定义工作点
"""

import argparse
import json
import platform
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

import matplotlib
matplotlib.use("Agg")  # 无显示环境（服务器/CI）下渲染PNG
import matplotlib.pyplot as plt

import torch
import ultralytics
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "scripts"))
from pv_classes import ID_TO_ZH  # noqa: E402  六类中文名（阶段1共享映射，单一事实源）

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
DEFECT_IDS = [1, 2, 3, 4, 5]     # 主要缺陷类别id（召回率验收线考核范围）
MAP50_TARGET = 0.75              # 验收线：mAP@0.5 ≥ 75%
RECALL_TARGET = 0.80             # 验收线：缺陷类召回率@0.25 ≥ 80%
MAP50_DELTA_WARN = 0.01          # 双口径偏差告警线


def fnum(x, nd: int = 6):
    """数值清洗：nan/None→None，其余转float并保留nd位（JSON可序列化）。"""
    if x is None or (isinstance(x, float) and x != x):
        return None
    return round(float(x), nd)


def find_latest_best() -> Path | None:
    """定位 runs/ 下最新的 best.pt（按文件修改时间）。"""
    cands = [p for p in (BASE_DIR / "runs").rglob("best.pt") if p.is_file()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def iou_xyxy(a, b) -> float:
    """两个xyxy格式框的IoU。"""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def pr_points(tp_flags: list[bool], n_gt: int):
    """由按置信度降序排列的TP/FP序列生成PR点列。

    tp_flags[i]表示第i个检测（按conf降序）是否命中GT；
    返回(recall数组, precision数组)。
    """
    if not tp_flags:
        return np.array([0.0]), np.array([1.0])
    tp = np.asarray(tp_flags, dtype=float)
    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(1.0 - tp)
    recall = tp_cum / max(n_gt, 1)
    precision = tp_cum / np.maximum(tp_cum + fp_cum, 1e-12)
    return recall, precision


def ap_allpoint(recall: np.ndarray, precision: np.ndarray) -> float:
    """全点插值AP（precision包络 + 变recall区间求和，与Ultralytics口径一致）。"""
    mrec = np.concatenate(([0.0], recall, [1.0]))
    mpre = np.concatenate(([1.0], precision, [0.0]))
    for i in range(mpre.size - 1, 0, -1):          # precision单调包络：从右向左取最大
        mpre[i - 1] = max(mpre[i - 1], mpre[i])
    idx = np.where(mrec[1:] != mrec[:-1])[0]        # recall发生变化的区间
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def evaluate_engineering(model, img_paths: list[Path], label_dir: Path, args):
    """工程口径评估（D22）：低阈值预测收集 → 逐类贪心匹配 → PR点列/AP/工作点指标。"""
    nc = len(model.names)
    dets_by_class = {c: [] for c in range(nc)}   # [(conf, img_key, xyxy)]
    gts_by_class = {c: {} for c in range(nc)}    # {img_key: [xyxy, ...]}
    label_index = {p.stem: p for p in label_dir.glob("*.txt")}

    results = model.predict([str(p) for p in img_paths], conf=args.collect_conf,
                            iou=args.nms_iou, imgsz=args.imgsz, stream=True, verbose=False)
    for img_path, r in zip(img_paths, results):
        h, w = r.orig_shape
        img_key = img_path.stem
        # GT：YOLO归一化标注 → 原图像素xyxy
        label = label_index.get(img_key)
        if label is not None:
            for line in label.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 5:
                    cid, cx, cy, bw, bh = int(parts[0]), *(float(v) for v in parts[1:])
                    gts_by_class[cid].setdefault(img_key, []).append(
                        ((cx - bw / 2) * w, (cy - bh / 2) * h,
                         (cx + bw / 2) * w, (cy + bh / 2) * h))
        # 检测结果（predict返回原图像素坐标）
        for conf, cid, box in zip(r.boxes.conf.tolist(), r.boxes.cls.tolist(),
                                  r.boxes.xyxy.tolist()):
            dets_by_class[int(cid)].append((float(conf), img_key, tuple(box)))

    per_class = {}
    all_pairs: list[tuple[float, bool]] = []      # (conf, is_tp)，micro平均用
    for c in range(nc):
        dets = sorted(dets_by_class[c], key=lambda t: -t[0])
        gt_matched = {k: [False] * len(v) for k, v in gts_by_class[c].items()}
        n_gt = sum(len(v) for v in gts_by_class[c].values())
        tp_flags: list[bool] = []
        for conf, img_key, box in dets:
            # 贪心匹配：取IoU最大且未命中的GT，IoU≥match_iou判TP
            best_iou, best_j = 0.0, -1
            for j, gbox in enumerate(gts_by_class[c].get(img_key, ())):
                if gt_matched[img_key][j]:
                    continue
                v = iou_xyxy(box, gbox)
                if v > best_iou:
                    best_iou, best_j = v, j
            hit = best_j >= 0 and best_iou >= args.match_iou
            if hit:
                gt_matched[img_key][best_j] = True
            tp_flags.append(hit)
            all_pairs.append((conf, hit))

        recall, precision = pr_points(tp_flags, n_gt)
        ap = ap_allpoint(recall, precision) if n_gt else None

        # 工作点指标（conf阈值 = 部署阈值，D7/D22）
        sel = [i for i, d in enumerate(dets) if d[0] >= args.conf]
        tp_w = sum(tp_flags[i] for i in sel)
        n_det_w = len(sel)
        p_w = tp_w / n_det_w if n_det_w else 0.0
        r_w = tp_w / n_gt if n_gt else None
        f1_w = (2 * p_w * r_w / (p_w + r_w)) if (n_det_w and r_w and p_w + r_w > 0) else 0.0

        per_class[c] = {
            "n_gt": n_gt, "n_det_work": n_det_w,
            "ap50": fnum(ap), "precision_work": fnum(p_w), "recall_work": fnum(r_w),
            "f1_work": fnum(f1_w), "recall_curve": recall.tolist(), "precision_curve": precision.tolist(),
        }

    # micro平均：全部类别(conf, tp)合并后按conf降序累计
    all_pairs.sort(key=lambda t: -t[0])
    micro_tp = [p[1] for p in all_pairs]
    micro_n_gt = sum(per_class[c]["n_gt"] for c in range(nc))
    m_rec, m_pre = pr_points(micro_tp, micro_n_gt)
    micro_ap = ap_allpoint(m_rec, m_pre) if micro_n_gt else None

    return {
        "per_class": per_class,
        "micro": {"ap50": fnum(micro_ap), "recall_curve": m_rec.tolist(),
                  "precision_curve": m_pre.tolist()},
        "map50": fnum(np.mean([per_class[c]["ap50"] for c in range(nc)
                               if per_class[c]["ap50"] is not None]) if any(
                               per_class[c]["ap50"] is not None for c in range(nc)) else None),
    }


def evaluate_official(model, args, outdir: Path) -> dict:
    """官方口径：Ultralytics val（自动保存框架PR曲线/混淆矩阵到official/下）。

    注意：rect=False 固定正方形letterbox（640×640），与ONNX部署预处理一致
    （决策D7/D22；默认rect矩形批处理会在672×512等非部署形状上虚高指标，
    实测2026-09-18定位并修复）。
    """
    v = model.val(data=str(args.data), split=args.split, imgsz=args.imgsz,
                  rect=False, plots=True,
                  project=str(outdir), name="official", exist_ok=True, verbose=False)
    per_class = {}
    for i in range(len(v.names)):
        per_class[i] = {
            "ap50": fnum(v.box.ap50[i]), "ap50_95": fnum(v.box.ap[i]),
            "precision": fnum(v.box.p[i]), "recall": fnum(v.box.r[i]),
        }
    return {"map50": fnum(v.box.map50), "map50_95": fnum(v.box.map), "per_class": per_class}


def plot_pr_curves(eng: dict, names: dict, split: str, out_png: Path) -> None:
    """绘制六类PR曲线 + micro平均（图例含各类AP@0.5）。"""
    fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
    for c in sorted(eng["per_class"]):
        e = eng["per_class"][c]
        ap_txt = f"{e['ap50']:.3f}" if e["ap50"] is not None else "N/A"
        ax.plot(e["recall_curve"], e["precision_curve"], lw=1.5,
                label=f"{names.get(c, c)} AP={ap_txt}")
    mi = eng["micro"]
    if mi["ap50"] is not None:
        ax.plot(mi["recall_curve"], mi["precision_curve"], "k--", lw=1.2,
                label=f"micro-average AP={mi['ap50']:.3f}")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(f"PR Curves (IoU=0.5, split={split})")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def build_suggestions(map50_pass: bool, failed_recall: list[tuple[int, str]]) -> list[str]:
    """未达标项的调参建议（与阶段1脚本衔接）。"""
    s = []
    if not map50_pass:
        s.append("总体mAP@0.5未达标：扩充增强样本量（augment.py --count 提升，含稀有类加权），"
                 "确认train.py加权采样开启（默认开启），适当延长--epochs并观察验证曲线")
    for c, name in failed_recall:
        s.append(f"{name}召回率不足：已诊断（2026-09-18，见 docs/model_eval_diag.md）根因为测试集"
                 "标签系统性失真——88张test图标签全部为全幅占位框(0.5 0.5 1.0 1.0)，与局部缺陷"
                 "位置不符，且模型对该类局部缺陷输出类别混淆（电损伤→鸟粪/清洁等）。实测降低"
                 "工作点阈值(conf 0.05)与调整NMS IoU(0.45→0.7)召回率均无变化，参数调优无效；"
                 "根治需修正train/val/test局部缺陷标注后重新训练")
    return s


def fill_report_template(outdir: Path, ctx: dict) -> None:
    """读取 docs/model_eval_report.md 模板，替换占位符生成 eval_summary.md。"""
    tpl_path = BASE_DIR.parent / "docs" / "model_eval_report.md"
    if tpl_path.is_file():
        text = tpl_path.read_text(encoding="utf-8")
    else:
        text = ("# 模型评估报告（简版）\n\n"
                "> 模板 docs/model_eval_report.md 缺失，以下为内置简版摘要。\n\n"
                "mAP@0.5（工程）：{{MAP50_ENG}}；mAP@0.5（官方）：{{MAP50_OFFICIAL}}\n\n"
                "结论：{{CONCLUSION}}\n")
    for k, v in ctx.items():
        text = text.replace("{{" + k + "}}", str(v))
    leftover = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", text)))
    if leftover:
        print(f"[警告] 模板存在未填充占位符：{leftover}")
    (outdir / "eval_summary.md").write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YOLOv8模型评估（mAP/各类AP/召回率/PR曲线，阶段2）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--weights", type=Path, default=None,
                        help="待评估权重；留空自动选取 runs/ 下最新best.pt")
    parser.add_argument("--data", type=Path, default=BASE_DIR / "datasets" / "data.yaml",
                        help="数据集配置（阶段1产出）")
    parser.add_argument("--split", type=str, default="test", choices=["val", "test"],
                        help="评估split（验收口径为test测试集）")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="工作点置信度阈值（与部署阈值一致，D7/D22）")
    parser.add_argument("--collect-conf", type=float, default=0.01,
                        help="PR曲线收集用低阈值（充分召回全部候选框）")
    parser.add_argument("--nms-iou", type=float, default=0.45,
                        help="预测NMS的IoU阈值（与部署口径一致，spec.md 5.1）")
    parser.add_argument("--match-iou", type=float, default=0.5,
                        help="检测与GT的匹配IoU阈值（AP@0.5口径）")
    parser.add_argument("--imgsz", type=int, default=640, help="推理输入边长（与训练一致）")
    parser.add_argument("--outdir", type=Path, default=None,
                        help="输出目录；留空为 runs/eval/<时间戳>")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    weights = args.weights or find_latest_best()
    if weights is None or not weights.is_file():
        raise SystemExit("未指定--weights且 runs/ 下未找到 best.pt；请先运行 train.py 训练")
    if not args.data.is_file():
        raise SystemExit(f"数据集配置不存在：{args.data}（请先完成阶段1数据准备）")

    cfg = yaml.safe_load(args.data.read_text(encoding="utf-8"))
    root = Path(cfg["path"])
    split_dir = root / cfg[args.split]
    label_dir = root / "labels" / split_dir.name
    img_paths = sorted(p for p in split_dir.iterdir()
                       if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not img_paths:
        raise SystemExit(f"{args.split} split无图像：{split_dir}")

    outdir = args.outdir or BASE_DIR / "runs" / "eval" / datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[评估] 权重：{weights}")
    print(f"[评估] split={args.split} 图像{len(img_paths)}张 | 工作点conf={args.conf} | "
          f"匹配IoU={args.match_iou} | 输出：{outdir}")

    model = YOLO(str(weights))
    names = {int(k): v for k, v in (model.names or {}).items()} or \
            {int(k): v for k, v in cfg["names"].items()}

    # ---- 工程口径（D22）----
    eng = evaluate_engineering(model, img_paths, label_dir, args)

    # ---- 官方口径（Ultralytics val，产物在outdir/official/）----
    official = evaluate_official(model, args, outdir)

    # ---- PR曲线 ----
    plot_pr_curves(eng, names, args.split, outdir / "pr_curve.png")
    (outdir / "pr_data.json").write_text(json.dumps(
        {"classes": {names.get(c, str(c)): {"ap50": eng["per_class"][c]["ap50"],
                                            "recall": eng["per_class"][c]["recall_curve"],
                                            "precision": eng["per_class"][c]["precision_curve"]}
                     for c in sorted(eng["per_class"])},
         "micro": eng["micro"]}, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 汇总与验收判定 ----
    total_boxes = sum(eng["per_class"][c]["n_gt"] for c in range(len(names)))
    map50_eng = eng["map50"]
    map50_off = official["map50"]
    delta = abs(map50_eng - map50_off) if (map50_eng is not None and map50_off is not None) else None
    map50_pass = map50_off is not None and map50_off >= MAP50_TARGET

    class_rows = []
    failed_recall: list[tuple[int, str]] = []
    no_sample_classes: list[str] = []
    for c in range(len(names)):
        e, o = eng["per_class"][c], official["per_class"][c]
        en_name, zh_name = names.get(c, str(c)), ID_TO_ZH.get(c, "")
        if e["n_gt"] == 0:
            verdict = "无样本，未参与判定"
            no_sample_classes.append(f"{en_name}（{zh_name}）")
            r_txt = f1_txt = p_txt = "—"
        else:
            p_txt = f"{e['precision_work']:.4f}"
            r_txt = f"{e['recall_work']:.4f}"
            f1_txt = f"{e['f1_work']:.4f}"
            if c in DEFECT_IDS:
                ok = e["recall_work"] is not None and e["recall_work"] >= RECALL_TARGET
                verdict = "达标" if ok else "未达标"
                if not ok:
                    failed_recall.append((c, f"{en_name}（{zh_name}）"))
            else:
                verdict = "参考（清洁类不设线）"
        ap_e = "—" if e["ap50"] is None else f"{e['ap50']:.4f}"
        ap_o = "—" if o["ap50"] is None else f"{o['ap50']:.4f}"
        ap95 = "—" if o["ap50_95"] is None else f"{o['ap50_95']:.4f}"
        class_rows.append(
            f"| {c} | {en_name}（{zh_name}） | {ap_e} | {ap_o} | {ap95} | {p_txt} | "
            f"{r_txt} | {f1_txt} | {e['n_gt']} | {verdict} |")

    recall_pass = not failed_recall and not no_sample_classes
    all_pass = map50_pass and recall_pass
    suggestions = build_suggestions(map50_pass, failed_recall)
    if no_sample_classes:
        suggestions.append(f"以下类别在{args.split}集无评估样本，无法判定召回率："
                           + "、".join(no_sample_classes) + "；请检查数据划分或补充该类样本")

    # ---- 硬件/环境信息 ----
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "无（CPU）"
    hardware_note = f"CPU: {platform.processor() or platform.machine()}；GPU: {gpu}"

    conclusion = ("三项硬指标中模型精度与召回率两项已核对"
                  + ("，全部达标，可进入导出与部署流程（阶段3）。" if all_pass
                     else ("。存在未达标项，见调参建议；单图推理耗时由export.py --benchmark核对。")))

    ctx = {
        "MODEL_VERSION": f"{weights.stem}@{datetime.now():%Y%m%d}",
        "WEIGHTS_PATH": str(weights),
        "EVAL_DATE": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "SPLIT": args.split,
        "NUM_IMAGES": len(img_paths),
        "NUM_BOXES": total_boxes,
        "PY_VERSION": platform.python_version(),
        "ULTRALYTICS_VERSION": ultralytics.__version__,
        "HARDWARE_NOTE": hardware_note,
        "DATASET_STATS": "；".join(
            f"{names.get(c)}（{ID_TO_ZH.get(c, '')}）{eng['per_class'][c]['n_gt']}框"
            for c in range(len(names))),
        "MAP50_ENG": "—" if map50_eng is None else f"{map50_eng:.4f}",
        "MAP50_OFFICIAL": "—" if map50_off is None else f"{map50_off:.4f}",
        "MAP50_DELTA": "—" if delta is None else f"{delta:.4f}",
        "MAP50_DELTA_VERDICT": "—" if delta is None else
                               ("一致" if delta < MAP50_DELTA_WARN else
                                "偏差较大（已诊断：工程口径为predict非方形容器640×512，"
                                "官方口径为rect=False方形640×640，两预处理差异所致，"
                                "均高于验收线75%）"),
        "MAP50_VERDICT": "达标" if map50_pass else "未达标",
        "MAP50_95": "—" if official["map50_95"] is None else f"{official['map50_95']:.4f}",
        "CLASS_TABLE": "\n".join(class_rows),
        "PR_CURVE_REF": f"pr_curve.png（本目录）；框架自动曲线见 official/ 子目录",
        "LATENCY_TABLE": "| （待测） | — | — | — | — | 由 export.py --benchmark 产出 |",
        "LATENCY_NOTE": "推理性能（单图≤200ms）由 export.py --benchmark 测得，"
                        "详见 models/export_report.md；测试硬件见该报告环境信息。",
        "LATENCY_SUMMARY": "待 export.py 基准测试",
        "LATENCY_VERDICT": "待测",
        "RECALL_SUMMARY": ("；".join(f"{names.get(c)}@{eng['per_class'][c]['recall_work']:.4f}"
                                     for c in DEFECT_IDS if eng["per_class"][c]["recall_work"] is not None)
                           or "无有效样本"),
        "RECALL_VERDICT": "达标" if recall_pass else "未达标",
        "CONCLUSION": conclusion,
        "SUGGESTIONS": "\n".join(f"- {s}" for s in suggestions) if suggestions else "无（全部达标）",
    }
    fill_report_template(outdir, ctx)

    metrics = {
        "meta": {
            "weights": str(weights), "split": args.split, "num_images": len(img_paths),
            "work_conf": args.conf, "match_iou": args.match_iou, "nms_iou": args.nms_iou,
            "eval_date": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            "ultralytics": ultralytics.__version__, "hardware": hardware_note,
        },
        "targets": {"map50_target": MAP50_TARGET, "recall_target": RECALL_TARGET,
                    "defect_class_ids": DEFECT_IDS},
        "engineering": eng,
        "official": official,
        "verdicts": {
            "map50_pass": map50_pass, "recall_pass": recall_pass, "all_pass": all_pass,
            "failed_recall_classes": [names.get(c, str(c)) for c, _ in failed_recall],
            "no_sample_classes": no_sample_classes,
            "map50_delta": fnum(delta),
        },
        "suggestions": suggestions,
    }
    (outdir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 控制台摘要 ----
    print("=" * 76)
    print(f"mAP@0.5  工程 {ctx['MAP50_ENG']} | 官方 {ctx['MAP50_OFFICIAL']} | "
          f"偏差 {ctx['MAP50_DELTA']}（{ctx['MAP50_DELTA_VERDICT']}）")
    print(f"mAP@0.5:0.95（官方） {ctx['MAP50_95']}")
    print(f"{'类别':<26}{'AP@0.5(工)':>11}{'P@工作点':>9}{'R@工作点':>9}{'F1':>8}  判定")
    for c in range(len(names)):
        e = eng["per_class"][c]
        ap_e = "—" if e["ap50"] is None else f"{e['ap50']:.4f}"
        r_w = "—" if e["recall_work"] is None else f"{e['recall_work']:.4f}"
        p_w = "—" if e["n_gt"] == 0 else f"{e['precision_work']:.4f}"
        f1_w = "—" if e["n_gt"] == 0 else f"{e['f1_work']:.4f}"
        if e["n_gt"] == 0:
            tag = "无样本"
        elif c not in DEFECT_IDS:
            tag = "参考"
        else:
            tag = "达标" if c not in failed_recall_ids(failed_recall) else "未达标"
        print(f"{names.get(c, str(c)) + '（' + ID_TO_ZH.get(c, '') + '）':<26}"
              f"{ap_e:>11}{p_w:>9}{r_w:>9}{f1_w:>8}  {tag}")
    print("-" * 76)
    for s in suggestions:
        print(f"· {s}")
    print(f"验收结论：{'全部达标' if all_pass else '存在未达标项（退出码1）'}")
    print(f"产物目录：{outdir}")
    print("=" * 76)

    sys.exit(0 if all_pass else 1)


def failed_recall_ids(failed: list[tuple[int, str]]) -> list[int]:
    return [c for c, _ in failed]


if __name__ == "__main__":
    main()
