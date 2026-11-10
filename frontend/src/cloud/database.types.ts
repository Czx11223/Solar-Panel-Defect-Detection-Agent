/**
 * 云数据库表类型（供 createWorkBuddyCloud<Database> 使用，对齐 supabase 的 schema 语义）。
 *
 * 字段与云 PostgreSQL 实际结构一致：
 * - owner_id 由 DEFAULT auth.uid() 填充，前端永不发送；
 * - created_at / updated_at 由数据库默认值填充；
 * - 因此 Insert 只需业务字段，其余可选。
 */

export interface AgentSessionRow {
  id: number
  owner_id: string
  owner_name: string | null
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface AgentMessageRow {
  id: number
  owner_id: string
  session_id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  reasoning: string | null
  tool_calls: unknown | null
  tool_call_id: string | null
  tool_name: string | null
  tokens_in: number
  tokens_out: number
  created_at: string
}

export interface DetectAssetRow {
  id: number
  owner_id: string
  owner_name: string | null
  record_id: number
  kind: 'original' | 'annotated'
  storage_path: string
  content_type: string | null
  size_bytes: number | null
  created_at: string
}

export interface TicketPayload {
  uid: string
  exp: number
  sig: string
  email?: string
  name?: string
}

export interface Database {
  public: {
    Tables: {
      agent_session: {
        Row: AgentSessionRow
        Insert: Partial<AgentSessionRow> & { title?: string }
        Update: Partial<AgentSessionRow>
        Relationships: []
      }
      agent_message: {
        Row: AgentMessageRow
        Insert: Partial<AgentMessageRow> & { session_id: number; role: string }
        Update: Partial<AgentMessageRow>
        Relationships: []
      }
      detect_asset: {
        Row: DetectAssetRow
        Insert: Partial<DetectAssetRow> & { record_id: number; kind: string; storage_path: string }
        Update: Partial<DetectAssetRow>
        Relationships: []
      }
    }
    Views: Record<string, never>
    Functions: {
      issue_ticket: {
        Args: Record<string, never>
        Returns: TicketPayload
      }
    }
    Enums: Record<string, never>
    CompositeTypes: Record<string, never>
  }
}
