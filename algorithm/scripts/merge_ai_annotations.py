"""AI标注合并脚本：将 ai_annotations_part{1,2,3}.json 合并为 YOLO 格式标签。

电损伤(3)、物理损伤(4)类由视觉AI逐张定位局部缺陷框。
过滤规则：
- 过小框（w<0.03 或 h<0.03）视为栅线/噪声，丢弃；
- 面积>0.5 的全幅框（整图损伤）仅在其他框不存在时保留一个，
  避免模型再次学到"整图纹理->类别"模式；
- 框坐标钳制到 [0,1]。
输出：datasets_refine/labels_ai/*.txt（与 images 同名），并生成统计报告。
"""
import json
from pathlib import Path

BASE = Path(r"D:\peixunwenjian\2026.9.14-9.28\algorithm\datasets_refine")
PARTS = [BASE / "ai_annotations_part1.json", BASE / "ai_annotations_part2.json", BASE / "ai_annotations_part3.json"]
IMG_DIR = BASE / "images"
OUT_DIR = BASE / "labels_ai"
CLS_MAP = {"Electrical-damage": 3, "Physical-Damage": 4}

MIN_DIM = 0.03
FULLFRAME_AREA = 0.5


def classify(name: str) -> int | None:
    for key, cid in CLS_MAP.items():
        if name.startswith(key):
            return cid
    return None


def main() -> None:
    merged = {}
    for p in PARTS:
        data = json.loads(p.read_text(encoding="utf-8"))
        merged.update(data)
    print(f"合并标注条目: {len(merged)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stats = {"written": 0, "no_img": [], "no_ann": [], "kept": 0, "filtered_small": 0,
             "filtered_fullframe": 0, "class_boxes": {3: 0, 4: 0}}

    for img_name, boxes in merged.items():
        cid = classify(img_name)
        if cid is None:
            continue
        img_path = IMG_DIR / img_name
        if not img_path.exists():
            stats["no_img"].append(img_name)
            continue
        if not boxes:
            stats["no_ann"].append(img_name)
            continue

        kept = []
        for b in boxes:
            cx, cy, w, h = float(b.get("cx", 0)), float(b.get("cy", 0)), float(b.get("w", 0)), float(b.get("h", 0))
            if w < MIN_DIM or h < MIN_DIM:
                stats["filtered_small"] += 1
                continue
            cx, cy = max(0.0, min(1.0, cx)), max(0.0, min(1.0, cy))
            w, h = max(0.0, min(1.0, w)), max(0.0, min(1.0, h))
            if w * h > FULLFRAME_AREA:
                stats["filtered_fullframe"] += 1
                continue
            kept.append((cx, cy, w, h))
        if not kept:
            stats["no_ann"].append(img_name)
            continue

        lines = [f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in kept]
        stem = img_path.stem
        (OUT_DIR / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        stats["kept"] += len(kept)
        stats["class_boxes"][cid] += len(kept)
        stats["written"] += 1

    report = [
        "AI标注合并报告（JSON -> YOLO txt）",
        "=" * 40,
        f"生成标签文件: {stats['written']}",
        f"有效框总数: {stats['kept']}",
        f"  电损伤(3): {stats['class_boxes'][3]}",
        f"  物理损伤(4): {stats['class_boxes'][4]}",
        f"过滤过小框(噪声): {stats['filtered_small']}",
        f"过滤全幅框(>50%面积): {stats['filtered_fullframe']}",
        f"无对应图像: {len(stats['no_img'])} {stats['no_img'][:10]}",
        f"无有效框(含空标注): {len(stats['no_ann'])}",
        "空标注清单（前50）:",
    ] + [f"  {n}" for n in stats["no_ann"][:50]]
    (BASE / "ai_merge_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
