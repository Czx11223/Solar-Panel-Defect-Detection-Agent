"""光伏面板缺陷检测系统 · 数据集8:1:1分层划分脚本。

功能：
    1. 将 data/images 与 data/labels 成对的样本按类别分层抽样，8:1:1 划分为
       train/val/test（按文件名类别前缀分层，前缀不匹配时回退取标注首框类别）；
    2. 小类别保底：某类图像数 >= 3 时 val/test 各保底1张；不足3张全部进train并告警；
    3. 未标注图像（有图无txt）排除出数据集并写入报告（决策D12）；
    4. 生成 Ultralytics YOLOv8 训练配置 datasets/data.yaml（类别名用英文标识，决策D11）；
    5. 生成 datasets/class_weights.json（训练集类别目标框统计与频率倒数权重）；
    6. 可选 --preview N 抽样生成框叠加预览图（datasets/preview/）；
    7. 输出划分报告 datasets/split_report.txt。

数据集下载地址（注册后免费下载）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+；依赖 opencv-python（仅预览用）。

运行示例：
    python scripts/split_dataset.py
    python scripts/split_dataset.py --img-dir data/images --label-dir data/labels --out datasets --ratio 0.8 0.1 0.1 --seed 42 --preview 12
"""

import argparse
import json
import random
import shutil
from pathlib import Path

import cv2

from pv_classes import BOX_COLORS_BGR, CLASSES, ID_TO_EN, ID_TO_ZH, class_id_from_name

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
BASE_DIR = Path(__file__).resolve().parent.parent


