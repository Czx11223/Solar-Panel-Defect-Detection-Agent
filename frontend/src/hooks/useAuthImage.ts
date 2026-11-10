/** 鉴权图片加载：axios blob → objectURL（<img> 无法携带 Authorization 头），
 * 组件卸载或 url 变化时自动 revoke，避免内存泄漏（frontend_web_spec.md 5.4） */

import { useEffect, useState } from 'react'

import { fetchFileBlob } from '../api/record'

export function useAuthImage(url: string | null): string | null {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let created: string | null = null
    setObjectUrl(null)
    if (!url) {
      return undefined
    }
    fetchFileBlob(url)
      .then((blob) => {
        if (cancelled) {
          return
        }
        created = URL.createObjectURL(blob)
        setObjectUrl(created)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      if (created) {
        URL.revokeObjectURL(created)
      }
    }
  }, [url])

  return objectUrl
}
