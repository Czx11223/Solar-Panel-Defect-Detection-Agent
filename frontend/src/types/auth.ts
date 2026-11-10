/** 认证与用户模块类型（对齐 docs/api_doc.md 4.1–4.5） */

export interface RegisterRequest {
  username: string
  password: string
  email?: string | null
  nickname?: string | null
}

export interface RegisterResponse {
  user_id: number
  username: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface UserProfile {
  user_id: number
  username: string
  email: string | null
  nickname: string | null
  created_at: string
}
