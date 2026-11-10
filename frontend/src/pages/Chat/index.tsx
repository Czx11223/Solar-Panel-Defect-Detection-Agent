/** 智能问答页：LLM Agent 对话（SSE 流式）。
 *  - 会话管理：左侧会话列表（新建/切换/删除），历史消息回放
 *  - 流式渲染：正文 Markdown、思维链折叠、工具调用过程卡片
 *  - 中断：AbortController 停止生成
 */

import {
  DeleteOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { App as AntApp, Alert, Button, Collapse, Drawer, Empty, Input, Popconfirm, Tag, Tooltip } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import {
  AgentEvent,
  AgentSession,
  AgentStatus,
  deleteSession,
  fetchAgentStatus,
  fetchMessages,
  fetchSessions,
  streamChat,
} from '../../api/agent'
import { ApiError } from '../../api/client'
import { clearAuth } from '../../utils/storage'

interface ToolEvent {
  name: string
  args: string
  ok?: boolean
  error?: string | null
  preview?: string
}

interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  tools?: ToolEvent[]
  error?: string
}

const SUGGESTIONS = [
  '知识库里说单图推理耗时的指标口径是什么？',
  '积灰类缺陷的运维建议是什么？',
  '帮我统计一下全部检测记录的缺陷分布',
]

let _uid = 0
const uid = () => `m${Date.now()}_${_uid++}`

