/** 图片上传组件：拖拽/点击选择、前端即时校验（格式/大小，与后端一致）、预览；
 * 校验不通过即时提示且不发请求（docs/api_doc.md 4.6，D36） */

import { App, Button, Upload } from 'antd'
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'

import { ALLOWED_EXTENSIONS, MAX_UPLOAD_MB } from '../../constants/validation'
import { useObjectUrl } from '../../hooks/useObjectUrl'

interface ImageUploaderProps {
  file: File | null
  disabled?: boolean
  onChange: (file: File | null) => void
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

export default function ImageUploader({ file, disabled = false, onChange }: ImageUploaderProps) {
  const { message } = App.useApp()
  const previewUrl = useObjectUrl(file)

  const beforeUpload: UploadProps['beforeUpload'] = (uploaded) => {
    const dot = uploaded.name.lastIndexOf('.')
    const ext = (dot >= 0 ? uploaded.name.slice(dot) : '').toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      message.error(`图片格式不支持，仅支持 ${ALLOWED_EXTENSIONS.join('/')}`)
      return Upload.LIST_IGNORE
    }
    if (uploaded.size > MAX_UPLOAD_MB * 1024 * 1024) {
      message.error(`图片大小不能超过 ${MAX_UPLOAD_MB}MB`)
      return Upload.LIST_IGNORE
    }
    onChange(uploaded as File)
    return false
  }

  if (file) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-white p-4">
        <div className="flex flex-col items-center gap-4 sm:flex-row">
          <img
            src={previewUrl ?? undefined}
            alt="上传预览"
            className="h-40 w-full rounded-lg border border-gray-200 bg-gray-100 object-contain sm:w-52"
          />
          <div className="flex w-full flex-col gap-2 text-center sm:w-auto sm:text-left">
            <span className="truncate text-sm font-medium">{file.name}</span>
            <span className="text-xs text-gray-500">{formatSize(file.size)}</span>
            <div className="flex justify-center gap-2 sm:justify-start">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                disabled={disabled}
                onClick={() => onChange(null)}
              >
                重新选择
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <Upload.Dragger
      accept={ALLOWED_EXTENSIONS.join(',')}
      beforeUpload={beforeUpload}
      disabled={disabled}
      showUploadList={false}
      maxCount={1}
    >
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">点击或拖拽图片到此处上传</p>
      <p className="ant-upload-hint">
        支持 {ALLOWED_EXTENSIONS.join(' / ')}，大小不超过 {MAX_UPLOAD_MB}MB
      </p>
    </Upload.Dragger>
  )
}
