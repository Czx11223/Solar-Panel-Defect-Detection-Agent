/** 登录态管理：token 存 localStorage（D35），profile 由 /api/user/profile 拉取 */

import { useCallback, useEffect, useState } from 'react'

import { fetchProfile } from '../api/auth'
import { signOutCloud } from '../cloud/auth'
import type { UserProfile } from '../types/auth'
import { clearAuth, getToken, setToken } from '../utils/storage'

export interface UseAuthResult {
  token: string | null
  profile: UserProfile | null
  login: (token: string) => void
  logout: () => void
}

export function useAuth(): UseAuthResult {
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [profile, setProfile] = useState<UserProfile | null>(null)

  const refreshProfile = useCallback(async () => {
    if (!getToken()) {
      setProfile(null)
      return
    }
    try {
      setProfile(await fetchProfile())
    } catch {
      // 401/网络异常已由拦截器统一提示；这里保持 profile 为空即可
      setProfile(null)
    }
  }, [])

  // 业务请求使用应用 JWT（登录时由云端票据兑换，24h 有效），挂载时只需读取本地登录态。
  // 不再在每次挂载时同步云端会话：云会话查询抖动会误清登录态，表现为"切模块被踢"。
  useEffect(() => {
    void (async () => {
      if (!getToken()) {
        setProfile(null)
        return
      }
      await refreshProfile()
    })()
  }, [refreshProfile])

  const login = useCallback((nextToken: string) => {
    setToken(nextToken)
    setTokenState(nextToken)
  }, [])

  const logout = useCallback(() => {
    // 云端会话也要销毁，否则下次打开还会自动登录
    void signOutCloud().finally(() => {
      clearAuth()
      setTokenState(null)
      setProfile(null)
    })
  }, [])

  return { token, profile, login, logout }
}
