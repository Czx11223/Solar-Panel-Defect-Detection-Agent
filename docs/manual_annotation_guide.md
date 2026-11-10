# 人工标注操作指南（电损伤 / 物理损伤）

## 1. 打开 LabelImg

在 PowerShell 中运行（二选一）：

```powershell
# 方式A：直接打开图像目录（推荐）
python -m labelImg "D:\peixunwenjian\2026.9.14-9.28\algorithm\datasets_refine\annotate_manual\Electrical-damage" "D:\peixunwenjian\2026.9.14-9.28\algorithm\datasets_refine\annotate_manual\predefined_classes.txt"

# 标完一类再开另一类
python -m labelImg "D:\peixunwenjian\2026.9.14-9.28\algorithm\datasets_refine\annotate_manual\Physical-Damage" "D:\peixunwenjian\2026.9.14-9.28\algorithm\datasets_refine\annotate_manual\predefined_classes.txt"
```

打开后点击 **PascalVOC**（左上角格式切换，确认是 PascalVOC 不是 YOLO）。

## 2. 标注规则

### 类别名（从右侧框下拉选择，勿手打）
| 类别 | 下拉框值 |
|---|---|
| 电损伤 | `Electrical-damage` |
| 物理损伤 | `Physical-Damage` |

### 电损伤（Electrical-damage）长什么样
- **热斑/烧灼点**：白色或灰白色核心 + 褐色/棕色热扩散晕圈
- 常见位置：两片电池之间的汇流条/焊带连接处，或电池片表面
- 框选范围：**框住白芯 + 棕色晕圈的整体**，紧贴缺陷边缘，不要框整块面板

### 物理损伤（Physical-Damage）长什么样
- **裂纹**：细长的线状裂缝，深色或亮色线条
- **碎裂/缺角**：电池片边缘破碎、缺角、掉块
- 框选范围：**紧贴裂纹/破损本体**，能窄就窄

### 通用规则
1. 一张图有多个缺陷 → 画多个框，每个框选一个缺陷
2. 框必须包含完整的缺陷区域，允许少量边距（2-5 像素），但**禁止框住大块正常区域**
3. 若某张图实在找不到任何缺陷（画不出框），**跳过该图**，在标注完成后告知我文件名，我会将其排除出数据集
4. 每张图标注完成后点 **Save**（Ctrl+S），LabelImg 自动在图像同目录生成同名 `.xml`

## 3. 标注完成后的处理

全部标注完成后告诉我，我会自动：
1. 把 XML 转成 YOLO 格式标签并替换 `datasets_fixed` 中的对应标签
2. 排除无标注图与未被标注的训练图（约 29 张）
3. 重建数据集并重新训练模型

## 4. 工作量
共 **107 张**：电损伤 55 张 + 物理损伤 52 张。每张约 1 分钟，预计 1.5-2 小时。