export default function ChatPage() {
  const { message } = AntApp.useApp()
  const [sessions, setSessions] = useState<AgentSession[]>([])
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const refreshSessions = useCallback(async () => {
    try {
      const data = await fetchSessions()
      setSessions(data.sessions)
    } catch { /* 忽略：列表刷新失败不阻塞对话 */ }
  }, [])

  useEffect(() => {
    fetchAgentStatus().then(setStatus).catch(() => setStatus(null))
    void refreshSessions()
  }, [refreshSessions])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const patchLastAssistant = (fn: (m: ChatMsg) => ChatMsg) => {
    setMessages((prev) => {
      const idx = [...prev].reverse().findIndex((m) => m.role === 'assistant')
      if (idx < 0) return prev
      const real = prev.length - 1 - idx
      return [...prev.slice(0, real), fn(prev[real]), ...prev.slice(real + 1)]
    })
  }

  const handleEvent = (e: AgentEvent) => {
    switch (e.type) {
      case 'meta':
        if (e.session_id) setSessionId(e.session_id)
        break
      case 'reasoning':
        patchLastAssistant((m) => ({ ...m, reasoning: (m.reasoning ?? '') + (e.content ?? '') }))
        break
      case 'delta':
        patchLastAssistant((m) => ({ ...m, content: m.content + (e.content ?? '') }))
        break
      case 'tool_call':
        patchLastAssistant((m) => ({
          ...m,
          tools: [...(m.tools ?? []), { name: e.name ?? '', args: e.arguments ?? '' }],
        }))
        break
      case 'tool_result':
        patchLastAssistant((m) => {
          const tools = [...(m.tools ?? [])]
          if (tools.length) {
            tools[tools.length - 1] = {
              ...tools[tools.length - 1],
              ok: e.ok, error: e.error, preview: e.preview,
            }
          }
          return { ...m, tools }
        })
        break
      case 'done':
        break
      case 'error':
        patchLastAssistant((m) => ({ ...m, error: e.message ?? '处理失败' }))
        message.error(e.message ?? '智能体处理失败')
        break
    }
  }

  const send = async () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setStreaming(true)
    setMessages((prev) => [
      ...prev,
      { id: uid(), role: 'user', content: text },
      { id: uid(), role: 'assistant', content: '', tools: [] },
    ])
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat({ message: text, sessionId }, handleEvent)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : '发送失败，请重试'
      if (e instanceof ApiError && e.code === 40101) clearAuth()
      patchLastAssistant((m) => ({ ...m, error: msg }))
      message.error(msg)
    } finally {
      setStreaming(false)
      abortRef.current = null
      void refreshSessions()
    }
  }

  const stop = () => {
    abortRef.current?.abort()
    setStreaming(false)
  }

  const loadSession = async (sid: number) => {
    if (streaming) stop()
    setSessionId(sid)
    setDrawerOpen(false)
    try {
      const data = await fetchMessages(sid)
      const list: ChatMsg[] = []
      for (const m of data.messages) {
        if (m.role === 'user') {
          list.push({ id: uid(), role: 'user', content: m.content })
        } else if (m.role === 'assistant') {
          list.push({
            id: uid(),
            role: 'assistant',
            content: m.content,
            reasoning: m.reasoning ?? undefined,
            tools: (m.tool_calls ?? []).map((tc) => ({
              name: tc.function.name, args: tc.function.arguments,
            })),
          })
        }
        // role=tool 的结果已在 assistant.tool_calls 中体现，历史不单独展示
      }
      setMessages(list)
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : '加载会话失败')
    }
  }

  const newSession = () => {
    if (streaming) stop()
    setSessionId(null)
    setMessages([])
    setDrawerOpen(false)
  }

  const removeSession = async (sid: number) => {
    try {
      await deleteSession(sid)
      if (sessionId === sid) newSession()
      void refreshSessions()
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : '删除失败')
    }
  }

  const renderMsg = (m: ChatMsg) => {
    if (m.role === 'user') {
      return (
        <div key={m.id} className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-sky-500 px-4 py-2 text-sm text-white shadow-sm md:max-w-[70%]">
            <p className="whitespace-pre-wrap break-words">{m.content}</p>
          </div>
        </div>
      )
    }
    return (
      <div key={m.id} className="flex justify-start">
        <div className="w-full max-w-full rounded-2xl rounded-bl-sm border border-gray-100 bg-white px-4 py-3 text-sm shadow-sm md:max-w-[85%]">
          {m.reasoning ? (
            <Collapse
              size="small"
              className="mb-2"
              items={[{
                key: 'r',
                label: <span className="text-xs text-gray-400">思考过程</span>,
                children: (
                  <p className="whitespace-pre-wrap break-words text-xs leading-6 text-gray-500">
                    {m.reasoning}
                  </p>
                ),
              }]}
            />
          ) : null}

          {m.tools?.length ? (
            <div className="mb-2 flex flex-col gap-1.5">
              {m.tools.map((t, i) => (
                <Tooltip key={i} title={<code className="text-[11px]">{t.args}</code>}>
                  <div className="flex items-center gap-2 rounded-lg bg-gray-50 px-2.5 py-1.5 text-xs text-gray-600">
                    <ToolOutlined className="text-sky-500" />
                    <span className="font-medium">{t.name}</span>
                    {t.ok === undefined ? (
                      <Tag color="processing">执行中</Tag>
                    ) : t.ok ? (
                      <Tag color="success">完成</Tag>
                    ) : (
                      <Tag color="error">失败</Tag>
                    )}
                    {t.error ? <span className="truncate text-red-400">{t.error}</span> : null}
                  </div>
                </Tooltip>
              ))}
            </div>
          ) : null}

          {m.content ? (
            <div className="prose prose-sky prose-sm max-w-none break-words prose-p:my-1.5 prose-table:text-xs">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
            </div>
          ) : !m.tools?.length && !m.error ? (
            <span className="text-gray-400">正在思考…</span>
          ) : null}

          {m.error ? (
            <p className="mt-1 text-xs text-red-500">{m.error}</p>
          ) : null}
        </div>
      </div>
    )
  }

  const sessionList = (
    <div className="flex h-full flex-col">
      <Button type="primary" icon={<PlusOutlined />} className="mb-3" onClick={newSession}>
        新会话
      </Button>
      <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <Empty description="暂无会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              className={`group flex cursor-pointer items-center justify-between rounded-lg px-2.5 py-2 text-sm transition-colors ${
                sessionId === s.id ? 'bg-sky-50 text-sky-600' : 'text-gray-600 hover:bg-gray-50'
              }`}
              onClick={() => void loadSession(s.id)}
            >
              <div className="min-w-0">
                <p className="truncate">{s.title}</p>
                <p className="text-[11px] text-gray-400">{s.message_count} 条消息</p>
              </div>
              <Popconfirm
                title="删除会话"
                description="将同时删除会话内的全部消息"
                onConfirm={(e) => { e?.stopPropagation(); void removeSession(s.id) }}
                onCancel={(e) => e?.stopPropagation()}
              >
                <Button
                  type="text" size="small" danger icon={<DeleteOutlined />}
                  onClick={(e) => e.stopPropagation()}
                />
              </Popconfirm>
            </div>
          ))
        )}
      </div>
    </div>
  )

  return (
    <div className="mx-auto flex h-[calc(100vh-11.5rem)] max-w-6xl gap-4">
      {/* 桌面侧栏 */}
      <aside className="hidden w-60 shrink-0 rounded-2xl border border-gray-100 bg-white p-3 shadow-sm lg:block">
        {sessionList}
      </aside>

      {/* 移动端抽屉 */}
      <Drawer title="会话列表" open={drawerOpen} onClose={() => setDrawerOpen(false)} width={280}>
        {sessionList}
      </Drawer>

      <section className="flex min-w-0 flex-1 flex-col rounded-2xl border border-gray-100 bg-white shadow-sm">
        <header className="flex items-center justify-between border-b border-gray-100 px-4 py-2.5">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <RobotOutlined className="text-sky-500" />
            光伏检测智能助手
            {status ? (
              <Tag color={status.llm_ready ? 'success' : 'warning'} className="ml-1">
                {status.llm_ready ? status.model : 'LLM 未配置'}
              </Tag>
            ) : null}
          </div>
          <Button
            type="text" size="small" icon={<PlusOutlined />} className="lg:hidden"
            onClick={() => setDrawerOpen(true)}
          >
            会话
          </Button>
        </header>

        {status && !status.llm_ready ? (
          <Alert
            className="m-3" type="warning" showIcon
            message="大模型服务未就绪"
            description={status.message}
          />
        ) : null}

        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <RobotOutlined className="text-4xl text-sky-200" />
              <p className="text-sm text-gray-500">
                我是光伏检测智能助手，可以帮你解读检测结果、查询历史记录、解答项目知识。
              </p>
              <div className="flex flex-col gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} size="small" className="rounded-full" onClick={() => setInput(s)}>
                    {s}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            messages.map(renderMsg)
          )}
          <div ref={bottomRef} />
        </div>

        <footer className="border-t border-gray-100 p-3">
          <div className="flex items-end gap-2">
            <Input.TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={streaming}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault()
                  void send()
                }
              }}
              className="rounded-xl"
            />
            {streaming ? (
              <Button danger icon={<StopOutlined />} onClick={stop}>停止</Button>
            ) : (
              <Button
                type="primary" icon={<SendOutlined />} disabled={!input.trim()}
                onClick={() => void send()}
              >
                发送
              </Button>
            )}
          </div>
        </footer>
      </section>
    </div>
  )
}
