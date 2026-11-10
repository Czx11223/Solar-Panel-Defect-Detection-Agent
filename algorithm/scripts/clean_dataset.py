"""光伏面板缺陷检测系统 · 数据集清洗与扁平工作区构建脚本。

背景：datasets/ 三个 split（train/val/test）由旧标签体系（含60-100%全幅占位框）
      划分而成，且 md5 查重发现 train/val/test 之间存在重复图像、test 内部重复、
      增强样本大量复制等问题（见 docs/model_eval_diag.md 2.3 节）。

功能：
    1. 合并：将 datasets/images|labels/{train,val,test} 按图像内容去重后合并为
       扁平工作区 datasets_refine/images + labels（供 LabelImg 人工修正与
       split_dataset.py 重新划分使用）；
    2. 去重：按图像文件 MD5 分组，保留优先级 test > val > train（评估集必须
       纯净，train 中出现与 test 相同的图属于数据泄漏，删除 train 侧副本）；
       同 split 内部重复仅保留排序第一张；
    3. 排除旧增强样本：默认跳过 augm_* 前缀（其标签继承自全幅框体系，
       重新划分后将基于修正标签重新生成增强，--keep-augm 可保留）；
    4. 成对校验：有图无标签 -> 报告并排除；有标签无图（孤儿标签）-> 报告并删除；
    5. 损坏过滤：cv2.imread 无法解码的图像（含标签）剔除并报告；
    6. 输出清洗报告 datasets_refine/clean_report.txt 与 clean_stats.json，
       记录清洗前后各 split 图像/标签/类别框数量（说明文档数据来源）。

安全设计：默认 --dry-run 只统计与打印计划，不写任何文件；确认后 --apply 执行。
源目录 datasets/ 永不修改，仅选择性拷贝到工作区。

运行环境：Python 3.12+；依赖 opencv-python（解码校验）、numpy。

运行示例：
    python scripts/clean_dataset.py --dry-run        # 预览清洗计划
    python scripts/clean_dataset.py --apply          # 执行清洗并构建工作区
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import cv2

from pv_classes import CLASSES

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
AUG_PREFIX = "augm_"
BASE_DIR = Path(__file__).resolve().parent.parent
# 跨split重复时的保留优先级（数值越小越优先保留）：评估集纯净优先
PRIORITY = {"test": 0, "val": 1, "train": 2}


def file_md5(path: Path, chunk: int = 1 << 20) -> str:
    """分块计算文件MD5，避免大图一次性读入内存。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def count_label_boxes(label_path: Path) -> tuple[int, list[int]]:
    """统计标签文件的目标框总数与各类别框数；损坏/空文件返回0。"""
    n = 0
    per_class = [0] * len(CLASSES)
    try:
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 5:
                n += 1
                try:
                    per_class[int(parts[0])] += 1
                except ValueError:
                    pass
    except OSError:
        pass
    return n, per_class


