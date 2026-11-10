/**
 * 浏览器端 Agent 循环（云端大模型 + 服务端工具）。
 *
 * 为什么在前端跑循环：
 * 云端大模型是 keyless 的、按应用 Origin 授权，只能由应用前端直接调用；服务端不代理模型请求。
 * 因此循环、上下文拼装、工具编排都在浏览器完成，工具本身仍然只在服务端实现一份，
 * 通过 /api/agent/tools/{name} 执行，模型拿不到任何直连数据库的能力。
 *
 * 事件协议与旧的服务端 SSE 完全一致（meta / reasoning / delta / tool_call / tool_result / done / error），
 * 页面渲染逻辑不需要改。
 */

import { get, post } from '../api/client'
import { fetchFileBlob } from '../api/record'
import type { AgentEvent } from '../api/agent'
import * as store from '../cloud/chat'
import { cloud } from '../cloud/client'
import { PREFERRED_MODELS } from '../cloud/publicConfig'

const MAX_ROUNDS = 6
const TOOL_RESULT_MAX_CHARS = 8000

const SYSTEM_PROMPT = `你是"光伏面板检测智能助手"，服务于光伏面板缺陷检测系统（YOLOv8 + FastAPI + React），
面向电站巡检与运维人员，回答须使用简体中文。

【你的能力】
你可以调用系统内置工具完成以下任务：
1. 图像缺陷检测：读取已上传巡检图像的检测结果，输出缺陷类别、置信度框与运维建议；
2. 检测记录查询与统计：按时间范围、缺陷类别查询历史记录并聚合统计；
3. 光伏知识库检索：检索项目知识库（系统架构、算法指标、部署运维等）回答专业问题；
4. 图像内容解读：调用视觉能力对检测结果图做自然语言解读。

【工具使用规则】
1. 涉及检测图像时，用户消息中的图像引用格式为 record_id（如 #12 或 record_id=12），
   调用工具时使用该整数ID；用户未上传图像而要求检测时，引导其先在"检测"页面上传。
2. 一次回答需要多个信息时尽量并行调用独立工具；有依赖的调用按顺序进行。
3. 工具失败时如实告知失败原因，不得编造检测结果或统计数据。
4. 工具返回的数据可直接引用，不需要向用户复述原始 JSON。

【业务指标口径（不得修改或近似表述）】
- 缺陷类别：清洁、积灰、鸟粪、电损伤、物理损伤、积雪（六类，类别ID 0-5）；
- 置信度阈值 0.25、NMS IoU 0.45、模型输入 640、上传上限 10MB（jpg/jpeg/png/bmp）；
- 运维建议置信度三档：≥0.75 高（立即处理）、0.5–0.75 中（近期安排）、<0.5 低（持续观察）；
- 单图推理耗时 ≤ 200ms（CPU onnxruntime）为设计目标值，实际以部署实测为准。

【局限性声明（涉及检测结果可信度、模型适用边界、数据隐私时必须先说明）】
- 检测结果为 AI 辅助判断，置信度不等于缺陷确诊，重大缺陷须人工复核；
- 类别外缺陷（如隐裂、蜗牛纹等未训练类别）不在检测能力范围；
- 检测图像与对话记录保存在云端（WorkBuddy 云服务，仅本人可访问），不用于训练；
- 你生成的建议基于知识库与规则模板，不替代专业运维规程。

【回答风格】
- 先给结论，再给依据；数字与专业术语准确；
- 引用知识库时注明依据章节；检测结果引用 record_id 与置信度；
- 适当使用 Markdown 结构（标题/列表/表格）组织较长回答。`

interface ToolSchema {
  type: 'function'
  function: { name: string; description: string; parameters: Record<string, unknown> }
}

interface ToolCall {
  id: string
  type: string
  function: { name: string; arguments: string }
}

type ChatMessage = Record<string, unknown>

interface ToolOutcome {
  ok: boolean
  data: unknown
  error: string | null
}

