"""光伏面板缺陷检测系统 · 挑选 50 张人工重标图片清单脚本。

背景：人工重标工作量大，用户要求缩短时间、只随机训练 50 张图片。
      为保证评估口径准确，评估集（val/test）中的电/物理损伤图必须全部重标，
      训练集部分则按数量补足 50 张。

策略：
    1. 读取现有 annotate_todo.txt 的全部待标图（154 张，均含全幅占位框）；
    2. 在源 datasets/images/{train,val,test} 中定位每张图的原 split 归属；
    3. 保留 val（17）+ test（16）全部，从 train（121）中随机抽取 17 张补齐 50；
    4. 输出新的清单 annotate_todo_50.txt（含每张图的 split 与类别来源）与统计信息。

运行示例：
    python scripts/pick_50_annotate.py
    python scripts/pick_50_annotate.py --seed 42
"""

import argparse
import random
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TODO_FILE = BASE_DIR / "datasets_refine" / "annotate_todo.txt"
OUT_FILE = BASE_DIR / "datasets_refine" / "annotate_todo_50.txt"
IMAGES_DIR = BASE_DIR / "datasets" / "images"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def locate_split(stem: str) -> str | None:
    """在源 datasets/images/{train,val,test} 中查找 stem 的归属 split。"""
    for split in ("train", "val", "test"):
        if any((IMAGES_DIR / split / stem).with_suffix(ext).is_file()
               for ext in IMG_EXTS):
            return split
    return None


def split_of(stem: str, val_all: list[str], test_all: list[str],
             train_pick: list[str]) -> str:
    """返回单张图的 split 名称。"""
    if stem in val_all:
        return "val"
    if stem in test_all:
        return "test"
    if stem in train_pick:
        return "train"
    return "?"


def main() -> None:
    parser = argparse.ArgumentParser(description="挑选 50 张人工重标图片清单")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认42）")
    args = parser.parse_args()

    stems = [ln.strip() for ln in TODO_FILE.read_text(encoding="utf-8-sig").splitlines()
             if ln.strip()]

    split_map: dict[str, list[str]] = {"train": [], "val": [], "test": [], "unknown": []}
    for s in stems:
        sp = locate_split(s)
        split_map[sp if sp else "unknown"].append(s)

    print(f"待标图总数: {len(stems)}")
    for sp in ("train", "val", "test", "unknown"):
        print(f"  {sp}: {len(split_map[sp])}")

    # 校验：val/test 数量必须与预期一致（17/16）
    val_all, test_all = split_map["val"], split_map["test"]
    n_train = 50 - len(val_all) - len(test_all)
    if n_train <= 0:
        raise SystemExit(f"val+test 已达 {len(val_all)+len(test_all)} 张，无需从 train 抽取")

    rng = random.Random(args.seed)
    train_pick = rng.sample(sorted(split_map["train"]), n_train)

    picked = sorted(val_all) + sorted(test_all) + sorted(train_pick)
    lines = [f"# 50张人工重标清单（val {len(val_all)} + test {len(test_all)} + train {len(train_pick)}，seed={args.seed}）"]
    lines += [f"{s}\t{split_of(s, val_all, test_all, train_pick)}"
              for s in picked]
    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n清单: {OUT_FILE}")
    print(f"构成: val {len(val_all)} + test {len(test_all)} + train {len(train_pick)}（共 {len(picked)}）")
    print(f"train 抽取: {train_pick}")


if __name__ == "__main__":
    main()
