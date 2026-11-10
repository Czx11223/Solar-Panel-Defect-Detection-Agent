/**
 * 云端会话与消息存储（Cloud Database）+ 图像对象存储（Cloud Storage）。
 *
 * 数据归属由数据库保证：owner_id 默认取 auth.uid()，RLS 只允许本人读写，
 * 前端绝不发送 owner_id，也不在前端做"是不是我的"判断。
 */

import { getIdentity } from './auth'
import { cloud } from './client'

import type { AgentSession } from '../api/agent'

export interface CloudMessage {
  id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  reasoning: string | null
  tool_calls: { id: string; type?: string; function: { name: string; arguments: string } }[] | null
  tool_call_id: string | null
  tool_name: string | null
  created_at: string
}

export interface AppendAssistant {
  content: string
  reasoning?: string | null
  toolCalls?: unknown[] | null
  tokensIn?: number
  tokensOut?: number
}

async function ownerName(): Promise<string | null> {
  const id = await getIdentity()
  return id?.name ?? null
}

/** 会话列表（按最近更新倒序），消息条数按会话聚合。 */
export async function listSessions(): Promise<AgentSession[]> {
  const { data, error } = await cloud.database
    .from('agent_session')
    .select('id, title, created_at, updated_at')
    .order('updated_at', { ascending: false })
    .limit(100)
  if (error) throw new Error(error.message)

  const sessions = (data ?? []) as AgentSession[]
  if (sessions.length === 0) return []

  const { data: msgRows, error: msgErr } = await cloud.database
    .from('agent_message')
    .select('session_id')
    .in('session_id', sessions.map((s) => s.id))
  if (msgErr) throw new Error(msgErr.message)

  const counts = new Map<number, number>()
  for (const row of (msgRows ?? []) as { session_id: number }[]) {
    counts.set(row.session_id, (counts.get(row.session_id) ?? 0) + 1)
  }
  return sessions.map((s) => ({ ...s, message_count: counts.get(s.id) ?? 0 }))
}

/** 新建会话，返回会话 ID。 */
export async function createSession(title: string): Promise<number> {
  const { data, error } = await cloud.database
    .from('agent_session')
    .insert({ title: title.slice(0, 60) || '新会话', owner_name: await ownerName() })
    .select('id')
    .single()
  if (error) throw new Error(error.message)
  return Number((data as { id: number }).id)
}

export async function deleteSession(sessionId: number): Promise<void> {
  const delMsgs = await cloud.database
    .from('agent_message').delete().eq('session_id', sessionId)
  if (delMsgs.error) throw new Error(delMsgs.error.message)
  const delSession = await cloud.database
    .from('agent_session').delete().eq('id', sessionId)
  if (delSession.error) throw new Error(delSession.error.message)
}

/** 会话历史（正序）。 */
export async function listMessages(sessionId: number): Promise<CloudMessage[]> {
  const { data, error } = await cloud.database
    .from('agent_message')
    .select('id, role, content, reasoning, tool_calls, tool_call_id, tool_name, created_at')
    .eq('session_id', sessionId)
    .order('id', { ascending: true })
    .limit(500)
  if (error) throw new Error(error.message)
  return (data ?? []) as CloudMessage[]
}

async function touchSession(sessionId: number): Promise<void> {
  await cloud.database
    .from('agent_session')
    .update({ updated_at: new Date().toISOString() })
    .eq('id', sessionId)
}

export async function appendUserMessage(sessionId: number, content: string): Promise<void> {
  const { error } = await cloud.database
    .from('agent_message')
    .insert({ session_id: sessionId, role: 'user', content })
  if (error) throw new Error(error.message)
  await touchSession(sessionId)
}

export async function appendAssistantMessage(
  sessionId: number, msg: AppendAssistant,
): Promise<void> {
  const { error } = await cloud.database.from('agent_message').insert({
    session_id: sessionId,
    role: 'assistant',
    content: msg.content ?? '',
    reasoning: msg.reasoning ?? null,
    tool_calls: msg.toolCalls && msg.toolCalls.length ? msg.toolCalls : null,
    tokens_in: msg.tokensIn ?? 0,
    tokens_out: msg.tokensOut ?? 0,
  })
  if (error) throw new Error(error.message)
  await touchSession(sessionId)
}

export async function appendToolMessage(
  sessionId: number, msg: { content: string; toolCallId: string; toolName: string },
): Promise<void> {
  const { error } = await cloud.database.from('agent_message').insert({
    session_id: sessionId,
    role: 'tool',
    content: msg.content,
    tool_call_id: msg.toolCallId,
    tool_name: msg.toolName,
  })
  if (error) throw new Error(error.message)
}

// ---------------- 对象存储 ----------------

/** 上传到 users/<uid>/... 私有目录，返回对象路径。 */
export async function uploadUserFile(
  relativePath: string, body: Blob, contentType?: string,
): Promise<string> {
  const identity = await getIdentity()
  if (!identity) throw new Error('登录状态已失效，请重新登录')
  const path = cloud.storage.userPath(identity.id, relativePath)
  const res = await cloud.storage.upload(path, body, { contentType })
  if (res.error) throw new Error(res.error.message)
  return path
}

/** 生成签名下载地址（默认 10 分钟有效）。 */
export async function signedUrl(path: string, ttlSeconds = 600): Promise<string> {
  const res = await cloud.storage.createSignedUrl(path, ttlSeconds)
  if (res.error) throw new Error(res.error.message)
  const data = res.data as { signedUrl?: string; url?: string }
  return data.signedUrl ?? data.url ?? ''
}
