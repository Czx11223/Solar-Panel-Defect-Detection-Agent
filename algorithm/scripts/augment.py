"""光伏面板缺陷检测系统 · 数据增强脚本（含类别加权采样）。

功能：
    1. 对 datasets/images/train 与 labels/train 的原始样本（非 augm_ 前缀）离线增强：
       随机翻转（水平p=0.5、垂直p=0.2）、随机旋转（默认±15°，bbox取旋转后外接框）、
       亮度扰动（alpha 0.8-1.2、beta ±30）、Mosaic 2×2拼接（默认输出640×640）；
    2. 类别加权采样：按目标框类别频率倒数计算单图权重，含稀有类的图像优先被增强，
       缓解六类分布不均；
    3. 增强样本以 augm_ 前缀成对写回 train 目录（决策D13），data.yaml 无需修改；
    4. 输出增强报告 datasets/aug_report.txt（增强前后类别分布对比与生成清单）。

数据集下载地址（注册后免费下载）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+；依赖 opencv-python、numpy。

运行示例：
    python scripts/augment.py --count 200 --clean
    python scripts/augment.py --dataset datasets --count 300 --ops flip,rotate,brightness,mosaic --seed 42
"""

import argparse
import random
from pathlib import Path

import cv2
import numpy as np

from pv_classes import CLASSES

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
AUG_PREFIX = "augm_"
OPS = ("flip", "rotate", "brightness", "mosaic")
BASE_DIR = Path(__file__).resolve().parent.parent


def read_boxes(label_path: Path) -> list[tuple[int, float, float, float, float]]:
    boxes = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 5:
            boxes.append((int(parts[0]), *(float(v) for v in parts[1:])))
    return boxes


def apply_flip(img, boxes, rng):
    """随机水平（p=0.5）/垂直（p=0.2）翻转；二者均未触发时强制水平，避免生成无变化样本。"""
    hflip = rng.random() < 0.5
    vflip = rng.random() < 0.2
    if not (hflip or vflip):
        hflip = True
    if hflip:
        img = cv2.flip(img, 1)
    if vflip:
        img = cv2.flip(img, 0)
    out = []
    for cid, cx, cy, w, h in boxes:
        if hflip:
            cx = 1.0 - cx
        if vflip:
            cy = 1.0 - cy
        out.append((cid, cx, cy, w, h))
    return img, out


def apply_rotate(img, boxes, rng, max_deg):
    """小角度旋转：bbox四角点旋转后取轴对齐外接框，并裁剪到图像范围内。"""
    angle = rng.uniform(-max_deg, max_deg)
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(img, m, (w, h), borderValue=(114, 114, 114))
    out = []
    for cid, cx, cy, bw, bh in boxes:
        x1, y1 = (cx - bw / 2) * w, (cy - bh / 2) * h
        x2, y2 = (cx + bw / 2) * w, (cy + bh / 2) * h
        corners = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
        pts = [(m[0, 0] * px + m[0, 1] * py + m[0, 2],
                m[1, 0] * px + m[1, 1] * py + m[1, 2]) for px, py in corners]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        nx1 = min(max(min(xs), 0.0), float(w))
        nx2 = min(max(max(xs), 0.0), float(w))
        ny1 = min(max(min(ys), 0.0), float(h))
        ny2 = min(max(max(ys), 0.0), float(h))
        if nx2 - nx1 < 1.0 or ny2 - ny1 < 1.0:
            continue
        out.append((cid, (nx1 + nx2) / 2 / w, (ny1 + ny2) / 2 / h,
                    (nx2 - nx1) / w, (ny2 - ny1) / h))
    return rotated, out


def apply_brightness(img, boxes, rng):
    """亮度/对比度线性扰动，标注框不变。"""
    alpha = rng.uniform(0.8, 1.2)
    beta = rng.uniform(-30.0, 30.0)
    return cv2.convertScaleAbs(img, alpha=alpha, beta=beta), boxes


