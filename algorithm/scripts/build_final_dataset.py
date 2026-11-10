"""最终数据集重建：人工标注落地后清理并生成训练配置。

清理规则（针对 datasets_fixed，原地删除）：
    1. train 中含类3/4 标签、但不在人工标注清单中的图（未标注/旧标签污染）→ 删图+标签；
    2. 人工标注中 skipped 的图 → 删图+标签；
    3. augm 增强副本中含类3/4 的图（基于旧错误标签生成）→ 删图+标签。

生成（datasets_final/）：
    data_final.yaml            训练配置（train=加权列表, val=images/val）
    images_train_final.txt     训练图列表（类3/4 图重复一次过采样）

输出：datasets_final/build_report.txt
"""

import shutil
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "datasets_fixed"
OUT = BASE / "datasets_final"
ANN_DIR = BASE / "datasets_refine" / "annotate_manual"
TODO = BASE / "datasets_refine" / "annotate_todo_final.txt"
SPLITS = ("train", "val", "test")


def manual_stems() -> set[str]:
    stems = set()
    if TODO.exists():
        for line in TODO.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            stems.add(Path(line.split("\t")[0]).stem)
    for xml in (ANN_DIR / "redo").glob("*.xml"):
        stems.add(xml.stem)
    return stems


def box_classes(label_path: Path) -> set[int]:
    cls = set()
    if not label_path.exists():
        return cls
    for line in label_path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if p:
            cls.add(int(p[0]))
    return cls


def main() -> None:
    keep = manual_stems()
    print(f"人工标注有效样本: {len(keep)}")

    removed: Counter = Counter()
    for sp in SPLITS:
        img_dir = DATA / "images" / sp
        lbl_dir = DATA / "labels" / sp
        for img in sorted(img_dir.glob("*.jpg")):
            stem = img.stem
            lbl = lbl_dir / f"{stem}.txt"
            cls = box_classes(lbl)
            has_34 = bool(cls & {3, 4})
            reasons = []
            if sp == "train" and has_34 and stem not in keep:
                reasons.append("train未标注")
            if stem.startswith("augm") and has_34:
                reasons.append("augm旧标签副本")
            if not reasons:
                continue
            img.unlink(missing_ok=True)
            lbl.unlink(missing_ok=True)
            for r in reasons:
                removed[r] += 1
    print("删除:", dict(removed))

    # ---- 生成训练配置 ----
    OUT.mkdir(parents=True, exist_ok=True)
    train_imgs = sorted((DATA / "images" / "train").glob("*.jpg"))
    lines = [str(p.relative_to(DATA.parent.parent / "algorithm")) for p in train_imgs]
    # 类3/4 图过采样（重复一次）
    over = []
    for p in train_imgs:
        cls = box_classes(DATA / "labels" / "train" / f"{p.stem}.txt")
        if cls & {3, 4}:
            over.append(str(p.relative_to(DATA.parent.parent / "algorithm")))
    lines += over
    list_path = OUT / "images_train_final.txt"
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    data_yaml = f"""# 光伏面板缺陷检测 · 最终人工标注数据集
path: {BASE.as_posix()}
train: {list_path.name}
val: images/val
test: images/test

nc: 6
names:
  0: Clean
  1: Dusty
  2: Bird-drop
  3: Electrical-damage
  4: Physical-Damage
  5: Snow-Covered
"""
    (OUT / "data_final.yaml").write_text(data_yaml, encoding="utf-8")

    cnt: Counter = Counter()
    for sp in SPLITS:
        for lbl in (DATA / "labels" / sp).glob("*.txt"):
            for c in box_classes(lbl):
                cnt[c] += 1
    report = OUT / "build_report.txt"
    with report.open("w", encoding="utf-8") as f:
        f.write(f"人工标注有效样本: {len(keep)}\n")
        f.write(f"删除统计: {dict(removed)}\n")
        f.write(f"train 图数: {len(train_imgs)}（列表含过采样 {len(lines)} 条）\n")
        f.write(f"train/val/test 框数: {dict(cnt)}\n")
    print(f"train 图数: {len(train_imgs)}，列表: {len(lines)} 条")
    print(f"框数: {dict(cnt)}")
    print(f"配置: {OUT / 'data_final.yaml'}")


if __name__ == "__main__":
    main()
