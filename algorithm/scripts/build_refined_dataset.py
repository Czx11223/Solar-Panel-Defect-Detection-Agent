"""构建修正数据集：AI局部缺陷标签替换全幅占位框，重建划分与增强。

背景（2026-09-29 诊断）：
    data/labels 885 个标签全部为全幅占位框(0.5 0.5 1.0 1.0)，模型学到"整幅图纹理→类别"，
    导致电损伤/物理损伤等局部缺陷召回率不达标。AI已对 154 张电损伤/物理损伤图完成
    局部缺陷标注（139 张有效局部框 + 15 张空标注）。

本脚本流程：
    1. 构建 data/labels_fixed：
       - 非类3/4（Clean/Dusty/Bird-drop/Snow-Covered，713张）→ 复制原标签；
       - 类3/4 中 AI 有效标注的 139 张 → 使用 AI 局部框标签；
       - 类3/4 中无精确标签的 33 张（15空标注 + 18未标注）→ 不写标签（由
         split_dataset.py D12 排除出数据集，避免全幅框污染与评估无GT图）。
    2. 调用 scripts/split_dataset.py 重新 8:1:1 分层划分（seed 42）输出 datasets_fixed；
    3. 调用 scripts/augment.py 对训练集离线增强（类别加权采样，seed 42）；
    4. 输出数据集构成报告 datasets_fixed/build_report.txt。

运行环境：Python 3.12+；依赖同 split_dataset.py / augment.py。

运行示例：
    python scripts/build_refined_dataset.py --aug-count 500
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from pv_classes import CLASSES, class_id_from_name

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = BASE_DIR / "scripts"

EMPTY_ANN = [  # AI 标注为空（无有效局部框）的图（merge_ai_annotations.py 报告）
    "Electrical-damage_Electrical (13)", "Electrical-damage_Electrical (14)",
    "Electrical-damage_Electrical (47)", "Electrical-damage_Electrical (49)",
    "Electrical-damage_Electrical (53)", "Electrical-damage_Electrical (61)",
    "Electrical-damage_Electrical (62)", "Electrical-damage_Electrical (70)",
    "Electrical-damage_Electrical (79)", "Electrical-damage_Electrical (89)",
    "Physical-Damage_Physical (14)", "Physical-Damage_Physical (34)",
    "Physical-Damage_Physical (41)", "Physical-Damage_Physical (49)",
    "Physical-Damage_Physical (63)",
]
DEFECT_PREFIXES = {"Electrical-damage", "Physical-Damage"}


def stem_is_class34(stem: str) -> bool:
    prefix = stem.split("_", 1)[0]
    try:
        return class_id_from_name(prefix) in (3, 4)
    except ValueError:
        return False


def build_labels_fixed(img_dir: Path, lbl_dir: Path, ai_dir: Path,
                       out_dir: Path) -> dict:
    """构建修正标签集，返回统计。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ai_stems = {p.stem: p for p in ai_dir.glob("*.txt")}
    stats = {"total": 0, "ai_used": 0, "excluded": 0, "copied": 0}
    excluded = []

    for img in sorted(img_dir.iterdir()):
        if not img.is_file() or img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
            continue
        stem = img.stem
        src = lbl_dir / f"{stem}.txt"
        if not src.is_file():
            continue
        stats["total"] += 1
        if stem_is_class34(stem) and stem not in ai_stems:
            # 类3/4 无 AI 精确标签（空标注或未标注）→ 排除出数据集
            stats["excluded"] += 1
            excluded.append(stem)
            continue
        if stem in ai_stems:
            shutil.copy2(ai_stems[stem], out_dir / f"{stem}.txt")
            stats["ai_used"] += 1
        else:
            shutil.copy2(src, out_dir / f"{stem}.txt")
            stats["copied"] += 1
    return stats | {"excluded_list": excluded}


def main() -> None:
    parser = argparse.ArgumentParser(description="构建AI修正数据集并重新划分/增强")
    parser.add_argument("--img-dir", type=Path, default=BASE_DIR / "data" / "images")
    parser.add_argument("--label-dir", type=Path, default=BASE_DIR / "data" / "labels")
    parser.add_argument("--ai-label-dir", type=Path,
                        default=BASE_DIR / "datasets_refine" / "labels_ai")
    parser.add_argument("--fixed-label-dir", type=Path, default=BASE_DIR / "data" / "labels_fixed")
    parser.add_argument("--out", type=Path, default=BASE_DIR / "datasets_fixed")
    parser.add_argument("--ratio", nargs=3, type=float, default=[0.8, 0.1, 0.1])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--aug-count", type=int, default=500,
                        help="增强样本生成数量（augment.py --count）")
    args = parser.parse_args()

    if not args.img_dir.is_dir() or not args.label_dir.is_dir():
        raise SystemExit(f"输入目录缺失：{args.img_dir} / {args.label_dir}")
    if not args.ai_label_dir.is_dir():
        raise SystemExit(f"AI标注目录缺失：{args.ai_label_dir}")

    # ---- 1. 构建修正标签集 ----
    if args.fixed_label_dir.is_dir():
        shutil.rmtree(args.fixed_label_dir)
    stats = build_labels_fixed(args.img_dir, args.label_dir, args.ai_label_dir,
                               args.fixed_label_dir)
    print(f"[构建] 标签集：总 {stats['total']} | AI局部框 {stats['ai_used']} | "
          f"复制 {stats['copied']} | 排除(无精确标签) {stats['excluded']}")

    # ---- 2. 重新划分 ----
    if args.out.is_dir():
        shutil.rmtree(args.out)
    split_cmd = [sys.executable, str(SCRIPTS / "split_dataset.py"),
                 "--img-dir", str(args.img_dir),
                 "--label-dir", str(args.fixed_label_dir),
                 "--out", str(args.out),
                 "--ratio", *[str(r) for r in args.ratio],
                 "--seed", str(args.seed)]
    subprocess.run(split_cmd, check=True)

    # ---- 3. 离线增强 ----
    aug_cmd = [sys.executable, str(SCRIPTS / "augment.py"),
               "--dataset", str(args.out),
               "--count", str(args.aug_count),
               "--seed", str(args.seed),
               "--clean"]
    subprocess.run(aug_cmd, check=True)

    # ---- 4. 报告 ----
    report = args.out / "build_report.txt"
    report.write_text(
        "AI修正数据集构建报告\n"
        "========================================\n"
        f"参与样本：{stats['total']}（排除 {stats['excluded']} 张无精确标签类3/4图）\n"
        f"AI局部框标签：{stats['ai_used']} 张\n"
        f"其余类别原标签：{stats['copied']} 张\n"
        f"增强样本数：{args.aug_count}\n"
        f"随机种子：{args.seed}\n"
        "\n排除清单（未标注，无GT，不参与划分）：\n" +
        "\n".join(f"  {s}" for s in stats["excluded_list"]) + "\n",
        encoding="utf-8")
    print(f"报告：{report}")
    print("下一步：python train.py --data datasets_fixed/data.yaml "
          "--name train_refined --epochs 80 --patience 20 --device cpu --workers 0 --batch 8 --cache ram")


if __name__ == "__main__":
    main()