def main() -> None:
    parser = argparse.ArgumentParser(
        description="数据集清洗（去重/成对/损坏过滤）并构建扁平工作区",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=BASE_DIR / "datasets",
                        help="源数据集根目录（含 images|labels/{train,val,test}）")
    parser.add_argument("--out", type=Path, default=BASE_DIR / "datasets_refine",
                        help="扁平工作区输出根目录")
    parser.add_argument("--splits", default="train,val,test",
                        help="参与合并的split，逗号分隔")
    parser.add_argument("--keep-augm", action="store_true",
                        help="保留 augm_* 旧增强样本（默认排除，修正标签后重新增强）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅统计与打印计划，不写文件（默认开启）")
    parser.add_argument("--apply", action="store_true",
                        help="执行清洗并写入工作区（与--dry-run互斥，--apply优先）")
    args = parser.parse_args()

    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    img_root, lbl_root = args.dataset / "images", args.dataset / "labels"

    # ---- 1. 收集全部候选样本（split, 图像路径, 标签路径）----
    samples: list[tuple[str, Path, Path]] = []
    for sp in splits:
        idir, ldir = img_root / sp, lbl_root / sp
        if not idir.is_dir():
            print(f"[警告] 图像目录不存在，跳过: {idir}")
            continue
        for p in sorted(idir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            if p.name.startswith(AUG_PREFIX) and not args.keep_augm:
                continue
            lbl = ldir / f"{p.stem}.txt"
            samples.append((sp, p, lbl))

    # ---- 2. 成对校验与损坏过滤 ----
    paired, unlabeled, orphan = [], [], []
    label_stems = set()
    for sp in splits:
        ldir = lbl_root / sp
        if ldir.is_dir():
            label_stems.update(p.stem for p in ldir.glob("*.txt"))
    for sp, img, lbl in samples:
        if not lbl.is_file():
            unlabeled.append((sp, img))            # 有图无标签 -> 排除
        else:
            paired.append((sp, img, lbl))
    for sp in splits:
        ldir = lbl_root / sp
        if not ldir.is_dir():
            continue
        img_stems = {p.stem for p in (img_root / sp).iterdir()
                     if p.is_file() and p.suffix.lower() in IMAGE_EXTS}
        for txt in ldir.glob("*.txt"):
            if txt.stem not in img_stems and not (
                    txt.stem.startswith(AUG_PREFIX) and args.keep_augm):
                orphan.append((sp, txt))           # 有标签无图 -> 删除

    damaged = []
    for sp, img, lbl in paired[:]:
        if cv2.imread(str(img)) is None:
            damaged.append((sp, img, lbl))
            paired.remove((sp, img, lbl))

    # ---- 3. 图像内容MD5去重 ----
    md5_groups: dict[str, list[tuple[str, Path, Path]]] = {}
    for sp, img, lbl in paired:
        md5_groups.setdefault(file_md5(img), []).append((sp, img, lbl))

    keep, duplicates = [], []
    for key, group in md5_groups.items():
        if len(group) == 1:
            keep.extend(group)
            continue
        # 排序键：保留优先级 + 文件名，取第一为保留样本，其余入重复清单
        group.sort(key=lambda x: (PRIORITY.get(x[0], 9), x[1].name))
        keep.append(group[0])
        for dup in group[1:]:
            duplicates.append(dup)

    # ---- 4. 工作区重名检测（扁平化后理论不重名，防御性检查）----
    dup_stems: dict[str, list[str]] = {}
    for _sp, img, _lbl in keep:
        dup_stems.setdefault(img.stem, []).append(str(img))
    name_conflicts = {s: v for s, v in dup_stems.items() if len(v) > 1}

    # ---- 5. 汇总统计（清洗后各split/类别框数）----
    after_split_imgs = {sp: 0 for sp in splits}
    after_class_boxes = [0] * len(CLASSES)
    for sp, img, lbl in keep:
        after_split_imgs[sp] += 1
        _n, per = count_label_boxes(lbl)
        for c in range(len(CLASSES)):
            after_class_boxes[c] += per[c]

    before_split_imgs = {sp: sum(1 for s in samples if s[0] == sp) for sp in splits}
    before_class_boxes = [0] * len(CLASSES)
    for sp, img, lbl in samples:
        if lbl.is_file():
            _n, per = count_label_boxes(lbl)
            for c in range(len(CLASSES)):
                before_class_boxes[c] += per[c]

    # ---- 6. 报告与产物 ----
    lines = [
        "数据集清洗报告（去重/成对/损坏过滤）",
        "=" * 60,
        f"清洗模式: {'执行(APPLY)' if args.apply else '预览(DRY-RUN，未写文件)'}",
        "",
        "清洗前（候选样本，已排除旧增强样本）:",
        "  " + "  ".join(f"{sp}={before_split_imgs[sp]}张" for sp in splits),
        f"  总图像: {sum(before_split_imgs.values())}",
        "  清洗前各类别目标框: " + "  ".join(
            f"{en}={before_class_boxes[i]}" for i, (en, _) in enumerate(CLASSES)),
        "",
        "清洗动作:",
        f"  有图无标签(排除): {len(unlabeled)}",
        f"  有标签无图(孤儿,删除): {len(orphan)}",
        f"  损坏图像(剔除): {len(damaged)}",
        f"  重复图像(仅保留最高优先级一份): {len(duplicates)}",
        f"  工作区重名冲突: {len(name_conflicts)}",
        "",
        "清洗后（保留样本）:",
        "  " + "  ".join(f"{sp}={after_split_imgs[sp]}张" for sp in splits),
        f"  总图像: {sum(after_split_imgs.values())}",
        "  清洗后各类别目标框: " + "  ".join(
            f"{en}={after_class_boxes[i]}" for i, (en, _) in enumerate(CLASSES)),
        "",
    ]
    if unlabeled:
        lines += ["未标注图像清单:"] + [f"  {sp}/{p.name}" for sp, p in unlabeled[:100]]
    if orphan:
        lines += ["孤儿标签清单(删除):"] + [f"  {sp}/{t.name}" for sp, t in orphan[:100]]
    if damaged:
        lines += ["损坏图像清单(剔除):"] + [f"  {sp}/{i.name}" for sp, i, _ in damaged[:100]]
    if duplicates:
        lines += ["重复图像清单(仅保留保留优先级最高一份):"]
        for sp, img, _lbl in duplicates[:150]:
            lines.append(f"  {sp}/{img.name}")
        if len(duplicates) > 150:
            lines.append(f"  ...（其余 {len(duplicates)-150} 项略）")
    if name_conflicts:
        lines += ["工作区重名冲突(跳过):"] + [f"  {s}: {v}" for s, v in name_conflicts.items()]

    stats = {
        "description": "数据集清洗统计（源 datasets/ 不受影响，仅选择性拷贝到工作区）",
        "mode": "apply" if args.apply else "dry-run",
        "before": {"per_split_images": before_split_imgs,
                   "total_images": sum(before_split_imgs.values()),
                   "per_class_boxes": {str(i): before_class_boxes[i]
                                       for i in range(len(CLASSES))}},
        "actions": {"unlabeled_excluded": len(unlabeled),
                    "orphan_labels_deleted": len(orphan),
                    "damaged_removed": len(damaged),
                    "duplicates_removed": len(duplicates),
                    "name_conflicts": len(name_conflicts)},
        "after": {"per_split_images": after_split_imgs,
                  "total_images": sum(after_split_imgs.values()),
                  "per_class_boxes": {str(i): after_class_boxes[i]
                                      for i in range(len(CLASSES))}},
    }

    if args.apply:
        (args.out / "images").mkdir(parents=True, exist_ok=True)
        (args.out / "labels").mkdir(parents=True, exist_ok=True)
        for sp, img, lbl in keep:
            if img.stem in name_conflicts:
                continue
            dst_img = args.out / "images" / img.name
            dst_lbl = args.out / "labels" / f"{img.stem}.txt"
            if not dst_img.exists():
                shutil.copy2(img, dst_img)
            if not dst_lbl.exists():
                shutil.copy2(lbl, dst_lbl)
        report_path = args.out / "clean_report.txt"
        stats_path = args.out / "clean_stats.json"
        lines += ["", f"工作区: {args.out}/images + labels（{sum(after_split_imgs.values())}张）"]
        lines += [f"报告: {report_path}", f"统计: {stats_path}"]
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        print("\n".join(lines))
    else:
        print("\n".join(lines))
        print("\n[DRY-RUN] 未写入任何文件；确认无误后运行: python scripts/clean_dataset.py --apply")


if __name__ == "__main__":
    main()
