"""光伏面板缺陷检测系统 · LabelImg XML（PascalVOC）转 YOLO txt 标注脚本。

功能：
    1. 解析 data/labels_xml/ 下 LabelImg 保存的 PascalVOC XML 标注；
    2. 像素坐标 (xmin, ymin, xmax, ymax) 转为 YOLO 归一化坐标 (cx, cy, w, h)，
       图像宽高取自 data/images/ 中同名图像的实际尺寸；
    3. 坐标越界自动钳制到 [0,1]，宽/高为 0 的框丢弃并告警；
    4. 类别名按六类映射表转换（大小写、连字符/下划线容错），含未知类别名的文件转换失败；
    5. 输出 data/labels/ 下同名 txt 与转换报告 data/convert_report.txt；
    6. 可选 --preview N 抽样生成检测框叠加图（data/preview/），用于人工核对标注质量。

数据集下载地址（注册后免费下载）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+；依赖 pillow（读图像尺寸）、opencv-python（仅预览用）。

运行示例：
    python scripts/convert_labels.py
    python scripts/convert_labels.py --xml-dir data/labels_xml --img-dir data/images --out-dir data/labels --preview 20
"""

import argparse
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
from PIL import Image

from pv_classes import BOX_COLORS_BGR, CLASSES, ID_TO_EN, class_id_from_name

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
BASE_DIR = Path(__file__).resolve().parent.parent


def parse_voc_objects(xml_path: Path) -> list[tuple[str, float, float, float, float]]:
    """解析单个PascalVOC XML，返回 (类别名, xmin, ymin, xmax, ymax) 列表。"""
    root = ET.parse(xml_path).getroot()
    objects = []
    for obj in root.iter("object"):
        name = (obj.findtext("name") or "").strip()
        box = obj.find("bndbox")
        if box is None:
            raise ValueError("object 节点缺少 bndbox")
        objects.append((
            name,
            float(box.findtext("xmin", "0")),
            float(box.findtext("ymin", "0")),
            float(box.findtext("xmax", "0")),
            float(box.findtext("ymax", "0")),
        ))
    return objects


def voc_to_yolo(w, h, xmin, ymin, xmax, ymax):
    """像素框转归一化框；钳制到图像范围内，退化框（宽/高<=0）返回 None。"""
    xmin = min(max(xmin, 0.0), float(w))
    xmax = min(max(xmax, 0.0), float(w))
    ymin = min(max(ymin, 0.0), float(h))
    ymax = min(max(ymax, 0.0), float(h))
    bw, bh = xmax - xmin, ymax - ymin
    if bw <= 0 or bh <= 0:
        return None
    return (xmin + xmax) / 2 / w, (ymin + ymax) / 2 / h, bw / w, bh / h


