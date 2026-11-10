/**
 * 云认证：邮箱验证码登录/注册（OTP 一条链路同时覆盖新老用户）。
 *
 * 登录成功后做两件事：
 * 1. 把云端 access token 写入本地（key pv_token），供应用接口与云端数据面使用；
 * 2. 向云端申请一张短期票据（issue_ticket），写入 pv_ticket。
 *
 * 票据由云端数据库的 `auth.uid()` 生成并签名，后端凭它确认"这个人确实是当前云端用户"，
 * 因此后端不需要拿用户令牌去反向自省，也不需要持有任何云端密钥。
 */

import type { TicketPayload } from './database.types'
import { clearAuth, getTicket, getToken, setTicket, setToken } from '../utils/storage'

import { cloud } from './client'

/** 后端接口基址：与 api/client.ts 保持同一口径（此处内联，避免与其形成循环依赖）。 */
const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

export interface CloudIdentity {
  id: string
  name: string | null
  email: string | null
}

/** 待验证的验证码挑战：发码后保存，提交时必须回传同一份。 */
export interface PendingOtp {
  email: string
  verificationId: string
  isExistingUser: boolean
}

function toIdentity(user: unknown): CloudIdentity | null {
  if (!user || typeof user !== 'object') return null
  const u = user as Record<string, unknown>
  const id = u.id ?? u.uid ?? u.user_id
  if (id === undefined || id === null || id === '') return null
  const pick = (key: string): string | null => {
    const v = u[key]
    return typeof v === 'string' && v ? v : null
  }
  return { id: String(id), name: pick('name') ?? pick('nickname'), email: pick('email') }
}

