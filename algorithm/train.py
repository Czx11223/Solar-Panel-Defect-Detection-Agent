"""光伏面板缺陷检测系统 · YOLOv8迁移学习训练脚本（阶段2）。

功能：
    1. 迁移学习：加载COCO预训练权重（默认yolov8s.pt，决策D16），输出层自动适配
       数据集类别数（nc由data.yaml解析为6类）；
    2. 数据：读取阶段1产出的 datasets/data.yaml（train/val/test路径 + 六类names）；
    3. 损失：YOLOv8默认联合损失 = box增益×CIoU边框回归 + cls增益×BCE分类损失
       + dfl增益×Distribution Focal Loss（边框分布学习），默认7.5/0.5/1.5；
    4. 优化器：AdamW（默认，决策D17，小数据集收敛快）或SGD（泛化更稳）；
       学习率余弦退火（cos_lr=True）：lr从lr0按余弦曲线平滑衰减至lr0×lrf，
       末期小步长利于精细收敛（--linear-lr可切换线性衰减）；
    5. 早停（防过拟合）：监控验证集fitness = 0.1×mAP@0.5 + 0.9×mAP@0.5:0.95，
       连续patience轮无提升自动停止训练，best.pt保留历史最优权重；
    6. 类别加权过采样（决策D19）：读取阶段1 class_weights.json，含稀有类的图像
       按权重重复进入采样清单（重复因子上限--sample-cap，默认3），
       生成 datasets/images_train_weighted.txt + data_train_weighted.yaml；
    7. 断点续训：--resume 自动定位 runs/ 下最新last.pt继续训练。

前置条件（人工步骤，见 docs/dataset_readme.md）：
    algorithm/datasets/data.yaml 与 class_weights.json 已由阶段1脚本产出。

数据集下载地址（注册后免费下载，人工步骤）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

预训练权重：首次运行时Ultralytics自动从官方源下载 yolov8s.pt（约22MB）至
脚本运行目录；离线环境请手工下载后放置于 algorithm/ 下同名文件。

运行环境：Python 3.12+；PyTorch（GPU/CPU wheel）安装见 requirements.txt 头部注释。

运行示例：
    python train.py                                     # 默认参数（yolov8s + AdamW + 加权采样）
    python train.py --weights yolov8n.pt --batch 4      # CPU/低显存环境
    python train.py --optimizer SGD --lr0 0.01          # 切换SGD优化器
    python train.py --no-weighted-sampling              # 关闭加权过采样
    python train.py --linear-lr                         # 余弦退火切换为线性衰减
    python train.py --resume                            # 断点续训
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import torch
import yaml
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def resolve_default_data() -> Path:
    """定位默认数据集配置，兼容阶段1规范目录与本项目实际产出的目录名。

    阶段1文档约定 datasets/data.yaml；实际交付目录为 datasets_final/ 与
    datasets_fixed/。按优先级探测已存在的文件，避免默认参数直接失效。
    """
    candidates = (
        BASE_DIR / "datasets" / "data.yaml",
        BASE_DIR / "datasets_final" / "data_final.yaml",
        BASE_DIR / "datasets_fixed" / "data.yaml",
    )
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


def build_weighted_yaml(data_yaml: Path, cap: int) -> Path | None:
    """按类别权重生成训练过采样清单与派生data.yaml（决策D19）。

    规则：
        1. 读阶段1 class_weights.json：各类权重 = 训练集目标框频率倒数（均值归一为1），
           稀有类权重>1、多数类权重<1；
        2. 每张训练图重复因子 = clamp(round(图内所含类别的最大权重), 1, cap)：
           含稀有类的图像重复多次进入采样清单，其余图像重复1次；
        3. 输出 datasets/images_train_weighted.txt（重复的图像绝对路径清单，
           Ultralytics按txt行构建样本列表，天然支持重复条目）与
           datasets/data_train_weighted.yaml（train指向txt，val/test不变）。

    返回派生yaml路径；class_weights.json缺失、权重无差异或训练集为空时
    返回None（回退原始data.yaml训练）。
    """
    root = data_yaml.parent
    weights_json = root / "class_weights.json"
    if not weights_json.is_file():
        print(f"[加权采样] 未找到 {weights_json}，回退原始数据集配置")
        return None

    weights = {int(k): float(v) for k, v in
               json.loads(weights_json.read_text(encoding="utf-8"))["weights"].items()}
    if not any(w > 1.05 for w in weights.values()):
        print("[加权采样] 各类权重均接近1（数据均衡或无稀有类），跳过过采样")
        return None

    cfg = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    img_dir = (root / cfg["train"]).resolve()
    # 图像与标注目录约定：images/<split> ↔ labels/<split>（阶段1 split_dataset.py 产出）
    label_dir = root / "labels" / Path(cfg["train"]).name

    lines: list[str] = []
    n_imgs = n_records = 0
    for img in sorted(img_dir.iterdir()):
        if not img.is_file() or img.suffix.lower() not in IMAGE_EXTS:
            continue
        # 图内所含类别的最大权重决定该图被采样的重复次数
        best = 1.0
        label = label_dir / f"{img.stem}.txt"
        if label.is_file():
            for ln in label.read_text(encoding="utf-8").splitlines():
                parts = ln.split()
                if parts:
                    best = max(best, weights.get(int(parts[0]), 1.0))
        factor = max(1, min(cap, round(best)))
        lines.extend([img.resolve().as_posix()] * factor)
        n_imgs += 1
        n_records += factor

    if not lines:
        print("[加权采样] 训练集为空，回退原始数据集配置")
        return None

    txt = root / "images_train_weighted.txt"
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    names = cfg.get("names", {})
    if isinstance(names, list):
        names = {i: n for i, n in enumerate(names)}
    derived = root / "data_train_weighted.yaml"
    derived.write_text(
        "# 由train.py自动生成的加权过采样训练配置（决策D19），勿手工编辑\n"
        f"path: {root.resolve().as_posix()}\n"
        f"train: {txt.resolve().as_posix()}\n"
        f"val: {cfg['val']}\n"
        f"test: {cfg['test']}\n"
        "names:\n" + "".join(f"  {k}: {v}\n" for k, v in names.items()),
        encoding="utf-8",
    )
    print(f"[加权采样] {n_imgs}张原图 → {n_records}条采样记录（重复上限{cap}），"
          f"配置：{derived.name}")
    return derived


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YOLOv8迁移学习训练（光伏面板六类缺陷检测，阶段2）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ---- 模型与数据 ----
    parser.add_argument("--weights", type=str, default="yolov8s.pt",
                        help="预训练权重：yolov8s.pt（默认，D16）/yolov8n.pt/yolov8m.pt；"
                             "首次运行自动下载；传yolov8n.yaml则为随机初始化（仅调试用）")
    parser.add_argument("--data", type=Path, default=resolve_default_data(),
                        help="数据集配置；默认自动探测 datasets/、datasets_final/、datasets_fixed/")

    # ---- 训练调度 ----
    parser.add_argument("--epochs", type=int, default=150,
                        help="最大训练轮数（配合早停通常提前结束）")
    parser.add_argument("--patience", type=int, default=30,
                        help="早停耐心值：验证集fitness连续N轮无提升则停止训练，防过拟合")
    parser.add_argument("--batch", type=int, default=16,
                        help="批大小（显存不足降8，CPU训练建议4）")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="训练输入图像边长（与部署推理一致，须为32的倍数）")
    parser.add_argument("--device", type=str, default=None,
                        help="训练设备：留空自动选择（cuda可用则GPU）；可传cpu/0/0,1")
    parser.add_argument("--workers", type=int, default=8,
                        help="数据加载进程数（Windows下报错可设0）")
    parser.add_argument("--cache", type=str, default="none", choices=["none", "ram", "disk"],
                        help="图像缓存：none不缓存/ram内存缓存（小数据集提速）/disk磁盘缓存")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子（与阶段1脚本一致，保证可复现）")
    parser.add_argument("--project", type=Path, default=BASE_DIR / "runs",
                        help="训练输出根目录")
    parser.add_argument("--name", type=str, default="train",
                        help="本次训练名称（输出目录 runs/<name>N）")
    parser.add_argument("--exist-ok", action="store_true",
                        help="允许复用已存在的输出目录（默认自动递增编号）")
    parser.add_argument("--resume", action="store_true",
                        help="断点续训：自动定位runs/下最新last.pt，忽略其余训练参数")

    # ---- 优化器与学习率 ----
    parser.add_argument("--optimizer", type=str, default="AdamW", choices=["AdamW", "SGD", "auto"],
                        help="优化器（D17）：AdamW小数据集收敛快（默认）；SGD泛化更稳；"
                             "auto由框架按数据规模自动选择")
    parser.add_argument("--lr0", type=float, default=0.001,
                        help="初始学习率（AdamW典型0.001；切SGD建议0.01）")
    parser.add_argument("--lrf", type=float, default=0.01,
                        help="最终学习率系数：最终lr = lr0 × lrf")
    parser.add_argument("--linear-lr", action="store_true",
                        help="关闭余弦退火，改用线性衰减（默认余弦退火cos_lr=True）")
    parser.add_argument("--momentum", type=float, default=0.937,
                        help="SGD动量 / AdamW的β1")
    parser.add_argument("--weight-decay", type=float, default=0.0005,
                        help="L2正则化系数，抑制过拟合")
    parser.add_argument("--warmup-epochs", type=float, default=3.0,
                        help="学习率预热轮数：前几轮从低lr/低动量线性升至设定值，"
                             "保护预训练权重不被初期大梯度破坏")
    parser.add_argument("--warmup-momentum", type=float, default=0.8,
                        help="预热期初始动量")
    parser.add_argument("--warmup-bias-lr", type=float, default=0.1,
                        help="预热期bias参数的初始学习率")

    # ---- 损失增益（YOLOv8联合损失三项权重）----
    parser.add_argument("--box", type=float, default=7.5,
                        help="边框回归损失（CIoU）增益")
    parser.add_argument("--cls", type=float, default=0.5,
                        help="分类损失（BCE）增益")
    parser.add_argument("--dfl", type=float, default=1.5,
                        help="Distribution Focal Loss增益（YOLOv8边框分布学习损失）")
    parser.add_argument("--label-smoothing", type=float, default=0.0,
                        help="标签平滑系数（默认关闭；过拟合时可设0.05–0.1）")

    # ---- 在线数据增强（离线增强已在阶段1完成，D23：关闭在线旋转避免重复）----
    parser.add_argument("--hsv-h", type=float, default=0.015, help="在线色调扰动幅度（0–1）")
    parser.add_argument("--hsv-s", type=float, default=0.7, help="在线饱和度扰动幅度（0–1）")
    parser.add_argument("--hsv-v", type=float, default=0.4, help="在线亮度扰动幅度（0–1）")
    parser.add_argument("--degrees", type=float, default=0.0,
                        help="在线旋转角度（度）；默认0：旋转增强已由阶段1离线完成（D23）")
    parser.add_argument("--translate", type=float, default=0.1, help="在线平移幅度（占图像比例）")
    parser.add_argument("--scale", type=float, default=0.5, help="在线缩放扰动幅度（±比例）")
    parser.add_argument("--fliplr", type=float, default=0.5, help="水平翻转概率")
    parser.add_argument("--flipud", type=float, default=0.0, help="垂直翻转概率（默认关闭）")
    parser.add_argument("--mosaic", type=float, default=1.0, help="Mosaic四图拼接概率（在线增强）")
    parser.add_argument("--close-mosaic", type=int, default=10,
                        help="最后N轮关闭Mosaic，让模型在真实数据分布上完成收敛")
    parser.add_argument("--no-amp", action="store_true",
                        help="关闭混合精度训练（默认开启AMP：FP16加速、约省一半显存）")

    # ---- 类别加权过采样（D19）----
    parser.add_argument("--no-weighted-sampling", action="store_true",
                        help="关闭类别加权过采样（默认开启，读取class_weights.json）")
    parser.add_argument("--sample-cap", type=int, default=3,
                        help="加权过采样的单图重复因子上限（防数据集膨胀与稀有类过拟合）")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ---- 断点续训分支：使用上次训练保存的全部参数，忽略本次CLI其余训练参数 ----
    if args.resume:
        last = max((BASE_DIR / "runs").rglob("last.pt"),
                   key=lambda p: p.stat().st_mtime, default=None)
        if last is None:
            raise SystemExit("未找到可续训的 last.pt（runs/ 下无训练记录）")
        print(f"[续训] 从 {last} 恢复训练")
        YOLO(str(last)).train(resume=True)
        return

    if not args.data.is_file():
        raise SystemExit(
            f"数据集配置不存在：{args.data}\n"
            "请先完成阶段1数据准备（下载Kaggle数据集 + LabelImg标注 + 运行处理脚本，"
            "流程见 docs/dataset_readme.md）")

    # ---- 设备检测：纯CPU环境告警并给出降配建议 ----
    if args.device is None and not torch.cuda.is_available():
        print("[警告] 未检测到CUDA，将使用CPU训练（速度慢）。"
              "建议：--weights yolov8n.pt --batch 4 --workers 0")

    # ---- 类别加权过采样（D19，默认开启）----
    train_data = args.data
    if not args.no_weighted_sampling:
        derived = build_weighted_yaml(args.data, args.sample_cap)
        if derived is not None:
            train_data = derived

    cache_arg = None if args.cache == "none" else args.cache

    model = YOLO(args.weights)
    model.train(
        data=str(train_data),
        epochs=args.epochs,            # 最大轮数（早停监控验证fitness，见patience）
        patience=args.patience,        # 早停：连续N轮验证fitness无提升则停止
        batch=args.batch,              # 批大小
        imgsz=args.imgsz,              # 输入边长（与部署一致）
        optimizer=args.optimizer,      # AdamW/SGD/auto（D17）
        lr0=args.lr0,                  # 初始学习率
        lrf=args.lrf,                  # 最终学习率 = lr0×lrf
        cos_lr=not args.linear_lr,     # 余弦退火调度（默认True）
        momentum=args.momentum,        # 动量/β1
        weight_decay=args.weight_decay,  # L2正则
        warmup_epochs=args.warmup_epochs,       # 预热轮数
        warmup_momentum=args.warmup_momentum,   # 预热初始动量
        warmup_bias_lr=args.warmup_bias_lr,     # 预热bias学习率
        box=args.box,                  # CIoU边框回归损失增益
        cls=args.cls,                  # BCE分类损失增益
        dfl=args.dfl,                  # DFL分布焦点损失增益
        label_smoothing=args.label_smoothing,
        hsv_h=args.hsv_h, hsv_s=args.hsv_s, hsv_v=args.hsv_v,  # 色彩扰动
        degrees=args.degrees,          # 在线旋转（默认0，D23）
        translate=args.translate,      # 平移
        scale=args.scale,              # 缩放
        fliplr=args.fliplr, flipud=args.flipud,  # 翻转
        mosaic=args.mosaic,            # Mosaic在线拼接
        close_mosaic=args.close_mosaic,  # 末N轮关闭Mosaic
        amp=not args.no_amp,           # 混合精度
        cache=cache_arg,               # 图像缓存
        device=args.device,            # None=自动选择
        workers=args.workers,          # DataLoader进程数
        project=str(args.project), name=args.name,
        seed=args.seed,                # 随机种子
        exist_ok=args.exist_ok,
        plots=True,                    # 自动产出损失/mAP曲线、混淆矩阵
        verbose=True,
    )

    # ---- 训练产物摘要 ----
    save_dir = Path(getattr(model.trainer, "save_dir", "")) if model.trainer else None
    print("\n" + "=" * 64)
    print(f"训练完成：{datetime.now():%Y-%m-%d %H:%M:%S}")
    if save_dir:
        best = save_dir / "weights" / "best.pt"
        last = save_dir / "weights" / "last.pt"
        print(f"产物目录：{save_dir}")
        print(f"最优权重：{best}{'（存在）' if best.is_file() else '（未生成）'}")
        print(f"最新权重：{last}{'（存在）' if last.is_file() else '（未生成）'}")
        print(f"训练曲线：{save_dir / 'results.png'}")
        print("下一步：python eval.py  评估测试集（mAP/各类AP/召回率/PR曲线）")
        print("        python export.py --int8 --benchmark  导出ONNX并测延迟")
    print("=" * 64)


if __name__ == "__main__":
    main()
