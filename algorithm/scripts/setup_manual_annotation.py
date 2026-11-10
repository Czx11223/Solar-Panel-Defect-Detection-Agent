"""人工标注准备：生成待标清单并复制图像到标注目录。

标注范围：
    val/test 全部电损伤+物理损伤图；
    train 每类随机抽 40 张（seed=42），其余排除训练集。

输出：
    datasets_refine/annotate_todo_final.txt   待标清单（路径\t类别）
    datasets_refine/annotate_manual/<类>/     待标图像副本
"""

import random
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "datasets_fixed"
OUT_DIR = BASE / "datasets_refine" / "annotate_manual"
TODO = BASE / "datasets_refine" / "annotate_todo_final.txt"
TRAIN_KEEP_PER_CLASS = 40
SEED = 42


def img_stems(split: str, prefix: str) -> list[str]:
    d = DATA / "images" / split
    return sorted(p.stem for p in d.glob(f"{prefix}_*.jpg"))


def main() -> None:
    picks: list[tuple[str, str]] = []   # (绝对路径, 类别名)
    rng = random.Random(SEED)

    for split in ("val", "test", "train"):
        for prefix, cls in (("Electrical-damage", "Electrical-damage"),
                            ("Physical-Damage", "Physical-Damage")):
            stems = img_stems(split, prefix)
            if split == "train":
                stems = rng.sample(stems, min(TRAIN_KEEP_PER_CLASS, len(stems)))
            for s in stems:
                img = DATA / "images" / split / f"{s}.jpg"
                if img.is_file():
                    picks.append((str(img), cls))

    picks.sort()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for img, cls in picks:
        sub = OUT_DIR / cls
        sub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(img, sub / Path(img).name)

    with TODO.open("w", encoding="utf-8") as f:
        f.write(f"# 人工标注待标清单 {len(picks)}张（LabelImg/PascalVOC）\n")
        for img, cls in picks:
            f.write(f"{img}\t{cls}\n")
    print(f"待标总数: {len(picks)}")
    from collections import Counter
    print(Counter(cls for _, cls in picks))
    print(f"图像目录: {OUT_DIR}")
    print(f"清单: {TODO}")


if __name__ == "__main__":
    main()