def draw_boxes_preview(image_path: Path, label_path: Path, out_path: Path) -> None:
    """在图像上叠加YOLO框并保存预览图。cv2无法渲染中文，预览标签使用英文标识。"""
    img = cv2.imread(str(image_path))
    if img is None:
        return
    h, w = img.shape[:2]
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        cid, cx, cy, bw, bh = int(parts[0]), *(float(v) for v in parts[1:])
        x1 = int((cx - bw / 2) * w)
        y1 = int((cy - bh / 2) * h)
        x2 = int((cx + bw / 2) * w)
        y2 = int((cy + bh / 2) * h)
        color = BOX_COLORS_BGR[cid]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, ID_TO_EN[cid], (x1, max(12, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.imwrite(str(out_path), img)


def main() -> None:
    parser = argparse.ArgumentParser(description="LabelImg PascalVOC XML 转 YOLO txt")
    parser.add_argument("--xml-dir", type=Path, default=BASE_DIR / "data" / "labels_xml",
                        help="LabelImg标注XML目录（默认 data/labels_xml）")
    parser.add_argument("--img-dir", type=Path, default=BASE_DIR / "data" / "images",
                        help="图像目录（默认 data/images）")
    parser.add_argument("--out-dir", type=Path, default=BASE_DIR / "data" / "labels",
                        help="YOLO txt输出目录（默认 data/labels）")
    parser.add_argument("--preview", type=int, default=0,
                        help="抽样生成N张框叠加预览图，0为不生成（默认0）")
    parser.add_argument("--preview-dir", type=Path, default=None,
                        help="预览图输出目录（默认 data/preview）")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.xml_dir.is_dir():
        raise SystemExit(f"XML标注目录不存在：{args.xml_dir}（请先用LabelImg完成标注）")
    if not args.img_dir.is_dir():
        raise SystemExit(f"图像目录不存在：{args.img_dir}（请先运行 organize_dataset.py）")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    img_index = {}
    for p in sorted(args.img_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            img_index[p.stem] = p

    xml_files = sorted(args.xml_dir.glob("*.xml"))
    ok = failed = empty = 0
    class_box_counts = {en: 0 for en, _ in CLASSES}
    errors, warnings, empties, converted = [], [], [], []

    for xf in xml_files:
        stem = xf.stem
        img = img_index.get(stem)
        if img is None:
            errors.append(f"{xf.name}: 找不到同名图像，未转换")
            failed += 1
            continue
        try:
            with Image.open(img) as im:
                w, h = im.size
        except Exception as exc:
            errors.append(f"{xf.name}: 图像无法读取（{exc}）")
            failed += 1
            continue
        try:
            objects = parse_voc_objects(xf)
        except Exception as exc:
            errors.append(f"{xf.name}: XML解析失败（{exc}）")
            failed += 1
            continue

        lines_out = []
        bad_name = None
        for name, xmin, ymin, xmax, ymax in objects:
            try:
                cid = class_id_from_name(name)
            except ValueError as exc:
                bad_name = f"{xf.name}: {exc}"
                break
            box = voc_to_yolo(w, h, xmin, ymin, xmax, ymax)
            if box is None:
                warnings.append(f"{xf.name}: 类别[{name}]的框宽或高为0，已丢弃")
                continue
            cx, cy, bw, bh = box
            lines_out.append(f"{cid} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            class_box_counts[CLASSES[cid][0]] += 1
        if bad_name is not None:
            errors.append(bad_name)
            failed += 1
            continue

        if not objects:
            empty += 1
            empties.append(xf.name)
        label_path = args.out_dir / f"{stem}.txt"
        label_path.write_text("\n".join(lines_out) + ("\n" if lines_out else ""),
                              encoding="utf-8")
        ok += 1
        converted.append((img, label_path))

    xml_stems = {xf.stem for xf in xml_files}
    unannotated = sorted(s for s in img_index if s not in xml_stems)

    if args.preview > 0 and converted:
        preview_dir = args.preview_dir or (args.out_dir.parent / "preview")
        preview_dir.mkdir(parents=True, exist_ok=True)
        rng = random.Random(args.seed)
        for img, lbl in rng.sample(converted, min(args.preview, len(converted))):
            draw_boxes_preview(img, lbl, preview_dir / f"{img.stem}_preview.jpg")
        print(f"预览图已生成：{preview_dir}")

    lines = [
        "标注转换报告（LabelImg XML -> YOLO txt）",
        "=" * 40,
        f"转换成功：{ok}（其中空标注 {empty}）",
        f"转换失败：{failed}",
        f"未标注图像（有图无XML，需回LabelImg补标）：{len(unannotated)}",
        "",
        "各类别目标框总数：",
    ]
    for en, zh in CLASSES:
        lines.append(f"  {en}（{zh}）：{class_box_counts[en]}")
    if warnings:
        lines += ["", f"告警（{len(warnings)}条）："] + warnings[:50]
    if errors:
        lines += ["", f"错误（{len(errors)}条）："] + errors[:50]
    if empties:
        lines += ["", "空标注文件清单："] + empties[:50]
    if unannotated:
        lines += ["", "未标注图像清单："] + unannotated[:200]
        if len(unannotated) > 200:
            lines.append(f"  ...（其余 {len(unannotated) - 200} 项略）")
    report = args.out_dir.parent / "convert_report.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"转换成功 {ok}，失败 {failed}，空标注 {empty}，未标注图像 {len(unannotated)}")
    print(f"报告：{report}")


if __name__ == "__main__":
    main()
