"""光伏面板缺陷检测系统 · 全幅占位框扫描与重标清单生成脚本。

背景：历史标注流程中 gen_pseudo_labels.py 为无框数据集生成了整图占位标签
      (cx=0.5, cy=0.5, w=1.0, h=1.0)，训练集约60%、验证/测试集100%均为该类
      全幅框，与真实局部缺陷位置严重不符（见 docs/model_eval_diag.md 根因结论）。

功能：
    1. 遍历 datasets/labels/{train,val,test} 下全部 YOLO txt 标签，逐框识别
       全幅占位框（归一化坐标 cx/cy≈0.5、w/h≈1.0，容差 --tol 默认0.001）；
    2. 按 split 与类别统计全幅框数量（终端表格 + JSON）；
    3. 筛选出"含目标类别（默认电损伤3/物理损伤4）全幅框的图像"生成重标清单
       full_box_list.txt（每行一条图像绝对路径），供 pseudo_refine.py 伪标注
       辅助与人工 LabelImg 修正使用（任务清单第1、2项）。

运行环境：Python 3.12+，标准库实现，无第三方依赖。

运行示例：
    python scripts/scan_full_boxes.py
    python scripts/scan_full_boxes.py --target-classes 3,4 --tol 0.002
"""

import argparse
import json
from pathlib import Path

from pv_classes import CLASSES, ID_TO_EN, ID_TO_ZH

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SPLITS = ("train", "val", "test")
AUG_PREFIX = "augm_"   # 增强样本前缀：其标签继承自全幅框体系，无需人工重标


def is_full_box(cx: float, cy: float, bw: float, bh: float, tol: float) -> bool:
    """判定是否为全幅占位框：中心点与宽高均落在容差范围内。

    YOLO归一化坐标系下全幅框固定为 (0.5, 0.5, 1.0, 1.0)；容差 tol 用于
    兼容标注工具浮点舍入误差（如 0.500000 与 1.000000）。
    """
    return (abs(cx - 0.5) <= tol and abs(cy - 0.5) <= tol
            and abs(bw - 1.0) <= tol and abs(bh - 1.0) <= tol)


def scan_label_file(label_path: Path, tol: float) -> list[int]:
    """解析单个标签文件，返回其中全幅占位框的类别ID列表。"""
    full_ids = []
    try:
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            try:
                cid, cx, cy, bw, bh = int(parts[0]), *(float(v) for v in parts[1:])
            except ValueError:
                continue
            if is_full_box(cx, cy, bw, bh, tol):
                full_ids.append(cid)
    except OSError as exc:
        print(f"  [警告] 无法读取 {label_path.name}: {exc}")
    return full_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="全幅占位框扫描统计与重标清单生成",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=BASE_DIR / "datasets",
                        help="数据集根目录（含 labels/{train,val,test}）")
    parser.add_argument("--splits", default=",".join(DEFAULT_SPLITS),
                        help="待扫描的split，逗号分隔")
    parser.add_argument("--tol", type=float, default=0.001,
                        help="全幅框判定容差（归一化坐标）")
    parser.add_argument("--target-classes", default="3,4",
                        help="需要重新标注的类别ID，逗号分隔（默认电损伤3/物理损伤4）")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="扫描产物输出目录（默认 dataset 根目录）")
    args = parser.parse_args()

    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    targets = {int(c) for c in args.target_classes.split(",") if c.strip()}
    for c in targets:
        if not (0 <= c < len(CLASSES)):
            raise SystemExit(f"非法类别ID: {c}（有效范围 0-{len(CLASSES)-1}）")
    out_dir = args.out_dir or args.dataset
    out_dir.mkdir(parents=True, exist_ok=True)

    # 逐split扫描：stats[split][class_id] = 全幅框数；full_files 记录含全幅框的文件
    stats: dict[str, dict[int, int]] = {}
    full_files: list[tuple[str, Path, list[int]]] = []  # (split, 标签路径, 全幅框类别)
    for sp in splits:
        label_dir = args.dataset / "labels" / sp
        if not label_dir.is_dir():
            print(f"[警告] split 目录不存在，跳过: {label_dir}")
            continue
        per_class = {c: 0 for c in range(len(CLASSES))}
        for txt in sorted(label_dir.glob("*.txt")):
            if txt.stem.startswith(AUG_PREFIX):
                continue  # 增强样本标签由修正后标签重新生成，不入重标清单
            ids = scan_label_file(txt, args.tol)
            if ids:
                for c in ids:
                    per_class[c] += 1
                full_files.append((sp, txt, ids))
        stats[sp] = per_class

    if not stats:
        raise SystemExit("未扫描到任何 split，请检查 --dataset/--splits 路径")

    # ---- 终端统计表 ----
    all_sp = list(stats)
    header = f"{'类别':<22}" + "".join(f"{sp:>10}" for sp in all_sp) + f"{'合计':>10}"
    print("\n" + "=" * (len(header) + 4))
    print("全幅占位框扫描统计")
    print("=" * (len(header) + 4))
    print(header)
    print("-" * len(header))
    grand = {c: 0 for c in range(len(CLASSES))}
    for c, (en, zh) in enumerate(CLASSES):
        row = f"  {c} {en}（{zh}）"
        tot = 0
        for sp in all_sp:
            n = stats[sp][c]
            tot += n
            row += f"{n:>10}"
        grand[c] = tot
        row += f"{tot:>10}"
        print(row)
    print("-" * len(header))
    row = "  合计"
    for sp in all_sp:
        row += f"{sum(stats[sp].values()):>10}"
    row += f"{sum(grand.values()):>10}"
    print(row)

    # ---- 重标清单（含目标类别全幅框的图像）----
    list_lines, list_imgs = [], []
    for sp, txt, ids in full_files:
        if any(c in targets for c in ids):
            # 图像与标签同名，扩展名可能是 jpg/jpeg/png/bmp
            img = None
            for ext in (".jpg", ".jpeg", ".png", ".bmp"):
                cand = args.dataset / "images" / sp / (txt.stem + ext)
                if cand.is_file():
                    img = cand
                    break
            if img is None:
                print(f"  [警告] {sp}/{txt.stem} 有标签但找不到图像，跳过清单")
                continue
            list_lines.append(str(img))
            list_imgs.append(img)

    list_path = out_dir / "full_box_list.txt"
    list_path.write_text("\n".join(list_lines) + ("\n" if list_lines else ""),
                         encoding="utf-8")
    print(f"\n重标清单（含目标类别{ '、'.join(str(c) for c in sorted(targets)) }全幅框的图像）:")
    print(f"  图像数: {len(list_imgs)}")
    print(f"  清单文件: {list_path}")

    # ---- JSON 机器可读统计 ----
    json_path = out_dir / "full_box_scan.json"
    json_path.write_text(json.dumps({
        "description": "全幅占位框扫描统计（cx/cy≈0.5, w/h≈1.0）",
        "tol": args.tol,
        "target_classes": sorted(targets),
        "per_split_per_class": {sp: {str(c): stats[sp][c] for c in range(len(CLASSES))}
                                for sp in all_sp},
        "total_full_boxes": sum(grand.values()),
        "relabel_image_count": len(list_imgs),
        "relabel_list": str(list_path),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON统计: {json_path}")

    # ---- 人工标注工作量提示（按目标类全幅框计数）----
    target_box_total = sum(stats[sp][c] for sp in all_sp for c in targets)
    print(f"\n目标类全幅框总数: {target_box_total}（人工重标工作量参考）")


if __name__ == "__main__":
    main()
