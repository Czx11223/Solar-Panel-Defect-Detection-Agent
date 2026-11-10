"""六类状态共享类别映射（后端侧）。

与 algorithm/scripts/pv_classes.py 保持一致：类别ID、英文标识、中文名、
渲染用BGR颜色。后端推理结果与数据集/训练侧通过class_id衔接，
中文名用于接口响应与运维建议。
"""

CLASSES = [
    # (英文标识, 中文名)
    ("Clean", "清洁"),
    ("Dusty", "积灰"),
    ("Bird-drop", "鸟粪"),
    ("Electrical-damage", "电损伤"),
    ("Physical-Damage", "物理损伤"),
    ("Snow-Covered", "积雪"),
]

ID_TO_EN = {i: en for i, (en, _zh) in enumerate(CLASSES)}
ID_TO_ZH = {i: zh for i, (_en, zh) in enumerate(CLASSES)}

# BGR颜色，供结果渲染绘制检测框
BOX_COLORS_BGR = [
    (80, 200, 80),    # 0 Clean 清洁 绿
    (0, 200, 255),    # 1 Dusty 积灰 黄
    (0, 120, 255),    # 2 Bird-drop 鸟粪 橙
    (0, 0, 255),      # 3 Electrical-damage 电损伤 红
    (255, 0, 200),    # 4 Physical-Damage 物理损伤 紫
    (255, 255, 255),  # 5 Snow-Covered 积雪 白
]
