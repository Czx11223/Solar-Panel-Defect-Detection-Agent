"""光伏面板缺陷检测系统 · 伪标注辅助脚本（人工重标前的模型预标注）。

背景：datasets/ 中电损伤/物理损伤类存在 369 张全幅占位框标签图像
      （清单 datasets/full_box_list.txt，见 scan_full_boxes.py），需要人工
      在 LabelImg 中修正为局部缺陷框。本脚本用当前最优模型对清单内图像推理，
      预生成局部检测框，人工只需调整框位置/类别而非从零绘制，显著降低工作量。

功能：
    1. 逐张推理：YOLO predict（conf=--conf 默认0.25，NMS IoU=0.45，imgsz=640，
       与部署推理参数一致），收集全部检测框（按置信度降序）；
    2. 三重输出（写入工作区 datasets_refine/，与 clean_dataset.py 共用）：
       a. labels/<stem>.txt     YOLO 归一化格式（覆盖原全幅占位框，作为修正底稿）；
       b. labels_xml/<stem>.xml PascalVOC 格式（LabelImg 可直接加载，人工仅需
                               删错框/改类别/微调位置，无需从零绘制）；
       c. preview/<stem>.jpg    检测框叠加预览图（含类别与置信度文字，快速浏览用）；
    3. 核对报告 pseudo_refine_report.txt：逐张列出"原始类别(文件名前缀) vs
       模型预测类别集合"，类别不一致的图像重点提示人工核对（模型对局部缺陷
       存在类别混淆，见 docs/model_eval_diag.md 2.2 节，框位置可参考、类别需确认）；
    4. 无检测输出的图像写入空标签并单独提示（需人工从零标注）。

运行环境：Python 3.12+；依赖 ultralytics、opencv-python、numpy。

运行示例：
    python scripts/pseudo_refine.py
    python scripts/pseudo_refine.py --weights runs/detect/train3/weights/best.pt
    python scripts/pseudo_refine.py --conf 0.15 --device cpu
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
from ultralytics import YOLO

from pv_classes import CLASSES, ID_TO_EN

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def find_latest_best() -> Path:
    """定位 runs/ 下最新的 best.pt（按文件修改时间）。"""
    cands = [p for p in (BASE_DIR / "runs").rglob("best.pt") if p.is_file()]
    if not cands:
        raise SystemExit("未找到 best.pt，请先完成训练（runs/ 下无模型权重）")
    return max(cands, key=lambda p: p.stat().st_mtime)


def write_voc_xml(img_path: Path, xml_path: Path,
                  boxes: list[tuple[int, float, float, float, float]]) -> None:
    """把模型检测框写成 PascalVOC XML（LabelImg 可加载格式）。

    boxes 元素：(class_id, cx, cy, w, h) 归一化坐标；像素框由图像尺寸还原，
    LabelImg 打开后自动显示预置框，人工可直接拖拽调整。
    """
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    parts = [
        "<annotation>",
        "  <folder>images</folder>",
        f"  <filename>{img_path.name}</filename>",
        "  <size>",
        f"    <width>{w}</width>",
        f"    <height>{h}</height>",
        "    <depth>3</depth>",
        "  </size>",
        "  <segmented>0</segmented>",
    ]
    for cid, cx, cy, bw, bh in boxes:
        x1 = int(round((cx - bw / 2) * w))
        y1 = int(round((cy - bh / 2) * h))
        x2 = int(round((cx + bw / 2) * w))
        y2 = int(round((cy + bh / 2) * h))
        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        parts += [
            "  <object>",
            f"    <name>{ID_TO_EN[cid]}</name>",
            "    <pose>Unspecified</pose>",
            "    <truncated>0</truncated>",
            "    <difficult>0</difficult>",
            "    <bndbox>",
            f"      <xmin>{x1}</xmin>",
            f"      <ymin>{y1}</ymin>",
            f"      <xmax>{x2}</xmax>",
            f"      <ymax>{y2}</ymax>",
            "    </bndbox>",
            "  </object>",
        ]
    parts.append("</annotation>")
    xml_path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def draw_preview(img_path: Path, boxes: list[tuple[float, int, tuple]],
                 out_path: Path) -> None:
    """检测框叠加预览图：彩色框 + 类别英文名 + 置信度。"""
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    colors = [(80, 200, 80), (0, 200, 255), (0, 120, 255),
              (0, 0, 255), (255, 0, 200), (255, 255, 255)]
    for conf, cid, box in boxes:
        x1, y1, x2, y2 = (int(v) for v in box)
        cv2.rectangle(img, (x1, y1), (x2, y2), colors[cid], 2)
        label = f"{ID_TO_EN[cid]} {conf:.2f}"
        cv2.putText(img, label, (x1, max(14, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[cid], 2)
    cv2.imwrite(str(out_path), img)


def stem_class(stem: str) -> str:
    """从文件名类别前缀解析英文类别名（与数据集命名一致）。"""
    return stem.split("_", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="伪标注辅助：模型对重标清单图像预生成局部缺陷框",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--weights", type=Path, default=None,
                        help="模型权重（默认自动选取 runs/ 下最新 best.pt）")
    parser.add_argument("--list", type=Path, default=BASE_DIR / "datasets" / "full_box_list.txt",
                        help="重标清单（scan_full_boxes.py 输出，每行一条图像绝对路径）")
    parser.add_argument("--out", type=Path, default=BASE_DIR / "datasets_refine",
                        help="工作区根目录（labels/labels_xml/preview 均位于其下）")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="推理置信度阈值（与部署一致）")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU 阈值")
    parser.add_argument("--imgsz", type=int, default=640, help="推理输入边长")
    parser.add_argument("--device", type=str, default=None,
                        help="推理设备：留空自动（cuda可用则GPU），可传cpu")
    parser.add_argument("--max-det", type=int, default=20,
                        help="单图最多保留检测框数（人工修正参考，无需全量）")
    parser.add_argument("--max-fullbox", type=float, default=0.9,
                        help="近全幅框过滤阈值：归一化宽或高超过该值的框视为"
                             "全幅占位框剔除（模型对局部缺陷图常输出整图框，"
                             "无位置参考价值且会误导人工；0则不过滤）")
    args = parser.parse_args()

    weights = args.weights or find_latest_best()
    if not Path(weights).is_file():
        raise SystemExit(f"权重不存在: {weights}")
    if not args.list.is_file():
        raise SystemExit(f"重标清单不存在: {args.list}（先运行 scan_full_boxes.py）")

    img_paths = [Path(p) for p in
                 args.list.read_text(encoding="utf-8").splitlines() if p.strip()]
    img_paths = [p for p in img_paths if p.is_file()]
    if not img_paths:
        raise SystemExit("清单中没有可用的图像路径")

    # 仅处理工作区中存在的图像（清洗可能已删除重复图，如 test/(83) 与 (75) 重复）
    img_dir = args.out / "images"
    skipped = [p.name for p in img_paths if not (img_dir / p.name).is_file()]
    if skipped:
        print(f"[跳过] 工作区中不存在的图像 {len(skipped)} 张: {skipped[:10]}{'...' if len(skipped) > 10 else ''}")
        img_paths = [p for p in img_paths if (img_dir / p.name).is_file()]
    if not img_paths:
        raise SystemExit("工作区中没有可用的重标图像（请先运行 clean_dataset.py --apply）")
    print(f"加载模型: {weights}")
    model = YOLO(str(weights))

    img_dir = args.out / "images"
    lbl_dir = args.out / "labels"
    xml_dir = args.out / "labels_xml"
    prev_dir = args.out / "preview"
    for d in (lbl_dir, xml_dir, prev_dir):
        d.mkdir(parents=True, exist_ok=True)
    # LabelImg 类别预置文件（若已有则跳过）
    predefined = args.out / "predefined_classes.txt"
    if not predefined.is_file():
        predefined.write_text("\n".join(en for en, _ in CLASSES) + "\n", encoding="utf-8")

    report_lines = [
        "伪标注核对报告（模型预标注 -> 人工LabelImg修正）",
        "=" * 70,
        f"权重: {weights}",
        f"参数: conf={args.conf} iou={args.iou} imgsz={args.imgsz}",
        f"图像数: {len(img_paths)}",
        "",
        "说明：模型对局部缺陷存在类别混淆，框位置可作参考，"
        "类别务必人工确认；",
        "      类别不一致的图像已在下方以 [类别不一致] 标记，优先核对。",
        "",
    ]
    n_box_total = 0
    n_empty = 0
    n_mismatch = 0
    summary: dict[str, list] = {"matched": [], "mismatched": [], "empty": []}

    for i, img_path in enumerate(img_paths, 1):
        orig_cls = stem_class(img_path.stem)
        r = model.predict(str(img_path), conf=args.conf, iou=args.iou,
                          imgsz=args.imgsz, device=args.device,
                          max_det=args.max_det, verbose=False)[0]
        h, w = r.orig_shape
        boxes = []          # (cid, cx, cy, bw, bh) 归一化
        boxes_draw = []     # (conf, cid, (x1,y1,x2,y2)) 像素，供预览
        n_filtered = 0
        for conf, cid, xyxy in zip(r.boxes.conf.tolist(), r.boxes.cls.tolist(),
                                   r.boxes.xyxy.tolist()):
            cid = int(cid)
            x1, y1, x2, y2 = xyxy
            cx = (x1 + x2) / 2 / w
            cy = (y1 + y2) / 2 / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            # 近全幅框剔除：模型对局部缺陷图常输出整图框，无位置参考价值
            if args.max_fullbox > 0 and (bw > args.max_fullbox or bh > args.max_fullbox):
                n_filtered += 1
                continue
            boxes.append((cid, cx, cy, bw, bh))
            boxes_draw.append((float(conf), cid, (x1, y1, x2, y2)))

        lbl_path = lbl_dir / f"{img_path.stem}.txt"
        xml_path = xml_dir / f"{img_path.stem}.xml"
        prev_path = prev_dir / f"{img_path.stem}_preview.jpg"

        # 写入YOLO底稿（覆盖全幅占位框）
        lines = [f"{c} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}" for c, cx, cy, bw, bh in boxes]
        lbl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        if not boxes:
            # 无局部框（模型无输出或全部为近全幅框被过滤）：写空XML，人工从零标注
            write_voc_xml(img_path, xml_path, [])
            draw_preview(img_path, [], prev_path)
            n_empty += 1
            summary["empty"].append(img_path.stem)
            reason = f"（模型输出{n_filtered}个近全幅框已过滤）" if n_filtered else "（模型无输出）"
            report_lines.append(f"[无局部框] {img_path.stem}（原类 {orig_cls}）：{reason}"
                                "需人工从零标注")
            continue

        write_voc_xml(img_path, xml_path, boxes)
        draw_preview(img_path, boxes_draw, prev_path)
        n_box_total += len(boxes)

        det_classes = sorted({c for c, *_ in boxes})
        det_names = ",".join(ID_TO_EN[c] for c in det_classes)
        orig_id = next((i for i, (en, _) in enumerate(CLASSES) if en == orig_cls), None)
        matched = orig_id in det_classes
        tag = "OK" if matched else "[类别不一致]"
        if not matched:
            n_mismatch += 1
            summary["mismatched"].append(img_path.stem)
        else:
            summary["matched"].append(img_path.stem)
        report_lines.append(
            f"{tag} {img_path.stem}  原类={orig_cls:<18} 模型框({len(boxes)}): {det_names}")

        if i % 50 == 0:
            print(f"  已处理 {i}/{len(img_paths)}")

    report_lines += [
        "",
        "=" * 70,
        f"汇总: 图像 {len(img_paths)} | 保留局部框 {n_box_total} | "
        f"类别一致 {len(summary['matched'])} | 类别不一致 {n_mismatch} | 无局部框 {n_empty}",
        "",
        "重要说明（2026-09-18 诊断结论）:",
        "  当前模型对电/物理损伤局部缺陷图几乎只输出近全幅框（normW/H≈1.0，",
        "  conf=0.001 低阈值下亦如此），位置参考价值低，本脚本已默认过滤",
        "  （--max-fullbox 0.9）；预置框如被过滤则该图为空标注，",
        "  需人工依据图像内容从零绘制局部缺陷框。",
        "",
        "人工修正步骤:",
        "  1. 打开LabelImg: 打开目录=datasets_refine/images, 保存目录=datasets_refine/labels_xml",
        "  2. 打开图像后如可见预置框（模型输出的局部框），删错框/改类别/拖拽调整；",
        "     空标注图需自行绘制缺陷框",
        "  3. 保存XML（Ctrl+S），全部完成后运行:",
        "     python scripts/convert_labels.py --xml-dir datasets_refine/labels_xml "
        "--img-dir datasets_refine/images --out-dir datasets_refine/labels",
    ]
    report_path = args.out / "pseudo_refine_report.txt"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    (args.out / "pseudo_refine_stats.json").write_text(json.dumps({
        "weights": str(weights),
        "conf": args.conf,
        "total_images": len(img_paths),
        "total_boxes": n_box_total,
        "matched": len(summary["matched"]),
        "mismatched": n_mismatch,
        "empty": n_empty,
        "image_list": img_paths and [str(p) for p in img_paths],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n伪标注完成: 图像 {len(img_paths)}，模型框 {n_box_total}，"
          f"类别一致 {len(summary['matched'])}，类别不一致 {n_mismatch}，无检出 {n_empty}")
    print(f"YOLO底稿: {lbl_dir}（可被 split_dataset.py 直接使用）")
    print(f"LabelImg工作区: {xml_dir}（含预置框，人工修正后转回YOLO）")
    print(f"预览图: {prev_dir}")
    print(f"核对报告: {report_path}")


if __name__ == "__main__":
    main()
