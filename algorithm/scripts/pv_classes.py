"""光伏面板缺陷检测系统 · 六类状态共享类别映射。

定义全部数据集脚本共用的类别ID、英文标识（Kaggle文件夹名）、中文名映射，
并提供名称容错解析（忽略大小写与连字符/下划线差异）。

数据集下载地址（注册后免费下载）：
    https://www.kaggle.com/datasets/pythonafroz/solar-panel-images

运行环境：Python 3.12+（本模块为纯常量定义，无第三方依赖）

使用方式：作为模块导入
    from pv_classes import CLASSES, class_id_from_name, ID_TO_EN
"""

CLASSES = [
    # (英文标识/Kaggle文件夹名, 中文名)
    ("Clean", "清洁"),
    ("Dusty", "积灰"),
    ("Bird-drop", "鸟粪"),
    ("Electrical-damage", "电损伤"),
    ("Physical-Damage", "物理损伤"),
    ("Snow-Covered", "积雪"),
]

ID_TO_EN = {i: en for i, (en, _zh) in enumerate(CLASSES)}
ID_TO_ZH = {i: zh for i, (_en, zh) in enumerate(CLASSES)}

# BGR颜色，供可视化预览与结果渲染使用
BOX_COLORS_BGR = [
    (80, 200, 80),    # 0 Clean 清洁 绿
    (0, 200, 255),    # 1 Dusty 积灰 黄
    (0, 120, 255),    # 2 Bird-drop 鸟粪 橙
    (0, 0, 255),      # 3 Electrical-damage 电损伤 红
    (255, 0, 200),    # 4 Physical-Damage 物理损伤 紫
    (255, 255, 255),  # 5 Snow-Covered 积雪 白
]


def normalize_key(name: str) -> str:
    """名称容错归一：去空白、转小写、连字符/空格统一为下划线。"""
    return name.strip().lower().replace("-", "_").replace(" ", "_")


# 容错映射表：英文标识与中文名均可解析到类别ID
NAME_TO_ID = {}
for _i, (_en, _zh) in enumerate(CLASSES):
    NAME_TO_ID[normalize_key(_en)] = _i
    NAME_TO_ID[normalize_key(_zh)] = _i


def class_id_from_name(name: str) -> int:
    """把类别名（英文/中文，任意大小写与连字符风格）解析为类别ID。

    无法识别时抛出 ValueError，由调用方决定进入错误清单。
    """
    key = normalize_key(name)
    if key not in NAME_TO_ID:
        raise ValueError(f"未知类别名: {name!r}（可用: {[en for en, _ in CLASSES]}）")
    return NAME_TO_ID[key]
