"""人工标注结果落地：LabelImg XML → datasets_fixed YOLO 标签替换。

输入：datasets_refine/annotate_manual/{Electrical-damage,Physical-Damage}/*.xml
逻辑：
    1. 解析 PascalVOC object（类别名容错：Electrical-damage/Physical-Damage）；
    2. 按图像 stem 定位原 split（datasets_fixed/images/{train,val,test}）；
    3. 像素框 → YOLO 归一化坐标，写入 datasets_fixed/labels/<split>/<stem>.txt（覆盖旧标签）；
    4. 输出落地报告（含无框图清单，供排除决策）。
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import cv2

from pv_classes import class_id_from_name

BASE = Path(__file__).resolve().parent.parent
ANN = BASE / "datasets_refine" / "annotate_manual"
DATA = BASE / "datasets_fixed"
SPLITS = ("train", "val", "test")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def locate_split(stem: str) -> str | None:
    for sp in SPLITS:
        if any((DATA / "images" / sp / stem).with_suffix(ext).is_file()
               for ext in IMAGE_EXTS):
            return sp
    return None


def parse_xml(xml_path: Path) -> list[tuple[int, float, float, float, float]]:
    root = ET.parse(xml_path).getroot()
    boxes = []
    for obj in root.iter("object"):
        name = (obj.findtext("name") or "").strip()
        try:
            cid = class_id_from_name(name)
        except ValueError:
            continue
        box = obj.find("bndbox")
        if box is None:
            continue
        boxes.append((cid, float(box.findtext("xmin")), float(box.findtext("ymin")),
                      float(box.findtext("xmax")), float(box.findtext("ymax"))))
    return boxes


def main() -> None:
    xmls = sorted(ANN.rglob("*.xml"))
    if not xmls:
        raise SystemExit(f"未找到任何XML：{ANN}")
    written, skipped, no_split, no_box, bad_img = [], [], [], [], []

    for xml in xmls:
        stem = xml.stem
        boxes = parse_xml(xml)
        split = locate_split(stem)
        if split is None:
            no_split.append(stem)
            continue
        if not boxes:
            no_box.append(stem)
            continue
        img = next((DATA / "images" / split / stem).with_suffix(e)
                   for e in IMAGE_EXTS
                   if (DATA / "images" / split / stem).with_suffix(e).is_file())
        im = cv2.imread(str(img))
        if im is None:
            bad_img.append(stem)
            continue
        h, w = im.shape[:2]
        lines = []
        for cid, xmin, ymin, xmax, ymax in boxes:
            xmin = min(max(xmin, 0.0), float(w))
            xmax = min(max(xmax, 0.0), float(w))
            ymin = min(max(ymin, 0.0), float(h))
            ymax = min(max(ymax, 0.0), float(h))
            bw, bh = xmax - xmin, ymax - ymin
            if bw <= 0 or bh <= 0:
                continue
            cx, cy = (xmin + xmax) / 2 / w, (ymin + ymax) / 2 / h
            lines.append(f"{cid} {cx:.6f} {cy:.6f} {bw / w:.6f} {bh / h:.6f}")
        if not lines:
            no_box.append(stem)
            continue
        out = DATA / "labels" / split / f"{stem}.txt"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(stem)

    report = BASE / "datasets_refine" / "manual_apply_report.txt"
    with report.open("w", encoding="utf-8") as f:
        f.write(f"落地标签: {len(written)} 张\n")
        f.write(f"无框跳过: {len(no_box)} 张 -> {no_box}\n")
        f.write(f"找不到split: {len(no_split)} 张 -> {no_split}\n")
        f.write(f"读图失败: {len(bad_img)} 张 -> {bad_img}\n")
    print(f"落地标签: {len(written)} 张")
    print(f"无框跳过: {len(no_box)} 张")
    print(f"找不到split: {len(no_split)} 张")
    print(f"读图失败: {len(bad_img)} 张")
    print(f"报告: {report}")


if __name__ == "__main__":
    main()