let _tools: ToolSchema[] | null = null
let _model: string | null = null

function clip(text: string): string {
  return text.length <= TOOL_RESULT_MAX_CHARS
    ? text
    : `${text.slice(0, TOOL_RESULT_MAX_CHARS)}\n…（结果过长已截断，原长度 ${text.length} 字符）`
}

/** 工具声明只保留服务端一份，前端按需拉取。 */
async function loadTools(): Promise<ToolSchema[]> {
  if (_tools) return _tools
  const res = await get<{ tools: ToolSchema[] }>('/agent/tools')
  _tools = res.tools
  return _tools
}

/** 选模型：优先 Kimi-K3（同族替代原 kimi-k3.1-pro），否则首个支持工具的可用模型。 */
async function pickModel(): Promise<string> {
  if (_model) return _model
  const models = await cloud.llm.models.list()
  const usable = models.filter((m) => m.disabled !== true && m.supportsToolCall !== false)
  for (const id of PREFERRED_MODELS) {
    const hit = usable.find((m) => m.id === id)
    if (hit) {
      _model = hit.id
      return _model
    }
  }
  const fallback = usable[0] ?? models[0]
  if (!fallback) throw new Error('云端暂无可用大模型，请稍后再试')
  _model = fallback.id
  return _model
}

/** 知识库/记录类工具统一走后端；视觉工具在浏览器直接调云端多模态。 */
async function execTool(name: string, rawArgs: string): Promise<ToolOutcome> {
  let args: Record<string, unknown> = {}
  if (rawArgs && rawArgs.trim()) {
    try {
      args = JSON.parse(rawArgs) as Record<string, unknown>
    } catch {
      return { ok: false, data: null, error: `工具参数不是合法 JSON：${rawArgs.slice(0, 80)}` }
    }
  }
  if (name === 'interpret_image') {
    try {
      return await interpretImage(Number(args.record_id))
    } catch (e) {
      // 云端视觉不可用时回落到服务端实现（若后端配置了自备密钥）
      try {
        return await post<ToolOutcome>(`/agent/tools/${name}`, { arguments: args })
      } catch {
        return { ok: false, data: null, error: (e as Error).message }
      }
    }
  }
  return post<ToolOutcome>(`/agent/tools/${name}`, { arguments: args })
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('结果图读取失败'))
    reader.readAsDataURL(blob)
  })
}

const VISION_PROMPT =
  '你是光伏电站巡检助手。请解读这张光伏面板缺陷检测结果图：' +
  '1. 描述图上可见的面板状态与标注框位置；' +
  '2. 指出可疑区域的形态特征（如积灰分布、鸟粪附着、裂纹走向等，仅基于可见内容描述）；' +
  '3. 提醒：这是 AI 辅助标注结果，置信度不等于缺陷确诊，重大缺陷须人工复核。' +
  '回答使用简体中文，不超过 300 字。'

async function interpretImage(recordId: number): Promise<ToolOutcome> {
  if (!Number.isFinite(recordId)) {
    return { ok: false, data: null, error: 'record_id 必须是整数' }
  }
  const base = await post<ToolOutcome>('/agent/tools/detect_image', {
    arguments: { record_id: recordId },
  })
  const detail = base.data as { result_image_url?: string; image_name?: string } | null
  if (!base.ok || !detail?.result_image_url) {
    return { ok: false, data: null, error: base.error || `记录 ${recordId} 没有结果图` }
  }
  const blob = await fetchFileBlob(detail.result_image_url)
  const dataUrl = await blobToDataUrl(blob)
  const model = await pickModel()

  let text = ''
  for await (const chunk of cloud.llm.chat.completions.create({
    model,
    messages: [
      {
        role: 'user',
        content: [
          { type: 'text', text: VISION_PROMPT },
          { type: 'image_url', image_url: { url: dataUrl } },
        ],
      },
    ] as never,
    stream: true,
  })) {
    const delta = chunk.choices?.[0]?.delta as { content?: string } | undefined
    if (delta?.content) text += delta.content
  }
  if (!text.trim()) throw new Error('视觉模型未返回内容')
  return {
    ok: true,
    data: {
      record_id: recordId,
      image_name: detail.image_name ?? null,
      interpretation: text.trim(),
      note: '解读基于标注图可见内容，须结合结构化检测结果综合判断',
    },
    error: null,
  }
}