/** 把票据编码成可放进请求头的 ASCII 串（base64url，无填充）。 */
export function encodeTicket(ticket: TicketPayload): string {
  const json = JSON.stringify({
    uid: ticket.uid,
    exp: ticket.exp,
    sig: ticket.sig,
    email: ticket.email ?? '',
    name: ticket.name ?? '',
  })
  const bytes = new TextEncoder().encode(json)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** 向云端申请短期票据：uid 与签名都由云端数据库生成，前端无法伪造。
 *  返回 null 表示当前没有可用的云端会话（或数据面不可达）。 */
export async function issueTicket(): Promise<TicketPayload | null> {
  try {
    const { data, error } = await cloud.database.rpc('issue_ticket')
    if (error || !data) return null
    const raw = (Array.isArray(data) ? data[0] : data) as TicketPayload
    if (!raw?.uid || !raw?.sig || !raw?.exp) return null
    setTicket(encodeTicket(raw))
    return raw
  } catch {
    return null
  }
}

/** 用票据向后端换取应用 JWT 并落盘。
 *
 *  业务请求此后只带应用 JWT（后端本地验签，24 小时），不再依赖 15 分钟票据：
 *  票据过期、云端数据面抖动都不会再导致"切换模块被踢回登录页"。
 *  返回 null 表示兑换失败（票据缺失/过期或后端不可达）。
 */
export async function exchangeAppToken(): Promise<string | null> {
  try {
    const ticket = getTicket()
    if (!ticket) return null
    const res = await fetch(`${API_BASE}/auth/cloud-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-PV-Ticket': ticket },
      body: JSON.stringify({ ticket }),
    })
    const payload = (await res.json().catch(() => null)) as
      | { code?: number; data?: { access_token?: string } }
      | null
    const token = payload?.data?.access_token
    if (!res.ok || !token) return null
    setToken(token)
    return token
  } catch {
    return null
  }
}

/** 读取当前云端会话里的用户身份（不发请求）。 */
export async function getIdentity(): Promise<CloudIdentity | null> {
  try {
    const { data, error } = await cloud.auth.getSession()
    if (error || !data) return null
    return toIdentity((data as { user?: unknown }).user)
  } catch {
    return null
  }
}

/** 把云端会话的 access token 同步到本地，供后端接口鉴权使用。
 *
 *  注意：自 2026-11 起业务请求使用**应用 JWT**（登录时由票据兑换），云端会话
 *  只用于云数据库/存储/模型。因此云会话查不到时**不能**清掉本地登录态——
 *  那会把还能正常访问应用的用户强行踢回登录页。仅在需要重新兑换时返回 null。
 */
export async function syncToken(): Promise<string | null> {
  try {
    const { data, error } = await cloud.auth.getSession()
    if (error || !data) return getToken()
    let token = await cloud.auth.getAccessToken()
    if (!token) {
      // 会话被判为过期时再强刷一次，避免把不可用的旧令牌留给后端
      const refreshed = await cloud.auth.refreshSession()
      if (!refreshed.error && refreshed.data) token = await cloud.auth.getAccessToken()
    }
    if (!token) return getToken()  // 保留现有应用 JWT，不清登录态
    setToken(token)
    // 令牌可能续期过，票据也一并换新，并兑换成应用 JWT
    await issueTicket()
    const appToken = await exchangeAppToken()
    return appToken ?? token
  } catch {
    return getToken()
  }
}

/** 发送邮箱验证码。返回挑战信息，提交验证码时必须原样使用。 */
export async function sendEmailCode(email: string): Promise<PendingOtp> {
  const sent = await cloud.auth.sendOtp({ email })
  if (sent.error || !sent.data) {
    throw new Error(sent.error?.message || '验证码发送失败，请稍后重试')
  }
  const data = sent.data as { verificationId: string; isExistingUser: boolean }
  return { email, verificationId: data.verificationId, isExistingUser: data.isExistingUser }
}

/** 校验验证码并建立会话（新用户自动注册）。 */
export async function verifyEmailCode(pending: PendingOtp, code: string): Promise<CloudIdentity> {
  const done = await cloud.auth.verifyOtp({
    email: pending.email,
    verificationId: pending.verificationId,
    isExistingUser: pending.isExistingUser,
    token: code.trim(),
  })
  if (done.error || !done.data) {
    throw new Error(done.error?.message || '验证码校验失败')
  }

  // 取可用令牌：先直接取；取不到说明会话被判过期，强刷一次再取。
  // 不能带着登录前的残留值继续，否则后端拿到的是过期令牌，表现为“登录后被踢”。
  let token = await cloud.auth.getAccessToken()
  if (!token) {
    const refreshed = await cloud.auth.refreshSession()
    if (!refreshed.error && refreshed.data) token = await cloud.auth.getAccessToken()
  }
  if (!token) {
    // 区分“会话没建立”和“会话在但令牌为空”，便于定位是验证码环节还是续期环节
    const session = await cloud.auth.getSession()
    const hasSession = !session.error && Boolean(session.data)
    clearAuth()
    throw new Error(hasSession
      ? '云端会话已建立但令牌不可用，请重新获取验证码再试'
      : '云端会话未建立（未取到 access token），请重新获取验证码再试')
  }
  setToken(token)

  // 用云端票据兑换一次应用 JWT：之后所有业务请求都用它（后端本地验签，24h），
  // 不再每次携带 15 分钟票据，也不会因为云端查询抖动被踢回登录页。
  const ticket = await issueTicket()
  if (!ticket) {
    clearAuth()
    throw new Error('云端票据签发失败，请重新登录')
  }
  const appToken = await exchangeAppToken()
  if (!appToken) {
    clearAuth()
    throw new Error('应用会话建立失败（票据兑换未通过），请重试')
  }

  // 自检：确认云端确实认可这个令牌。失败就直接在登录页报原因，
  // 不让用户先进应用再被 401 踢回登录页。
  const me = await cloud.auth.getUser()
  if (me.error) {
    clearAuth()
    throw new Error(`云端会话校验失败：${me.error.message || '未知原因'}`)
  }

  const identity = toIdentity(me.data) ?? toIdentity((done.data as { user?: unknown }).user)
  if (!identity) throw new Error('登录成功但未取到用户身份，请重试')
  return identity
}

/** 退出云端登录（同时清本地令牌）。 */
export async function signOutCloud(): Promise<void> {
  try {
    await cloud.auth.signOut()
  } finally {
    clearAuth()
  }
}
