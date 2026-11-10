/** 智能问答 API：会话与消息存放在云端（Cloud Database），
 *  对话由浏览器端 Agent 循环直接调用云端大模型（keyless），工具回打本服务后端执行。
 */

import { runAgent } from '../agent/loop'
import { cloud } from '../cloud/client'
import * as store from '../cloud/chat'
import { PREFERRED_MODELS } from '../cloud/publicConfig'

export interface AgentEvent {
  type: 'meta' | 'reasoning' | 'delta' | 'tool_call' | 'tool_result' | 'done' | 'error'
  session_id?: number
  model?: string
  content?: string
  name?: string
  arguments?: string
  ok?: boolean
  error?: string | null
  preview?: string
  message_id?: number
  rounds?: number
  usage?: { prompt_tokens: number; completion_tokens: number }
  code?: number
  message?: string
}

export interface AgentSession {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface AgentMessage {
  id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  reasoning: string | null
  tool_calls: { id: string; function: { name: string; arguments: string } }[] | null
  tool_name: string | null
  created_at: string
}

export interface AgentStatus {
  llm_ready: boolean
  model: string
  base_url: string
  message: string
}

/** 启动一轮对话；事件流形态与旧版服务端 SSE 一致。 */
export async function streamChat(
  params: { message: string; sessionId?: number | null; signal?: AbortSignal },
  onEvent: (e: AgentEvent) => void,
): Promise<void> {
  await runAgent({
    message: params.message,
    sessionId: params.sessionId ?? null,
    signal: params.signal,
    onEvent,
  })
}

export async function fetchSessions(): Promise<{ sessions: AgentSession[] }> {
  return { sessions: await store.listSessions() }
}

export async function fetchMessages(sessionId: number): Promise<{ messages: AgentMessage[] }> {
  const rows = await store.listMessages(sessionId)
  return {
    messages: rows.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      reasoning: m.reasoning,
      tool_calls: m.tool_calls,
      tool_name: m.tool_name,
      created_at: m.created_at,
    })),
  }
}

export async function deleteSession(sessionId: number): Promise<{ deleted: boolean }> {
  await store.deleteSession(sessionId)
  return { deleted: true }
}

/** 云端模型可用性（前端用于顶部状态标签与错误提示）。 */
export async function fetchAgentStatus(): Promise<AgentStatus> {
  try {
    const models = await cloud.llm.models.list()
    const usable = models.filter((m) => m.disabled !== true && m.supportsToolCall !== false)
    const preferred = PREFERRED_MODELS
      .map((id) => usable.find((m) => m.id === id))
      .find(Boolean)
    const model = preferred?.id ?? usable[0]?.id ?? models[0]?.id ?? ''
    return {
      llm_ready: Boolean(model),
      model: preferred?.name ?? model ?? '云端模型',
      base_url: 'cloud',
      message: model ? 'ok' : '云端暂无可用的工具型大模型',
    }
  } catch (e) {
    return {
      llm_ready: false,
      model: '',
      base_url: 'cloud',
      message: (e as Error).message || '云端模型服务不可用',
    }
  }
}