function buildMessages(history: store.CloudMessage[], userText: string): ChatMessage[] {
  const messages: ChatMessage[] = [{ role: 'system', content: SYSTEM_PROMPT }]
  for (const m of history) {
    if (m.role === 'user') {
      messages.push({ role: 'user', content: m.content })
    } else if (m.role === 'assistant') {
      const msg: ChatMessage = { role: 'assistant', content: m.content || '' }
      // 多轮工具循环必须原样回传思考内容与工具调用，否则上下文断裂
      if (m.reasoning) msg.reasoning_content = m.reasoning
      if (m.tool_calls?.length) msg.tool_calls = m.tool_calls
      messages.push(msg)
    } else if (m.role === 'tool') {
      messages.push({
        role: 'tool',
        tool_call_id: m.tool_call_id ?? '',
        content: m.content,
      })
    }
  }
  messages.push({ role: 'user', content: userText })
  return messages
}

interface RoundResult {
  content: string
  reasoning: string
  toolCalls: ToolCall[]
  finishReason: string | null
  usage: { prompt_tokens: number; completion_tokens: number }
}

export interface RunAgentParams {
  message: string
  sessionId?: number | null
  signal?: AbortSignal
  onEvent: (e: AgentEvent) => void
}

/** 执行一轮 User 消息的完整 Agent 交互；返回会话 ID。 */
export async function runAgent(params: RunAgentParams): Promise<number> {
  const { message, signal, onEvent } = params
  let sessionId = params.sessionId ?? null

  try {
    if (sessionId === null) {
      sessionId = await store.createSession(message.replace(/\s+/g, ' ').slice(0, 20))
    }
    const history = await store.listMessages(sessionId)
    await store.appendUserMessage(sessionId, message)

    const model = await pickModel()
    onEvent({ type: 'meta', session_id: sessionId, model })

    const tools = await loadTools()
    const messages = buildMessages(history, message)
    const usageTotal = { prompt_tokens: 0, completion_tokens: 0 }

    for (let round = 0; round < MAX_ROUNDS; round += 1) {
      const result = await streamRound({ model, messages, tools, onEvent, signal })
      usageTotal.prompt_tokens += result.usage.prompt_tokens
      usageTotal.completion_tokens += result.usage.completion_tokens

      const assistant: ChatMessage = { role: 'assistant', content: result.content }
      if (result.reasoning) assistant.reasoning_content = result.reasoning
      if (result.toolCalls.length) assistant.tool_calls = result.toolCalls

      await store.appendAssistantMessage(sessionId, {
        content: result.content,
        reasoning: result.reasoning || null,
        toolCalls: result.toolCalls.length ? result.toolCalls : null,
        tokensIn: result.usage.prompt_tokens,
        tokensOut: result.usage.completion_tokens,
      })
      messages.push(assistant)

      if (result.finishReason !== 'tool_calls' || result.toolCalls.length === 0) {
        onEvent({
          type: 'done', session_id: sessionId, rounds: round + 1, usage: usageTotal,
        })
        return sessionId
      }

      for (const call of result.toolCalls) {
        const name = call.function?.name ?? ''
        const rawArgs = call.function?.arguments ?? '{}'
        onEvent({ type: 'tool_call', name, arguments: rawArgs })

        const outcome = await execTool(name, rawArgs)
        const payload = outcome.ok
          ? { ok: true, data: outcome.data }
          : { ok: false, error: outcome.error }
        const text = clip(JSON.stringify(payload, null, 0))

        onEvent({
          type: 'tool_result',
          name,
          ok: outcome.ok,
          error: outcome.error,
          preview: text.slice(0, 200),
        })
        await store.appendToolMessage(sessionId, {
          content: text,
          toolCallId: call.id || `call_${name}`,
          toolName: name,
        })
        messages.push({ role: 'tool', tool_call_id: call.id || `call_${name}`, content: text })
      }
    }

    // 达到轮次上限：不再给工具，让模型基于已有信息收尾
    messages.push({
      role: 'user',
      content: '（系统提示：已达单次回答工具调用上限，请基于以上信息直接给出最终回答，不再调用工具。）',
    })
    const final = await streamRound({ model, messages, tools: null, onEvent, signal })
    await store.appendAssistantMessage(sessionId, {
      content: final.content,
      reasoning: final.reasoning || null,
      tokensIn: final.usage.prompt_tokens,
      tokensOut: final.usage.completion_tokens,
    })
    onEvent({
      type: 'done',
      session_id: sessionId,
      rounds: MAX_ROUNDS + 1,
      usage: {
        prompt_tokens: usageTotal.prompt_tokens + final.usage.prompt_tokens,
        completion_tokens: usageTotal.completion_tokens + final.usage.completion_tokens,
      },
    })
    return sessionId
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      return sessionId ?? 0
    }
    const msg = (e as { error?: { message?: string }; message?: string }).error?.message
      ?? (e as Error).message
      ?? '智能体处理失败'
    onEvent({ type: 'error', code: 50000, message: msg })
    if (sessionId) return sessionId
    throw e
  }
}

