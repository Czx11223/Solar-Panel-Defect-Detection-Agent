"""检测模块响应模型。

targets/advice/defect_summary的生成逻辑在services层；
本文件定义对外契约（含每个字段的中文说明），响应统一由路由层组装。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TargetItem(BaseModel):
    class_id: int = Field(description="类别ID（0清洁/1积灰/2鸟粪/3电损伤/4物理损伤/5积雪）")
    class_name: str = Field(description="类别中文名")
    confidence: float = Field(description="置信度（0–1），低于0.25的目标不输出")
    bbox: list[float] = Field(description="原图像素坐标系[x1,y1,x2,y2]")


class AdviceItem(BaseModel):
    level: str = Field(description="处置级别：high/mid/low")
    level_name: str = Field(description="级别中文名：高/中/低")
    class_name: str = Field(description="缺陷类别中文名")
    count: int = Field(description="该类别检出数量")
    max_confidence: float = Field(description="该类别最高置信度")
    text: str = Field(description="运维建议文本")


class DetectResponse(BaseModel):
    record_id: int = Field(description="检测记录ID（已入库）")
    model_version: str = Field(description="模型版本标识")
    inference_time_ms: float | None = Field(description="单图推理耗时（不含传输与渲染）")
    image_size: dict = Field(description="原图尺寸{width, height}")
    targets: list[TargetItem] = Field(description="检测目标列表，未检出为空数组")
    defect_summary: dict[str, int] = Field(description="缺陷类别汇总{中文类名: 数量}")
    advice: list[AdviceItem] = Field(description="运维建议列表，按风险从高到低")
    rendered_image_base64: str = Field(description="标注结果图base64（data:image/jpeg;base64,...）")
    result_image_url: str = Field(description="标注结果图访问地址（属主校验）")
