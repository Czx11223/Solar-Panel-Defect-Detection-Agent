"""为无边界框标注的数据集生成整图伪标签（弱监督方案，替代人工标注）。

每个图像按其所属类别生成一个覆盖全图的检测框：
    class_id 0.5 0.5 1.0 1.0
输出到 data/labels/，与 data/images/ 中图像同名。配合 split_dataset.py 8:1:1 划分。
局限性：模型学习的是面板状态级检测定位，小缺陷精确局部定位能力弱于人工框标注。
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
IMG_DIR = BASE / "data" / "images"
LABEL_DIR = BASE / "data" / "labels"
CLASSES = ["Clean", "Dusty", "Bird-drop", "Electrical-damage", "Physical-Damage", "Snow-Covered"]
ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp"}

LABEL_DIR.mkdir(exist_ok=True)
counts = {c: 0 for c in CLASSES}
ignored = []

for img in sorted(IMG_DIR.iterdir()):
    if img.suffix.lower() not in ALLOWED_SUFFIX:
        continue
    cls = img.stem.split("_", 1)[0]
    if cls not in counts:
        ignored.append(img.name)
        continue
    txt = LABEL_DIR / (img.stem + ".txt")
    txt.write_text(f"{CLASSES.index(cls)} 0.5 0.5 1.0 1.0\n", encoding="utf-8")
    counts[cls] += 1

total = sum(counts.values())
print(f"pseudo labels generated: {total}")
for c in CLASSES:
    print(f"  {c}: {counts[c]}")
if ignored:
    print(f"ignored (unknown prefix): {ignored}")
if total == 0:
    sys.exit("ERROR: no labels generated, check images directory")
