# 光伏面板缺陷检测系统 · 数据集修复说明文档

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统（YOLOv8 目标检测） |
| 文档类型 | 数据集修复与训练说明（任务清单交付文档） |
| 编写日期 | 2026-09-18 |
| 关联文档 | model_eval_diag.md（未达标归因）、model_eval_report.md（评估报告模板） |
| 数据集 | Kaggle Solar Panel Images（6 类：清洁/积灰/鸟粪/电损伤/物理损伤/积雪） |

## 1 修复背景

历史标注流程中 `gen_pseudo_labels.py` 为数据集生成了整图占位标签
`(0.5, 0.5, 1.0, 1.0)`，导致：

- 训练集约 60%、验证/测试集 100% 的标签为全幅占位框，与实际局部缺陷位置不符；
- 模型学习到"整幅图纹理 → 类别"的全局模式，对电损伤热斑、物理损伤裂纹等
  **局部缺陷**输出类别混淆（电损伤→鸟粪、物理损伤→清洁），工程口径下
  电损伤召回率 0.70、物理损伤召回率 0.7143，未达 80% 验收线；
- 双口径 mAP@0.5（0.82/0.90）虽达标，但评估基于失真标签，不能代表真实能力。

本次修复针对电损伤/物理损伤两类局部缺陷重新标注，并完成数据集清洗、重新
划分、增强与重训练，使模型学习局部缺陷定位模式。

## 2 修复流水线

| 步骤 | 脚本 | 作用 |
|---|---|---|
| 1 全幅框扫描 | `scripts/scan_full_boxes.py` | 批量识别全幅占位框，统计数量，生成重标清单 |
| 2 数据集清洗 | `scripts/clean_dataset.py` | md5 去重、图标签成对校验、损坏图过滤，构建扁平工作区 |
| 3 伪标注辅助 | `scripts/pseudo_refine.py` | 当前模型对重标清单推理局部框，输出 YOLO txt + LabelImg XML + 预览图 |
| 4 人工修正 | LabelImg（人工） | 在预置框基础上删错框/改类别/微调位置（154 张清单） |
| 5 XML 转 YOLO | `scripts/convert_labels.py` | 修正后的 XML 转回 YOLO txt |
| 6 重新划分 | `scripts/split_dataset.py` | 清洗后数据 8:1:1 分层划分，生成 data.yaml 与类别权重 |
| 7 数据增强 | `scripts/augment.py` | 翻转/旋转/亮度扰动/Mosaic 拼接 + 类别加权采样 |
| 8 训练 | `train.py` | 迁移学习（加权过采样、早停、余弦退火），约 4~5 小时 |
| 9 评估归档 | `eval.py` | 双口径评估（官方 + 工程），输出 mAP/召回率/PR 曲线 |

## 3 清洗前后数据集统计

### 3.1 全幅占位框扫描统计（修复前，已排除增强样本）

来源：`datasets/full_box_scan.json`（tol=0.001；augm_* 增强样本不入重标范围，
其标签将由修正后标签重新生成）

| 类别 | train | val | test | 合计 |
|---|---:|---:|---:|---:|
| 0 Clean 清洁 | 228 | 19 | 19 | 266 |
| 1 Dusty 积灰 | 222 | 19 | 19 | 260 |
| 2 Bird-drop 鸟粪 | 234 | 21 | 21 | 276 |
| 3 Electrical-damage 电损伤 | 83 | 10 | 10 | 103 |
| 4 Physical-Damage 物理损伤 | 55 | 7 | 7 | 69 |
| 5 Snow-Covered 积雪 | 188 | 12 | 12 | 212 |
| **合计** | **1010** | **88** | **88** | **1186** |

**重标范围**：电损伤/物理损伤类全幅框共 **172 个**（train 138 + val 17 + test 17），
对应 **172 张真实样本图像**（`datasets/full_box_list.txt`）。其中 val/test 共
34 张一并纳入重标（评估集标签同样失真，若不修正则评估无法反映真实能力）。

注：全局型缺陷（清洁/积灰/鸟粪/积雪）的"全幅框"语义近似正确（该类缺陷覆盖
整块面板区域），工程口径下其召回率 0.89-0.95 已达标，故本次仅重标局部型缺陷
（电损伤/物理损伤）两类。

### 3.2 清洗前后对比（clean_stats.json）

清洗动作：排除旧增强样本（augm_* 700 张，标签继承自全幅框体系）、图像内容
MD5 去重（保留优先级 test > val > train，消除跨集数据泄漏）、成对校验、损坏过滤。

| 指标 | 清洗前 | 清洗后 | 变化 |
|---|---:|---:|---:|
| 图像总数（排除旧增强后） | 885 | 794 | -91（重复） |
| 其中 train | 709 | 623 | -86 |
| 其中 val | 88 | 84 | -4 |
| 其中 test | 88 | 87 | -1 |
| 有图无标签 | 0 | 0 | 无 |
| 有标签无图（孤儿） | 0 | 0 | 无 |
| 损坏图像 | 0 | 0 | 无 |

清洗前后各类别目标框数：

| 类别 | 清洗前框数 | 清洗后框数 |
|---|---:|---:|
| Clean 清洁 | 193 | 186 |
| Dusty 积灰 | 190 | 182 |
| Bird-drop 鸟粪 | 207 | 159 |
| Electrical-damage 电损伤 | 103 | 91 |
| Physical-Damage 物理损伤 | 69 | 63 |
| Snow-Covered 积雪 | 123 | 113 |
| **合计** | **885** | **794** |

