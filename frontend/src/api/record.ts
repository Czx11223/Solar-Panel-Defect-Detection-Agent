/** 历史记录接口（docs/api_doc.md 4.7–4.11）：
 * 导出与图像访问均需鉴权头，统一用 blob 获取（<img>/window.open 无法携带Header）
 */

import { get, getBlob } from './client'

import type { RecordDetailResponse, RecordListParams, RecordListResponse } from '../types/record'

export function fetchRecords(params: RecordListParams): Promise<RecordListResponse> {
  return get<RecordListResponse>('/record/list', { ...params })
}

export function fetchRecordDetail(recordId: number): Promise<RecordDetailResponse> {
  return get<RecordDetailResponse>(`/record/${recordId}`)
}

/** 鉴权资源（原图/标注图）blob 获取，url 为后端相对路径（如 /api/files/results/x.jpg） */
export function fetchFileBlob(url: string): Promise<Blob> {
  return getBlob(url)
}

export function exportRecords(start?: string, end?: string): Promise<Blob> {
  const search = new URLSearchParams()
  if (start) search.set('start', start)
  if (end) search.set('end', end)
  const query = search.toString()
  return getBlob(`/record/export${query ? `?${query}` : ''}`)
}
