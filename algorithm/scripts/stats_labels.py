"""统计标签集中各类全幅框/局部框分布（诊断辅助脚本）。"""
import sys
from collections import Counter
from pathlib import Path

from pv_classes import CLASSES, ID_TO_EN

BASE_DIR = Path(__file__).resolve().parent.parent


def scan(label_dir: Path) -> dict:
    full = Counter()
    local = Counter()
    total_files = 0
    for txt in sorted(label_dir.glob("*.txt")):
        total_files += 1
        for line in txt.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) != 5:
                continue
            cid = int(p[0])
            w, h = float(p[3]), float(p[4])
            if abs(w - 1.0) < 0.001 and abs(h - 1.0) < 0.001:
                full[cid] += 1
            else:
                local[cid] += 1
    return {"total_files": total_files, "full": full, "local": local}


def main() -> None:
    targets = {
        "data/labels": BASE_DIR / "data" / "labels",
        "datasets/labels/train": BASE_DIR / "datasets" / "labels" / "train",
        "datasets/labels/val": BASE_DIR / "datasets" / "labels" / "val",
        "datasets/labels/test": BASE_DIR / "datasets" / "labels" / "test",
    }
    for name, d in targets.items():
        if not d.is_dir():
            print(f"{name}: 目录不存在")
            continue
        r = scan(d)
        print(f"\n=== {name}（{r['total_files']} 个标签文件）===")
        print(f"{'类':<4}{'全幅框':>8}{'局部框':>8}{'合计':>8}")
        for i, (en, zh) in enumerate(CLASSES):
            print(f"{i} {en:<18}{r['full'].get(i,0):>8}{r['local'].get(i,0):>8}"
                  f"{r['full'].get(i,0)+r['local'].get(i,0):>8}")


if __name__ == "__main__":
    main()
