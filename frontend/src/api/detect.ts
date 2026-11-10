/** 检测接口（docs/api_doc.md 4.6） */

import { postForm } from './client'

import type { DetectResponse } from '../types/detect'

export function detectImage(file: File): Promise<DetectResponse> {
  const form = new FormData()
  form.append('file', file)
  return postForm<DetectResponse>('/detect/image', form)
}
