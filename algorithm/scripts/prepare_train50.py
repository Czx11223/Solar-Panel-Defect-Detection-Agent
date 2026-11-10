"""光伏面板缺陷检测系统 · 组装"仅 50 张训练"的数据集工作区。

背景：用户要求缩短时间，仅随机训练 50 张图片。本脚本在人工完成 50 张
      LabelImg 修正（datasets_refine_50/labels_xml）并执行 convert_labels.py
      转回 YOLO txt 后运行，组装训练/评估数据集：

    训练集 train（50 张，全部来自原 train split，保证评估无泄漏）：
      - 17 张电/物理损伤图：annotate_todo_50.txt 中 train 部分（修正标签）
      - 33 张其他类别图：从原 train 的 Clean/Dusty/Bird-drop/Snow-Covered
        中按 4 类均衡随机抽取（标签为语义正确的全幅框，无需标注）

    评估集 val/test（原清洗后全部，共 84/87 张）：
      - 50 张清单内的电/物理损伤图（val 17 + test 16）用修正标签替换
      - 其余图片标签（全局型缺陷全幅框，语义正确）沿用原标签

前置：1) 人工标注完成 datasets_refine_50/labels_xml
      2) python scripts/convert_labels.py --xml-dir datasets_refine_50/labels_xml \
             --img-dir datasets_refine_50/images --out-dir datasets_refine_50/labels

输出：train50_work/{images,labels}/{train,val,test} + data.yaml

运行示例：
    python scripts/prepare_train50.py
    python scripts/prepare_train50.py --seed 42
"""

import argparse
import random
import shutil
from pathlib import Path

from pv_classes import CLASSES, ID_TO_EN

BASE_DIR = Path(__file__).resolve().parent.parent
REF = BASE_DIR / "datasets_refine"          # 清洗后全量扁平工作区（794 图）
REF50 = BASE_DIR / "datasets_refine_50"     # 50 张人工修正工作区
SRC_SPLIT = BASE_DIR / "datasets" / "images"  # 原 train/val/test 归属
OUT = BASE_DIR / "train50_work"
LIST50 = REF / "annotate_todo_50.txt"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
# 全局型缺陷类别（标签为语义正确的全幅框，可继续使用）
GLOBAL_CLASSES = {0, 1, 2, 5}
# 局部型缺陷类别（需修正标签）
LOCAL_CLASSES = {3, 4}


def locate_split(stem: str) -> str | None:
    for split in ("train", "val", "test"):
        if any((SRC_SPLIT / split / stem).with_suffix(ext).is_file()
               for ext in IMG_EXTS):
            return split
    return None


def img_path_of(base: Path, stem: str) -> Path | None:
    for ext in IMG_EXTS:
        p = base / (stem + ext)
        if p.is_file():
            return p
    return None


def label_first_class(label_path: Path) -> int | None:
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts:
            try:
                return int(parts[0])
            except ValueError:
                return None
    return None


def todo_stems() -> list[str]:
    """读取 50 张重标清单中的图像名（去掉 split 列与注释）。"""
    stems = []
    for ln in LIST50.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            stems.append(ln.split("\t")[0].strip())
    return stems