def apply_mosaic(samples, size):
    """4张图2×2拼接：各图缩放至半幅，标签坐标平移合并，越界框裁剪、退化框剔除。"""
    half = size // 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    out = []
    for idx, (img, boxes) in enumerate(samples):
        ox = (idx % 2) * half
        oy = (idx // 2) * half
        canvas[oy:oy + half, ox:ox + half] = cv2.resize(
            img, (half, half), interpolation=cv2.INTER_LINEAR)
        for cid, cx, cy, bw, bh in boxes:
            ncx = (cx * half + ox) / size
            ncy = (cy * half + oy) / size
            nw = bw * half / size
            nh = bh * half / size
            x1 = max(0.0, ncx - nw / 2)
            x2 = min(1.0, ncx + nw / 2)
            y1 = max(0.0, ncy - nh / 2)
            y2 = min(1.0, ncy + nh / 2)
            if x2 - x1 <= 0.0 or y2 - y1 <= 0.0:
                continue
            out.append((cid, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))
    return canvas, out


def save_aug_sample(img_dir: Path, lbl_dir: Path, stem: str, image, boxes) -> str:
    seq = 0
    while (img_dir / f"{AUG_PREFIX}{stem}_{seq:04d}.jpg").exists():
        seq += 1
    name = f"{AUG_PREFIX}{stem}_{seq:04d}"
    cv2.imwrite(str(img_dir / f"{name}.jpg"), image,
                [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    lines = [f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for c, cx, cy, w, h in boxes]
    (lbl_dir / f"{name}.txt").write_text(
        "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description="训练集离线增强（随机翻转/旋转/亮度/Mosaic + 类别加权采样）")
    parser.add_argument("--dataset", type=Path, default=BASE_DIR / "datasets",
                        help="数据集根目录（默认 datasets）")
    parser.add_argument("--count", type=int, default=200,
                        help="生成增强样本数量（默认200）")
    parser.add_argument("--ops", default="flip,rotate,brightness,mosaic",
                        help="增强算子，逗号分隔，可选 flip,rotate,brightness,mosaic")
    parser.add_argument("--rotate-deg", type=float, default=15.0,
                        help="随机旋转最大角度（默认15度）")
    parser.add_argument("--mosaic-size", type=int, default=640,
                        help="Mosaic输出图像边长（默认640）")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true",
                        help="运行前清除既有 augm_ 增强样本（重复运行建议带上）")
    args = parser.parse_args()

    ops = [s.strip() for s in args.ops.split(",") if s.strip()]
    invalid = [o for o in ops if o not in OPS]
    if invalid:
        raise SystemExit(f"不支持的增强算子：{invalid}（可选：{list(OPS)}）")

    img_dir = args.dataset / "images" / "train"
    lbl_dir = args.dataset / "labels" / "train"
    if not img_dir.is_dir() or not lbl_dir.is_dir():
        raise SystemExit(f"训练集目录不存在，请先运行 split_dataset.py：{args.dataset}")

    if args.clean:
        removed = 0
        for p in img_dir.iterdir():
            if p.name.startswith(AUG_PREFIX):
                p.unlink()
                removed += 1
        for p in lbl_dir.iterdir():
            if p.name.startswith(AUG_PREFIX):
                p.unlink()
        if removed:
            print(f"--clean 已清除 {removed} 个既有增强样本")

    items = [(p, lbl_dir / f"{p.stem}.txt") for p in sorted(img_dir.iterdir())
             if not p.name.startswith(AUG_PREFIX)
             and p.suffix.lower() in IMAGE_EXTS
             and (lbl_dir / f"{p.stem}.txt").is_file()]
    if not items:
        raise SystemExit("训练集中没有原始样本（非 augm_），请先完成 split_dataset.py")

    stems = [p.stem for p, _ in items]
    path_by_stem = {p.stem: p for p, _ in items}
    parsed = {p.stem: read_boxes(lbl) for p, lbl in items}

    # 类别加权采样：单图权重 = 其所含类别频率倒数的最大值（含稀有类的图优先被增强）
    counts = [0] * len(CLASSES)
    for boxes in parsed.values():
        for b in boxes:
            counts[b[0]] += 1
    total_boxes = sum(counts) or 1
    inv_freq = [(total_boxes / c) if c else 0.0 for c in counts]
    positive = [w for w in inv_freq if w > 0]
    min_w = min(positive) if positive else 1.0
    weights = [max((inv_freq[b[0]] for b in parsed[s]), default=min_w) for s in stems]

    rng = random.Random(args.seed)
    op_counts = {o: 0 for o in ops}
    gen_counts = [0] * len(CLASSES)
    generated = []

    for _ in range(args.count):
        op = rng.choice(ops)
        if op == "mosaic":
            picked = rng.choices(stems, weights=weights, k=4)
            samples = []
            failed = False
            for s in picked:
                img = cv2.imread(str(path_by_stem[s]))
                if img is None:
                    failed = True
                    break
                samples.append((img, parsed[s]))
            if failed:
                continue
            out_img, out_boxes = apply_mosaic(samples, args.mosaic_size)
            src_stem = picked[0]
        else:
            s = rng.choices(stems, weights=weights, k=1)[0]
            img = cv2.imread(str(path_by_stem[s]))
            if img is None:
                continue
            if op == "flip":
                out_img, out_boxes = apply_flip(img, parsed[s], rng)
            elif op == "rotate":
                out_img, out_boxes = apply_rotate(img, parsed[s], rng, args.rotate_deg)
            else:
                out_img, out_boxes = apply_brightness(img, parsed[s], rng)
            src_stem = s
        name = save_aug_sample(img_dir, lbl_dir, src_stem, out_img, out_boxes)
        op_counts[op] += 1
        for b in out_boxes:
            gen_counts[b[0]] += 1
        generated.append(f"{name}  <-  {src_stem} [{op}]")

    after = [counts[i] + gen_counts[i] for i in range(len(CLASSES))]
    lines = [
        "训练集数据增强报告",
        "=" * 40,
        f"原始样本图像数：{len(items)}",
        f"生成增强样本数：{len(generated)}",
        f"随机种子：{args.seed}",
        "",
        "各算子生成数：" + "，".join(f"{o}={op_counts[o]}" for o in ops),
        "",
        "类别目标框分布（增强前 -> 增强后）：",
    ]
    for i, (en, zh) in enumerate(CLASSES):
        lines.append(f"  {i} {en}（{zh}）：{counts[i]} -> {after[i]}")
    if generated:
        lines += ["", "生成样本清单："] + generated
    report = args.dataset / "aug_report.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"生成增强样本 {len(generated)} 个（" +
          "，".join(f"{o}={op_counts[o]}" for o in ops) + "）")
    print(f"报告：{report}")


if __name__ == "__main__":
    main()
