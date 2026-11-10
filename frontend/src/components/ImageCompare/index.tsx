/** 原图/结果图对比：鉴权图片经 blob 加载（<img> 无法携带 Authorization 头）；
 * 桌面端左右并排、移动端上下堆叠（D37） */

import { Spin } from 'antd'

import { useAuthImage } from '../../hooks/useAuthImage'

interface ImageCompareProps {
  leftLabel: string
  leftUrl: string | null
  rightLabel: string
  rightUrl: string | null
}

export default function ImageCompare({
  leftLabel,
  leftUrl,
  rightLabel,
  rightUrl,
}: ImageCompareProps) {
  const left = useAuthImage(leftUrl)
  const right = useAuthImage(rightUrl)

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <p className="mb-1 text-sm font-medium text-gray-700">{leftLabel}</p>
        {left ? (
          <img
            src={left}
            alt={leftLabel}
            className="w-full rounded-lg border border-gray-200 bg-gray-100"
          />
        ) : (
          <div className="flex h-48 items-center justify-center rounded-lg bg-gray-50">
            <Spin />
          </div>
        )}
      </div>
      <div>
        <p className="mb-1 text-sm font-medium text-gray-700">{rightLabel}</p>
        {right ? (
          <img
            src={right}
            alt={rightLabel}
            className="w-full rounded-lg border border-gray-200 bg-gray-100"
          />
        ) : (
          <div className="flex h-48 items-center justify-center rounded-lg bg-gray-50">
            <Spin />
          </div>
        )}
      </div>
    </div>
  )
}
