"""历史记录模块请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecordListItem(BaseModel):
    record_id: int
    image_name: str = Field(description="原始文件名")
    defect_summary: dict[str, int] = Field(description="缺陷汇总{中文类名: 数量}")
    inference_time_ms: float | None
    model_version: str
    result_image_url: str | None = Field(description="标注图访问地址")
    created_at: str = Field(description="检测时间（东八区）")


class RecordListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RecordListItem]


class RecordDetailResponse(RecordListItem):
    image_url: str | None = Field(description="原图访问地址")
    targets: list[dict] = Field(description="完整检测目标列表（detect_result解析）")
    image_size: dict = Field(description="原图尺寸")
