/**
 * 云服务客户端：全局单例。
 *
 * Auth / Database / Storage / LLM 四个模块共用同一个实例——登录后共享请求层
 * 会自动给数据库、存储请求带上会话，不需要在每个调用点重复注入身份。
 */

import { createWorkBuddyCloud } from '@tencent-ai/workbuddy-cloud-sdk'

import type { Database } from './database.types'
import { PUBLIC_CONFIG } from './publicConfig'

export const cloud = createWorkBuddyCloud<Database>({
  endpoint: PUBLIC_CONFIG.endpoint,
  oauthRelayBaseUrl: PUBLIC_CONFIG.oauthRelayBaseUrl,
  publishableKey: PUBLIC_CONFIG.publishableKey,
})

/** 统一的取数助手：把 { data, error } 信封转成 throw。 */
export function unwrap<T>(result: { data: T | null; error: unknown }): T {
  if (result.error) {
    const err = result.error as { message?: string; kind?: string }
    throw new Error(err?.message || '云服务调用失败')
  }
  return result.data as T
}
