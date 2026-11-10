"""光伏面板缺陷检测系统 · 构建 50 张人工标注的 LabelImg 工作区。

从 datasets_refine/（154张待标工作区）中按 annotate_todo_50.txt 清单挑选
50 张（val 17 + test 16 + train 17），复制 images/labels_xml/preview 到
datasets_refine_50/，人工只需在 LabelImg 中标注这 50 张，大幅缩短标注时间。

LabelImg 用法：
    python labelImg  (或 labelImg.exe)
    1. Open Dir     -> datasets_refine_50/images
    2. Change Save Dir -> datasets_refine_50/labels_xml  （预置框自动加载）
    3. 逐张核对/修正框：删错框、改类别、拖拽调整位置
    4. 保存（Ctrl+S），类别名使用 predefined_classes.txt 中的六类英文名

运行示例：
    python scripts/prepare_50_workspace.py
"""

import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC = BASE_DIR / "datasets_refine"
DST = BASE_DIR / "datasets_refine_50"
LIST = BASE_DIR / "datasets_refine" / "annotate_todo_50.txt"


def load_stems() -> list[str]:
    stems = []
    for ln in LIST.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        stem = ln.split("\t")[0].strip()
        if stem:
            stems.append(stem)
    return stems


def main() -> None:
    stems = load_stems()
    print(f"清单图片数: {len(stems)}")

    img_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    missing_any = False
    for sub in ("images", "labels_xml", "preview"):
        (DST / sub).mkdir(parents=True, exist_ok=True)

    n_img = n_xml = n_prev = 0
    for stem in stems:
        img = next((SRC / "images" / (stem + ext)) for ext in img_exts
                   if (SRC / "images" / (stem + ext)).is_file())
        xml = SRC / "labels_xml" / (stem + ".xml")
        prev = SRC / "preview" / (stem + "_preview.jpg")

        if not img.is_file() or not xml.is_file() or not prev.is_file():
            print(f"  缺失: {stem} (img={img.is_file()}, xml={xml.is_file()}, preview={prev.is_file()})")
            missing_any = True
            continue
        shutil.copy2(img, DST / "images" / img.name)
        shutil.copy2(xml, DST / "labels_xml" / xml.name)
        shutil.copy2(prev, DST / "preview" / prev.name)
        n_img += 1
        n_xml += 1
        n_prev += 1

    if missing_any:
        raise SystemExit("存在缺失文件，请先运行 pseudo_refine.py 补全")

    report = DST / "README.txt"
    report.write_text(
        "50张人工重标工作区（val 17 + test 16 + train 17，由 annotate_todo_50.txt 生成）\n"
        f"图片: {n_img}  labels_xml: {n_xml}  preview: {n_prev}\n"
        "LabelImg 用法:\n"
        "  1. Open Dir -> images  (打开图片目录)\n"
        "  2. Change Save Dir -> labels_xml (预置框自动加载)\n"
        "  3. 逐张修正：删错框/改类别/拖位置，保存\n"
        "  4. 完成后运行 convert_labels.py 转回 YOLO txt\n",
        encoding="utf-8",
    )
    print(f"工作区: {DST}")
    print(f"  图片 {n_img} / XML {n_xml} / 预览 {n_prev}")
    print(f"  说明: {report}")


if __name__ == "__main__":
    main()