def main() -> None:
    parser = argparse.ArgumentParser(description="组装仅50张训练的数据集")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not (REF50 / "labels").is_dir() or not any((REF50 / "labels").glob("*.txt")):
        raise SystemExit("datasets_refine_50/labels 为空，请先完成人工标注并运行 convert_labels.py")

    # 前置校验：确认 50 张标签已从全幅占位框修正为局部框
    fullbox_left = 0
    for s in todo_stems():
        lbl = REF50 / "labels" / f"{s}.txt"
        if not lbl.is_file():
            continue
        for line in lbl.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 5:
                _cid, cx, cy, bw, bh = (float(v) for v in parts)
                if abs(cx - 0.5) < 1e-3 and abs(cy - 0.5) < 1e-3 and bw > 0.9 and bh > 0.9:
                    fullbox_left += 1
                    break
    if fullbox_left:
        raise SystemExit(
            f"仍有 {fullbox_left} 张标签为全幅占位框，请先在 LabelImg 中完成修正再运行")

    # 1. 读取 50 张清单（stem -> split）
    todo = todo_stems()
    todo_set = set(todo)
    print(f"50张清单: {len(todo)}")

    # 2. 确定每张图的原 split 归属（用于隔离训练/评估）
    stem_split = {s: locate_split(s) for s in todo_set}
    unknown = [s for s, sp in stem_split.items() if sp is None]
    if unknown:
        raise SystemExit(f"无法定位 split 的图: {unknown}")

    # 3. 训练集 50 张 = 清单中 train 17 张 + 原 train 其他类别随机 33 张
    train17 = sorted(s for s, sp in stem_split.items() if sp == "train")
    if len(train17) != 17:
        print(f"警告: 清单中 train 图 {len(train17)} 张（预期17），继续")

    rng = random.Random(args.seed)
    other_cands: dict[int, list[str]] = {c: [] for c in GLOBAL_CLASSES}
    for p in sorted((SRC_SPLIT / "train").glob("*")):
        if p.suffix.lower() not in IMG_EXTS or p.stem in todo_set:
            continue
        lbl = REF / "labels" / (p.stem + ".txt")
        if not lbl.is_file():
            continue
        cid = label_first_class(lbl)
        if cid in GLOBAL_CLASSES:
            other_cands[cid].append(p.stem)

    need = 50 - len(train17)
    pick_other: list[str] = []
    for cid in sorted(GLOBAL_CLASSES):
        n = need // len(GLOBAL_CLASSES)
        cands = sorted(other_cands[cid])
        if len(cands) < n:
            print(f"  警告: {ID_TO_EN[cid]} 候选仅 {len(cands)} 张，全取")
            n = len(cands)
        pick_other += rng.sample(cands, n)
    # 不足部分从剩余候选补齐
    remain = [s for cid in GLOBAL_CLASSES for s in other_cands[cid]
              if s not in pick_other]
    while len(pick_other) < need and remain:
        pick_other.append(rng.choice(remain))
        remain.remove(pick_other[-1])
    if len(pick_other) < need:
        raise SystemExit(f"其他类别候选不足: 需 {need} 仅 {len(pick_other)}")

    train_set = sorted(train17 + pick_other)
    print(f"训练集: {len(train_set)} 张（清单train {len(train17)} + 其他类别 {len(pick_other)}）")

    # 4. 评估集 = 原 val/test 全部（清洗后 794 张中 split=val/test 的图）
    val_set, test_set = [], []
    for p in sorted(REF.glob("images/*")):
        if p.suffix.lower() not in IMG_EXTS:
            continue
        sp = locate_split(p.stem)
        if sp == "val":
            val_set.append(p.stem)
        elif sp == "test":
            test_set.append(p.stem)
    print(f"评估集: val {len(val_set)} / test {len(test_set)}")

    # 5. 组装输出
    def copy_pair(sp: str, stem: str, label_src: Path) -> None:
        img = img_path_of(REF / "images", stem)
        if img is None:
            raise SystemExit(f"工作区缺图: {stem}")
        (OUT / "images" / sp).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / sp).mkdir(parents=True, exist_ok=True)
        shutil.copy2(img, OUT / "images" / sp / img.name)
        shutil.copy2(label_src, OUT / "labels" / sp / f"{stem}.txt")

    n_fixed = 0
    for sp, stems in (("train", train_set), ("val", val_set), ("test", test_set)):
        for s in stems:
            fixed_label = REF50 / "labels" / f"{s}.txt"
            if fixed_label.is_file():
                copy_pair(sp, s, fixed_label)   # 修正标签优先
                if sp != "train":
                    n_fixed += 1
            else:
                orig_label = REF / "labels" / f"{s}.txt"
                if not orig_label.is_file():
                    raise SystemExit(f"无标签: {s}")
                copy_pair(sp, s, orig_label)

    # 6. data.yaml
    yaml_text = (
        "# 由 prepare_train50.py 生成（仅50张训练，评估集独立）\n"
        f"path: {OUT.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        + "".join(f"  {i}: {en}\n" for i, (en, _zh) in enumerate(CLASSES))
    )
    (OUT / "data.yaml").write_text(yaml_text, encoding="utf-8")

    report = [
        "仅50张训练数据集组装报告",
        "=" * 40,
        f"训练集: {len(train_set)}（电/物理修正 {len(train17)} + 其他类别 {len(pick_other)}，seed={args.seed}）",
        f"评估集: val {len(val_set)} / test {len(test_set)}",
        f"评估集标签替换（清单内电/物理修正）: {n_fixed}",
        "",
        "训练集构成（按类别）:",
    ]
    for cid, (en, _zh) in enumerate(CLASSES):
        cnt = sum(1 for s in train_set
                  if label_first_class(OUT / "labels" / "train" / f"{s}.txt") == cid)
        report.append(f"  {en:<20}{cnt}")
    (OUT / "prepare_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"完成: {OUT}")
    print(f"评估集修正标签替换: {n_fixed} 张")
    print(f"报告: {OUT / 'prepare_report.txt'}")


if __name__ == "__main__":
    main()
