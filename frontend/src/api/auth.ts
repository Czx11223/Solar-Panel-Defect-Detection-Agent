/** 认证与用户接口（docs/api_doc.md 4.1–4.3） */

import { get, post } from './client'

import type {
  LoginRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
  UserProfile,
} from '../types/auth'

export function register(data: RegisterRequest): Promise<RegisterResponse> {
  return post<RegisterResponse>('/auth/register', data)
}

export function login(data: LoginRequest): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/login', data)
}

export function fetchProfile(): Promise<UserProfile> {
  return get<UserProfile>('/user/profile')
}
