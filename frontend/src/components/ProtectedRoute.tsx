/** 鉴权路由守卫：未登录（无 token）访问受保护页面 → 跳转 /login 并记录来源 */

import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { clearAuth, getToken } from '../utils/storage'

/** 解析 JWT payload 的 exp 做本地预检，避免过期令牌先进入页面再等首个 401 才跳转。 */
function isTokenUsable(token: string): boolean {
  try {
    const segment = token.split('.')[1]
    if (!segment) return false
    const normalized = segment.replace(/-/g, '+').replace(/_/g, '/')
    const payload = JSON.parse(atob(normalized)) as { exp?: number }
    return typeof payload.exp === 'number' && payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const location = useLocation()
  const token = getToken()

  if (!token || !isTokenUsable(token)) {
    if (token) clearAuth()
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}