注：框数下降除去重外，还因 val/test 标签为单类全幅框、train 部分样本含多框。

### 3.3 重标注数量

| 项目 | 数量 |
|---|---:|
| 电损伤全幅框（需重标） | 103 |
| 物理损伤全幅框（需重标） | 69 |
| **重标框合计** | **172** |
| 重标图像数（清单，含 val/test 34 张） | 172 |
| 其中清洗去重后工作区实际待标注 | 154 |
| 伪标注辅助有效框数（局部框） | 0 |
| 需人工从零绘制局部框的图像数 | 154 |

**执行方案（用户最终确认：方案 A 全量重标 + 全量重训）**：清洗后工作区
`datasets_refine/` 中 154 张电/物理损伤图（train 121 + val 17 + test 16）
全部纳入人工重标（`annotate_todo.txt`），修正完成后由 `convert_labels.py`
转回 YOLO 标签，`split_dataset.py` 对全量数据（794 张）重新 8:1:1 划分，
增强后重训（约 4~5 小时）。此前"仅 50 张训练"的缩减方案（`annotate_todo_50.txt`、
`datasets_refine_50/`、`prepare_train50.py`）已归档，不再使用。

伪标注结论（2026-09-18 实测）：当前模型对电/物理损伤局部缺陷图在
conf=0.001~0.25 下均只输出近全幅框（normW/H≈1.0），无局部定位能力，
伪标注框无位置参考价值（脚本已默认过滤），154 张全部需人工依据图像
内容从零绘制局部缺陷框。伪标注的价值在于：一次性建立 LabelImg 工作区
（预置类别清单与待标注文件），并排除增强副本避免重复劳动。

## 4 数据增强配置

由 `scripts/augment.py` 离线执行（基于修正后的标签）：

| 增强算子 | 配置 |
|---|---|
| 随机翻转 | 水平 p=0.5，垂直 p=0.2 |
| 随机旋转 | ±15°，bbox 取旋转后外接框 |
| 亮度扰动 | alpha 0.8–1.2，beta ±30 |
| Mosaic 拼接 | 2×2，输出 640×640 |
| 类别加权采样 | 按目标框类别频率倒数加权，含稀有类图像优先增强 |

训练端（train.py 内置）另启用类别加权过采样（class_weights.json 频率倒数，
单图重复上限 3）与在线 HSV 扰动，缓解类别不均衡。

## 5 训练参数

| 参数 | 值 |
|---|---|
| 模型 | YOLOv8n（迁移学习，COCO 预训练） |
| 数据划分 | 8:1:1（train/val/test，分层抽样，seed=42） |
| 输入尺寸 | 640×640 |
| 批大小 | 8（CPU） |
| 优化器 | AdamW（lr0=0.001，余弦退火至 0.01×lr0） |
| 早停 | patience=30，监控验证集 fitness |
| 最大轮数 | 150 |
| 增强 | 离线增强 700 张 + 在线 HSV 扰动 |
| 预估时长 | 4~5 小时（CPU，yolov8n） |

## 6 最终评估指标（训练完成后填写）

工程口径（conf=0.25、IoU=0.5，与部署一致）：

| 指标 | 验收线 | 实测 | 结论 |
|---|---:|---:|---|
| mAP@0.5 | ≥0.75 | 待填 | — |
| 积灰召回率@0.25 | ≥0.80 | 待填 | — |
| 鸟粪召回率@0.25 | ≥0.80 | 待填 | — |
| 电损伤召回率@0.25 | ≥0.80 | 待填 | — |
| 物理损伤召回率@0.25 | ≥0.80 | 待填 | — |
| 积雪召回率@0.25 | ≥0.80 | 待填 | — |

官方口径（Ultralytics val，rect=False 方形 640×640）mAP@0.5：待填。

评估产物：`runs/eval/<时间戳>/metrics.json`、`eval_summary.md`、`pr_curve.png`。

## 7 复现命令

```bash
# 1. 全幅框扫描与重标清单
python scripts/scan_full_boxes.py

# 2. 清洗并构建扁平工作区（--dry-run 预览，--apply 执行）
python scripts/clean_dataset.py --dry-run
python scripts/clean_dataset.py --apply

# 3. 伪标注辅助（生成 YOLO 底稿 + LabelImg XML + 预览图）
python scripts/pseudo_refine.py --conf 0.25

# 3.5（可选，已归档）50 张缩减方案：python scripts/pick_50_annotate.py --seed 42
#    python scripts/prepare_50_workspace.py   —— 用户最终确认方案 A，不再使用

# 4.（人工）LabelImg 修正 datasets_refine/labels_xml 下 154 张图的预置框
#    Open Dir -> datasets_refine/images，Change Save Dir -> datasets_refine/labels_xml

# 5. XML 转回 YOLO（154 张修正后）
python scripts/convert_labels.py --xml-dir datasets_refine/labels_xml \
    --img-dir datasets_refine/images --out-dir datasets_refine/labels

# 6. 重新划分 8:1:1（全量 794 张，含 154 张修正标签）
python scripts/split_dataset.py --img-dir datasets_refine/images \
    --label-dir datasets_refine/labels --out datasets --seed 42

# 7. 增强（生成约700张增强样本，--clean 清除旧增强）
python scripts/augment.py --count 700 --clean

# 8. 训练（约4-5小时）
python train.py --weights yolov8n.pt --batch 8 --workers 0 --epochs 150 \
    --patience 30 --name train_r2

# 9. 评估归档
python eval.py --weights runs/detect/train_r2/weights/best.pt
```
