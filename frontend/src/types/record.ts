/** 历史记录模块类型（对齐 docs/api_doc.md 4.7–4.9） */

import type { ImageSize, TargetItem } from './detect'

export interface RecordListItem {
  record_id: number
  image_name: string
  defect_summary: Record<string, number>
  inference_time_ms: number | null
  model_version: string
  result_image_url: string | null
  created_at: string
}

export interface RecordListResponse {
  total: number
  page: number
  page_size: number
  items: RecordListItem[]
}

export interface RecordDetailResponse extends RecordListItem {
  image_url: string | null
  targets: TargetItem[]
  image_size: ImageSize
}

export interface RecordListParams {
  page: number
  page_size: number
}
