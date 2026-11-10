"""运维建议匹配：按缺陷类别输出维护建议，置信度三档分级（D28）。

- 每类缺陷维护静态建议模板（advice_texts），检测后按类别聚合数量与最高置信度；
- 置信度分级：≥0.75高（立即处理）、0.5–0.75中（近期安排）、<0.5低（持续观察）；
- 清洁类输出"无需维护"提示；未检出任何缺陷时同样返回清洁提示；
- 输出按风险从高到低排序。
"""

from __future__ import annotations

# 类别ID → 建议文本（1积灰/2鸟粪/3电损伤/4物理损伤/5积雪）
ADVICE_TEXTS = {
    1: "面板表面存在积灰，建议安排清洗（高压水枪或清洁机器人），积灰会降低发电效率。",
    2: "检测到鸟粪附着，建议及时清除，并评估防鸟措施（驱鸟器/防鸟刺）。",
    3: "检测到疑似电损伤（热斑/电弧痕迹），建议停机检修并由专业人员排查电路，防范火灾风险。",
    4: "检测到物理损伤（裂纹/破碎），建议评估组件结构安全，必要时更换组件。",
    5: "检测到积雪覆盖，建议关注组件承重与发电效率，条件允许时及时除雪。",
}

CLEAN_TEXT = "面板状态正常，无需维护；请按巡检周期持续监测。"

# 置信度分档阈值与处置语义（有序，从高到低）
LEVEL_RULES = [
    (0.75, "high", "高", "立即处理"),
    (0.50, "mid", "中", "近期安排"),
    (0.00, "low", "低", "持续观察"),
]
_LEVEL_ORDER = {"high": 3, "mid": 2, "low": 1}


def _level_of(conf: float) -> tuple[str, str, str]:
    for threshold, key, name, action in LEVEL_RULES:
        if conf >= threshold:
            return key, name, action
    return LEVEL_RULES[-1][1], LEVEL_RULES[-1][2], LEVEL_RULES[-1][3]


def build_advice(targets: list[dict]) -> list[dict]:
    """按检测目标生成运维建议列表（风险从高到低）。"""
    # 按类别聚合：数量与最高置信度
    agg: dict[int, dict] = {}
    for t in targets:
        cid = t["class_id"]
        if cid == 0:  # 清洁类不计入缺陷建议
            continue
        item = agg.setdefault(cid, {"count": 0, "max_conf": 0.0})
        item["count"] += 1
        item["max_conf"] = max(item["max_conf"], t["confidence"])

    advice: list[dict] = []
    for cid, item in agg.items():
        key, name, action = _level_of(item["max_conf"])
        advice.append({
            "level": key,
            "level_name": name,
            "class_name": _zh_name(cid),
            "count": item["count"],
            "max_confidence": round(item["max_conf"], 4),
            "text": f"{ADVICE_TEXTS.get(cid, '')} 处置优先级：{action}。",
        })

    advice.sort(key=lambda a: (_LEVEL_ORDER[a["level"]], a["count"]), reverse=True)

    # 无缺陷（含清洁类检出）时给出常规巡检提示
    if not advice:
        advice.append({
            "level": "low", "level_name": "低", "class_name": "清洁",
            "count": 0, "max_confidence": 0.0, "text": CLEAN_TEXT,
        })
    return advice


def _zh_name(class_id: int) -> str:
    from ..core.pv_classes import ID_TO_ZH
    return ID_TO_ZH.get(class_id, str(class_id))
