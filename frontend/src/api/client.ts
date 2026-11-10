/** axios 实例与统一拦截（frontend_web_spec.md 5.1）：
 *  - 请求拦截：注入 Authorization: Bearer <token>（云端 access token 或应用 JWT）
 *  - 响应拦截：解包 {code, message, data}，code!==0 抛 ApiError；
 *    40101 时先用云端会话续期并重试一次，仍失败才清登录态跳登录页
 *  - blob 请求（CSV导出/鉴权图片）不参与解包
 */

import { message } from 'antd'
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

import { exchangeAppToken, issueTicket } from '../cloud/auth'
import { cloud } from '../cloud/client'
import type { ApiEnvelope } from '../types/common'
import { clearAuth, getTicket, getToken } from '../utils/storage'

/** 业务错误：携带后端错误码，供页面按 code 分支提示 */
export class ApiError extends Error {
  readonly code: number

  constructor(code: number, messageText: string) {
    super(messageText)
    this.name = 'ApiError'
    this.code = code
  }
}

export const BASE_URL: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 60_000,
})

/** 除标准 Authorization 外，再送两个自有凭据：
 *  - X-PV-Token：身份令牌（应用 JWT 或云端 access token）。发布平台的网关会用平台
 *    凭据覆盖 Authorization，自定义头不参与网关的凭据处理；
 *  - X-PV-Ticket：云端签发的短期身份票据，后端据此确认云端身份（无需反向自省）。
 *  令牌与票据只放请求头，不放进 URL。 */
export function attachToken(config: InternalAxiosRequestConfig, token: string): void {
  config.headers.Authorization = `Bearer ${token}`
  config.headers['X-PV-Token'] = token
  const ticket = getTicket()
  if (ticket) config.headers['X-PV-Ticket'] = ticket
}

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    attachToken(config, token)
  }
  return config
})

const CODE_UNAUTH = 40101

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

function handleSessionExpired(reason?: string): void {
  clearAuth()
  // 优先展示服务端给出的具体原因（"登录态已失效" / "认证配置错误" / "认证暂不可用"），
  // 便于定位是令牌过期还是部署配置问题。
  message.warning(reason || '登录已过期，请重新登录')
  if (window.location.hash !== '#/login') {
    window.location.hash = '#/login'
  }
}

/** 401 恢复：先尝试用云端会话换一张新票据并兑换应用 JWT（登录态仍有效时透明续期），
 *  成功则原请求重放；仍失败才按登录过期处理。
 *  业务请求使用应用 JWT（24h），不再依赖 15 分钟票据，避免切模块被踢。 */
async function renewSession(): Promise<string | null> {
  try {
    const { data, error } = await cloud.auth.getSession()
    if (error || !data) return null
    const cloudToken = await cloud.auth.getAccessToken()
    if (!cloudToken) {
      const refreshed = await cloud.auth.refreshSession()
      if (refreshed.error) return null
    }
    // 重新签发票据 → 兑换应用 JWT
    await issueTicket()
    return await exchangeAppToken()
  } catch {
    return null
  }
}

function isEnvelope(payload: unknown): payload is ApiEnvelope<unknown> {
  return typeof payload === 'object' && payload !== null && 'code' in payload
}

/** 401 恢复：续期后重放原请求；失败则按登录过期处理。 */
async function recoverAndRetry(
  config: RetriableConfig, fallbackMessage: string,
): Promise<unknown> {
  const token = await renewSession()
  if (token) {
    config._retried = true
    attachToken(config, token)
    return http.request(config)
  }
  handleSessionExpired(fallbackMessage)
  throw new ApiError(CODE_UNAUTH, fallbackMessage)
}

http.interceptors.response.use(
  (response) => {
    // blob 响应（responseType 由请求方指定）不参与统一解包
    if (response.config.responseType === 'blob') {
      return response
    }
    const envelope = response.data as ApiEnvelope<unknown>
    if (envelope.code !== 0) {
      const cfg = response.config as RetriableConfig
      if (envelope.code === CODE_UNAUTH && !cfg._retried) {
        return recoverAndRetry(cfg, envelope.message) as never
      }
      if (envelope.code === CODE_UNAUTH) handleSessionExpired(envelope.message)
      return Promise.reject(new ApiError(envelope.code, envelope.message))
    }
    return response
  },
  (error: AxiosError) => {
    // 网络层失败（无响应/超时/连接拒绝）
    if (error.response) {
      const payload = error.response.data
      if (isEnvelope(payload)) {
        const cfg = error.config as RetriableConfig | undefined
        if (payload.code === CODE_UNAUTH && cfg && !cfg._retried) {
          return recoverAndRetry(cfg, payload.message) as never
        }
        if (payload.code === CODE_UNAUTH) handleSessionExpired(payload.message)
        return Promise.reject(new ApiError(payload.code, payload.message))
      }
    }
    return Promise.reject(new ApiError(-1, '网络连接失败，请检查后端服务'))
  },
)

async function unwrap<T>(request: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const res = await request
  return res.data.data
}

export function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  return unwrap(http.get<ApiEnvelope<T>>(url, { params }))
}

export function post<T>(url: string, body?: unknown): Promise<T> {
  return unwrap(http.post<ApiEnvelope<T>>(url, body))
}

export function postForm<T>(url: string, formData: FormData): Promise<T> {
  return unwrap(http.post<ApiEnvelope<T>>(url, formData))
}

export function del<T>(url: string): Promise<T> {
  return unwrap(http.delete<ApiEnvelope<T>>(url))
}

export async function getBlob(url: string): Promise<Blob> {
  // 后端返回的资源 URL 恒为 /api/... 相对路径。统一剥离 /api 前缀后交给 axios 的
  // baseURL 拼接；无论 VITE_API_BASE 是 '/api' 还是完整域名（https://host/api），
  // 都不会拼出 /api/api/...，也不会把请求发到错误的源。
  let clean = url
  if (url.startsWith('/api/')) {
    clean = url.slice('/api'.length)
  } else if (BASE_URL.startsWith('http') && url.startsWith(`${BASE_URL}/`)) {
    clean = url.slice(BASE_URL.length)
  }
  const res = await http.get<Blob>(clean, { responseType: 'blob' })
  return res.data
}
