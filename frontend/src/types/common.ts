/** 后端统一响应结构 {code, message, data}（见 docs/api_doc.md 2.3） */
export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}