def stem_class_id(stem: str, label_path: Path) -> int | None:
    """按文件名类别前缀分层；前缀不匹配时回退取标注中第一个框的类别。"""
    prefix = stem.split("_", 1)[0]
    try:
        return class_id_from_name(prefix)
    except ValueError:
        pass
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts:
            try:
                return int(parts[0])
            except ValueError:
                return None
    return None


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
    parser = argparse.ArgumentParser(description="数据集8:1:1分层划分并生成YOLO配置")
    parser.add_argument("--img-dir", type=Path, default=BASE_DIR / "data" / "images",
                        help="图像目录（默认 data/images）")
    parser.add_argument("--label-dir", type=Path, default=BASE_DIR / "data" / "labels",
                        help="YOLO标注目录（默认 data/labels）")
    parser.add_argument("--out", type=Path, default=BASE_DIR / "datasets",
                        help="划分输出根目录（默认 datasets）")
    parser.add_argument("--ratio", nargs=3, type=float, default=[0.8, 0.1, 0.1],
                        metavar=("TRAIN", "VAL", "TEST"),
                        help="划分比例，三项之和为1（默认 0.8 0.1 0.1）")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--preview", type=int, default=0,
                        help="抽样生成N张框叠加预览图，0为不生成（默认0）")
    args = parser.parse_args()

    if abs(sum(args.ratio) - 1.0) > 1e-6 or any(r <= 0 for r in args.ratio):
        raise SystemExit(f"划分比例非法：{args.ratio}（三项须均为正数且和为1）")
    if not args.img_dir.is_dir():
        raise SystemExit(f"图像目录不存在：{args.img_dir}（请先运行 organize_dataset.py）")
    if not args.label_dir.is_dir():
        raise SystemExit(f"标注目录不存在：{args.label_dir}（请先运行 convert_labels.py）")

    img_index = {p.stem: p for p in sorted(args.img_dir.iterdir())
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTS}
    label_index = {p.stem: p for p in sorted(args.label_dir.glob("*.txt"))}

    # D12：有图无标注的图像排除出数据集，清单写入报告
    excluded = [s for s in img_index if s not in label_index]
    orphan_labels = [s for s in label_index if s not in img_index]
    paired = [s for s in img_index if s in label_index]

    groups = {}
    unstratifiable = []
    for s in paired:
        cid = stem_class_id(s, label_index[s])
        if cid is None:
            unstratifiable.append(s)
        else:
            groups.setdefault(cid, []).append(s)
    excluded += unstratifiable

    rng = random.Random(args.seed)
    splits = {"train": [], "val": [], "test": []}
    split_class_counts = {sp: {} for sp in splits}
    small_class_warnings = []
    for cid in sorted(groups):
        stems = groups[cid][:]
        rng.shuffle(stems)
        n = len(stems)
        if n < 3:
            splits["train"].extend(stems)
            split_class_counts["train"][cid] = n
            small_class_warnings.append(
                f"{ID_TO_EN[cid]}（{ID_TO_ZH[cid]}）：仅{n}张，全部进入train")
            continue
        n_val = max(1, round(n * args.ratio[1]))
        n_test = max(1, round(n * args.ratio[2]))
        n_train = n - n_val - n_test
        splits["train"].extend(stems[:n_train])
        splits["val"].extend(stems[n_train:n_train + n_val])
        splits["test"].extend(stems[n_train + n_val:])
        split_class_counts["train"][cid] = n_train
        split_class_counts["val"][cid] = n_val
        split_class_counts["test"][cid] = n_test

    for split, stems in splits.items():
        (args.out / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.out / "labels" / split).mkdir(parents=True, exist_ok=True)
        for s in stems:
            shutil.copy2(img_index[s], args.out / "images" / split / img_index[s].name)
            shutil.copy2(label_index[s], args.out / "labels" / split / f"{s}.txt")

    # data.yaml（D11：类别名用英文标识，避免训练日志中文乱码）
    yaml_text = (
        "# 由 split_dataset.py 自动生成，供 Ultralytics YOLOv8 训练使用\n"
        f"path: {args.out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        + "".join(f"  {i}: {en}\n" for i, (en, _zh) in enumerate(CLASSES))
    )
    (args.out / "data.yaml").write_text(yaml_text, encoding="utf-8")

    # class_weights.json：训练集类别目标框统计与频率倒数权重（均值归一为1；无样本类权重为0）
    counts = [0] * len(CLASSES)
    for s in splits["train"]:
        for line in (args.out / "labels" / "train" / f"{s}.txt").read_text(encoding="utf-8").splitlines():
            if line.strip():
                counts[int(line.split()[0])] += 1
    total_boxes = sum(counts)
    inv = [(total_boxes / c) if c else 0.0 for c in counts]
    mean_inv = (sum(inv) / len(CLASSES)) if total_boxes else 1.0
    weights = [round(v / mean_inv, 4) if c else 0.0 for v, c in zip(inv, counts)]
    (args.out / "class_weights.json").write_text(json.dumps({
        "description": "训练集类别目标框统计与加权采样权重；weights=频率倒数并归一化均值为1，count为0的类权重为0",
        "class_names_en": {str(i): en for i, (en, _zh) in enumerate(CLASSES)},
        "class_names_zh": {str(i): zh for i, (_en, zh) in enumerate(CLASSES)},
        "box_counts": {str(i): counts[i] for i in range(len(CLASSES))},
        "total_boxes": total_boxes,
        "weights": {str(i): weights[i] for i in range(len(CLASSES))},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.preview > 0:
        all_pairs = [(sp, s) for sp, stems in splits.items() for s in stems]
        if all_pairs:
            preview_dir = args.out / "preview"
            preview_dir.mkdir(parents=True, exist_ok=True)
            for sp, s in rng.sample(all_pairs, min(args.preview, len(all_pairs))):
                draw_boxes_preview(args.out / "images" / sp / img_index[s].name,
                                   args.out / "labels" / sp / f"{s}.txt",
                                   preview_dir / f"{sp}_{s}_preview.jpg")
            print(f"预览图已生成：{preview_dir}")

    total_split = sum(len(v) for v in splits.values())
    lines = [
        "数据集划分报告（8:1:1 分层抽样）",
        "=" * 40,
        f"参与划分样本：{total_split}（train {len(splits['train'])} / "
        f"val {len(splits['val'])} / test {len(splits['test'])}）",
        f"排除未标注/无法分层样本：{len(excluded)}"
        f"（未标注 {len(excluded) - len(unstratifiable)}，无法分层 {len(unstratifiable)}）",
        f"孤立标注（有txt无图）：{len(orphan_labels)}",
        f"随机种子：{args.seed}",
        "",
        "各split各类别图像数：",
        "  类别                train  val  test",
    ]
    for cid in sorted(groups):
        en = ID_TO_EN[cid]
        tr = split_class_counts["train"].get(cid, 0)
        va = split_class_counts["val"].get(cid, 0)
        te = split_class_counts["test"].get(cid, 0)
        lines.append(f"  {en:<20}{tr:>6}{va:>5}{te:>5}")
    lines += ["", "训练集类别目标框数与加权权重（class_weights.json）："]
    for i, (en, zh) in enumerate(CLASSES):
        lines.append(f"  {i} {en}（{zh}）：框数 {counts[i]}，权重 {weights[i]}")
    if small_class_warnings:
        lines += ["", "小类别告警："] + small_class_warnings
    if excluded:
        lines += ["", f"排除样本清单（{len(excluded)}）："] + excluded[:200]
        if len(excluded) > 200:
            lines.append(f"  ...（其余 {len(excluded) - 200} 项略）")
    if orphan_labels:
        lines += ["", "孤立标注清单："] + orphan_labels[:50]
    report = args.out / "split_report.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"划分完成：train {len(splits['train'])} / val {len(splits['val'])} / "
          f"test {len(splits['test'])}，排除 {len(excluded)}")
    print(f"配置：{args.out / 'data.yaml'}")
    print(f"报告：{report}")


if __name__ == "__main__":
    main()
