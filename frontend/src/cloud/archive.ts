/**
 * 检测结果云端归档：把原图与标注结果图写入云对象存储，并在云数据库登记资产索引。
 *
 * 为什么前端归档而不是后端：存储是"已登录用户"的资源，只有前端持有云端会话；
 * 服务端不代理云端存储请求（也没有长期凭据）。索引表 detect_asset 记录
 * record_id → 对象路径，用于历史页跨设备回看同一张图。
 */

import { cloud } from './client'
import { getIdentity } from './auth'
import { uploadUserFile } from './chat'

import type { DetectResponse } from '../types/detect'

export interface ArchiveResult {
  originalPath: string | null
  annotatedPath: string | null
  failed: boolean
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [meta, b64] = dataUrl.split(',')
  const mime = /data:([^;]+)/.exec(meta)?.[1] ?? 'image/jpeg'
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}

async function recordAsset(
  recordId: number, kind: 'original' | 'annotated', path: string,
  contentType: string, size: number,
): Promise<void> {
  const identity = await getIdentity()
  const { error } = await cloud.database.from('detect_asset').insert({
    record_id: recordId,
    kind,
    storage_path: path,
    content_type: contentType,
    size_bytes: size,
    owner_name: identity?.name ?? null,
  })
  if (error) throw new Error(error.message)
}

/** 归档一次检测：失败不抛出（检测本身已成功），由调用方提示"仅本地留存"。 */
export async function archiveDetection(
  recordId: number, original: File, result: DetectResponse,
): Promise<ArchiveResult> {
  const outcome: ArchiveResult = { originalPath: null, annotatedPath: null, failed: false }
  try {
    const identity = await getIdentity()
    if (!identity) return { ...outcome, failed: true }

    const ext = (original.name.split('.').pop() || 'jpg').toLowerCase()
    const originalPath = await uploadUserFile(
      `records/${recordId}/original.${ext}`, original, original.type || 'image/jpeg',
    )
    outcome.originalPath = originalPath
    await recordAsset(recordId, 'original', originalPath,
      original.type || 'image/jpeg', original.size)

    if (result.rendered_image_base64) {
      const blob = dataUrlToBlob(result.rendered_image_base64)
      const annotatedPath = await uploadUserFile(
        `records/${recordId}/annotated.jpg`, blob, 'image/jpeg',
      )
      outcome.annotatedPath = annotatedPath
      await recordAsset(recordId, 'annotated', annotatedPath, 'image/jpeg', blob.size)
    }
    return outcome
  } catch {
    return { ...outcome, failed: true }
  }
}
