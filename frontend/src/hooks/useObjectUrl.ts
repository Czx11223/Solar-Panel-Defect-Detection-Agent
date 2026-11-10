/** File → objectURL，file 变化或卸载时自动 revoke（上传预览用，frontend_web_spec.md 5.4） */

import { useEffect, useState } from 'react'

export function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!file) {
      setUrl(null)
      return undefined
    }
    const created = URL.createObjectURL(file)
    setUrl(created)
    return () => URL.revokeObjectURL(created)
  }, [file])

  return url
}