interface StreamRoundParams {
  model: string
  messages: ChatMessage[]
  tools: ToolSchema[] | null
  onEvent: (e: AgentEvent) => void
  signal?: AbortSignal
}

/** 单轮流式调用：边收边渲染，结束时汇总正文/思考/工具调用。 */
async function streamRound({
  model, messages, tools, onEvent, signal,
}: StreamRoundParams): Promise<RoundResult> {
  const contentParts: string[] = []
  const reasoningParts: string[] = []
  const acc = new Map<number, ToolCall>()
  let finishReason: string | null = null
  let usage = { prompt_tokens: 0, completion_tokens: 0 }

  for await (const chunk of cloud.llm.chat.completions.create({
    model,
    messages: messages as never,
    ...(tools && tools.length ? { tools: tools as never } : {}),
    stream: true,
    stream_options: { include_usage: true },
    ...(signal ? { signal } : {}),
  })) {
    if (chunk.usage) {
      usage = {
        prompt_tokens: chunk.usage.prompt_tokens ?? 0,
        completion_tokens: chunk.usage.completion_tokens ?? 0,
      }
    }
    const choice = chunk.choices?.[0]
    if (!choice) continue
    if (choice.finish_reason) finishReason = choice.finish_reason
    const delta = choice.delta as {
      content?: string
      reasoning_content?: string
      tool_calls?: { index?: number; id?: string; function?: { name?: string; arguments?: string } }[]
    } | undefined
    if (!delta) continue

    if (delta.reasoning_content) {
      reasoningParts.push(delta.reasoning_content)
      onEvent({ type: 'reasoning', content: delta.reasoning_content })
    }
    if (delta.content) {
      contentParts.push(delta.content)
      onEvent({ type: 'delta', content: delta.content })
    }
    for (const tc of delta.tool_calls ?? []) {
      const idx = tc.index ?? 0
      const cur = acc.get(idx) ?? { id: '', type: 'function', function: { name: '', arguments: '' } }
      if (tc.id) cur.id = tc.id
      if (tc.function?.name) cur.function.name += tc.function.name
      if (tc.function?.arguments) cur.function.arguments += tc.function.arguments
      acc.set(idx, cur)
    }
  }

  return {
    content: contentParts.join(''),
    reasoning: reasoningParts.join(''),
    toolCalls: [...acc.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v),
    finishReason,
    usage,
  }
}
