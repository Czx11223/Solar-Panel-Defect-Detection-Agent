/** 检测模块类型（对齐 docs/api_doc.md 4.6 与 5.1/5.2） */

export interface TargetItem {
  class_id: number
  class_name: string
  confidence: number
  bbox: [number, number, number, number]
}

export type AdviceLevel = 'high' | 'mid' | 'low'

export interface AdviceItem {
  level: AdviceLevel
  level_name: string
  class_name: string
  count: number
  max_confidence: number
  text: string
}

export interface ImageSize {
  width: number
  height: number
}

export interface DetectResponse {
  record_id: number
  model_version: string
  inference_time_ms: number | null
  image_size: ImageSize
  targets: TargetItem[]
  defect_summary: Record<string, number>
  advice: AdviceItem[]
  rendered_image_base64: string
  result_image_url: string
}
