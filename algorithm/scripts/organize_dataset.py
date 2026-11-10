"""光伏面板缺陷检测系统 · 数据集目录组织脚本。

功能：
    1. 递归扫描 raw 目录下的6类类别文件夹，收集 jpg/jpeg/png/bmp 图像；
    2. 统一重命名为 "{类别英文标识}_{原文件名}" 并复制（默认）或移动到 data/images/；
    3. 生成 LabelImg 标注配套文件：predefined_classes.txt（类别预置）、annotate_todo.txt（标注任务清单）；
    4. 输出统计报告 data/organize_report.txt。

数据集下载地址（注册后免费下载，解压后将6个类别文件夹放入 data/raw/）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+，标准库实现，无第三方依赖。

运行示例（脚本按自身位置定位 algorithm/ 目录，可在任意工作目录执行）：
    python scripts/organize_dataset.py
    python scripts/organize_dataset.py --raw data/raw --out data --mode copy
"""

import argparse
import shutil
from pathlib import Path

from pv_classes import CLASSES, normalize_key

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
BASE_DIR = Path(__file__).resolve().parent.parent
# 容错类别文件夹名（不区分大小写、连字符/下划线等价） -> 标准英文标识
FOLDER_TO_CLASS = {normalize_key(en): en for en, _ in CLASSES}


def match_class_folder(dir_parts) -> str | None:
    """从图像所在目录层级中找到第一个能匹配六类之一的文件夹名。"""
    for part in dir_parts:
        cls = FOLDER_TO_CLASS.get(normalize_key(part))
        if cls is not None:
            return cls
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="光伏面板数据集目录组织（raw -> data/images 统一命名）")
    parser.add_argument("--raw", type=Path, default=BASE_DIR / "data" / "raw",
                        help="Kaggle原始数据集目录（默认 data/raw）")
    parser.add_argument("--out", type=Path, default=BASE_DIR / "data",
                        help="输出数据目录（默认 data）")
    parser.add_argument("--mode", choices=["copy", "move"], default="copy",
                        help="图像处理方式：copy保留原始数据（默认），move直接移动")
    args = parser.parse_args()

    if not args.raw.is_dir():
        raise SystemExit(f"原始数据目录不存在：{args.raw}")

    images_dir = args.out / "images"
    labels_xml_dir = args.out / "labels_xml"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_xml_dir.mkdir(parents=True, exist_ok=True)

    per_class = {en: [] for en, _ in CLASSES}
    ignored = []

    for p in sorted(args.raw.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in IMAGE_EXTS:
            ignored.append(f"{p.relative_to(args.raw)} （非图像文件：{p.suffix}）")
            continue
        cls = match_class_folder(p.relative_to(args.raw).parts[:-1])
        if cls is None:
            ignored.append(f"{p.relative_to(args.raw)} （所在文件夹无法匹配六类之一）")
            continue
        per_class[cls].append(p)

    used_names = set()
    rename_log = []
    output_files = []
    for en, _zh in CLASSES:
        for src in per_class[en]:
            stem = f"{en}_{src.stem}"
            if stem in used_names:
                k = 1
                while f"{stem}_{k}" in used_names:
                    k += 1
                rename_log.append(f"{src.relative_to(args.raw)} -> {stem}_{k}{src.suffix.lower()}（重名去重）")
                stem = f"{stem}_{k}"
            used_names.add(stem)
            dst = images_dir / f"{stem}{src.suffix.lower()}"
            if args.mode == "copy":
                shutil.copy2(src, dst)
            else:
                shutil.move(str(src), str(dst))
            output_files.append(dst.name)

    (args.out / "predefined_classes.txt").write_text(
        "\n".join(en for en, _ in CLASSES) + "\n", encoding="utf-8")
    (args.out / "annotate_todo.txt").write_text(
        "\n".join(sorted(output_files)) + "\n", encoding="utf-8")

    lines = [
        "光伏面板数据集目录组织报告",
        "=" * 40,
        f"处理方式：{args.mode}",
        f"图像总数：{len(output_files)}",
        "",
        "各类别图像数：",
    ]
    for en, zh in CLASSES:
        lines.append(f"  {en}（{zh}）：{len(per_class[en])}")
    lines += ["", f"忽略文件数：{len(ignored)}"]
    lines += ignored[:50]
    if len(ignored) > 50:
        lines.append(f"  ...（其余 {len(ignored) - 50} 项略）")
    if rename_log:
        lines += ["", "重名去重明细："] + rename_log[:50]
        if len(rename_log) > 50:
            lines.append(f"  ...（其余 {len(rename_log) - 50} 项略）")
    report = args.out / "organize_report.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verb = "复制" if args.mode == "copy" else "移动"
    print(f"图像总数 {len(output_files)}，已{verb}至 {images_dir}")
    print(f"标注配套文件：predefined_classes.txt、annotate_todo.txt")
    print(f"报告：{report}")


if __name__ == "__main__":
    main()
