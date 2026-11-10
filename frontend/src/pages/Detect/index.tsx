/** 检测首页：上传 → 检测（loading）→ 结果展示；错误按 code 分支提示（docs/api_doc.md 4.6） */

import { Alert, App, Button, Card, Empty, Space, Spin } from 'antd'
import { CloudUploadOutlined, ExperimentOutlined } from '@ant-design/icons'
import { useState } from 'react'

import { detectImage } from '../../api/detect'
import { ApiError } from '../../api/client'
import { archiveDetection } from '../../cloud/archive'
import { signedUrl } from '../../cloud/chat'
import DetectionViewer from '../../components/DetectionViewer'
import ImageUploader from '../../components/ImageUploader'
import type { DetectResponse } from '../../types/detect'

const DETECT_ERROR_TIPS: Record<number, string> = {
  40001: '图片解码失败，请更换图片后重试',
  40002: '图片大小超过上限（10MB），请压缩后重试',
  40003: '图片格式不支持，仅支持 jpg/jpeg/png/bmp',
  50301: '模型服务未就绪，请稍后重试',
  50000: '服务器内部错误，请稍后重试',
}

const tips = [
  '支持 jpg / jpeg / png / bmp 格式，单张不超过 10MB',
  '单张推理约 200ms 内完成（受硬件与图片复杂度影响）',
  '检出的缺陷类别包括：积灰、鸟粪、电损伤、物理损伤、积雪',
  '检测完成后自动保存历史记录，可在「检测历史」中查看与导出',
  '原图与标注结果图会同步归档到云端存储，仅本人可见',
]

export default function DetectPage() {
  const { message } = App.useApp()
  const [file, setFile] = useState<File | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [result, setResult] = useState<DetectResponse | null>(null)
  const [archiveState, setArchiveState] = useState<'idle' | 'saving' | 'done' | 'failed'>('idle')
  const [cloudLink, setCloudLink] = useState<string | null>(null)

  const handleChangeFile = (next: File | null) => {
    setFile(next)
    setResult(null)
  }

  const handleDetect = async () => {
    if (!file) {
      message.warning('请先选择图片')
      return
    }
    setDetecting(true)
    try {
      const res = await detectImage(file)
      setResult(res)
      message.success(`检测完成，共检出 ${res.targets.length} 个目标`)

      // 云端归档：原图与标注图写入云存储，失败不影响本次检测结果
      setArchiveState('saving')
      setCloudLink(null)
      const snapshot = file
      void archiveDetection(res.record_id, snapshot, res).then(async (archived) => {
        if (archived.failed) {
          setArchiveState('failed')
          return
        }
        setArchiveState('done')
        if (archived.annotatedPath) {
          try {
            setCloudLink(await signedUrl(archived.annotatedPath, 3600))
          } catch {
            setCloudLink(null)
          }
        }
      })
    } catch (err) {
      if (err instanceof ApiError) {
        message.error(DETECT_ERROR_TIPS[err.code] ?? err.message)
      } else {
        message.error('检测失败，请稍后重试')
      }
    } finally {
      setDetecting(false)
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5">
        <h2 className="mb-1 text-lg font-semibold text-gray-800 md:text-2xl">光伏面板缺陷检测</h2>
        <p className="text-sm text-gray-500 md:text-base">
          上传光伏面板现场图片，AI识别积灰、鸟粪、电损伤、物理损伤、积雪等缺陷，输出检测框与运维建议
        </p>
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="flex flex-col gap-5">
          <Card
            title="上传图片"
            className="pv-shadow-card !border-sky-100"
            styles={{ header: { borderBottom: '1px solid #ecfeff' } }}
          >
            <div className="pv-upload-dragger">
              <ImageUploader file={file} disabled={detecting} onChange={handleChangeFile} />
            </div>
            <Button
              type="primary"
              icon={<ExperimentOutlined />}
              block
              className="mt-5 h-11 bg-gradient-to-r from-sky-500 to-sky-600 shadow-md shadow-sky-200"
              disabled={!file}
              loading={detecting}
              onClick={handleDetect}
            >
              {detecting ? '正在检测…' : '开始检测'}
            </Button>
          </Card>
          <Card title="使用说明" size="small" className="pv-shadow-card !border-sky-100">
            <ul className="mb-0 list-disc space-y-1.5 pl-5 text-sm text-gray-600">
              {tips.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="min-h-80">
          {detecting ? (
            <Card className="pv-shadow-card h-full">
              <div className="flex min-h-80 flex-col items-center justify-center gap-3 text-gray-500">
                <Spin size="large" />
                <span>模型推理中，请稍候…</span>
              </div>
            </Card>
          ) : result ? (
            <Space direction="vertical" size={12} className="w-full">
              {archiveState === 'saving' ? (
                <Alert
                  type="info" showIcon icon={<CloudUploadOutlined />}
                  message="正在归档到云端存储…"
                />
              ) : archiveState === 'done' ? (
                <Alert
                  type="success" showIcon icon={<CloudUploadOutlined />}
                  message={
                    <span>
                      已归档到云端
                      {cloudLink ? (
                        <a href={cloudLink} target="_blank" rel="noreferrer" className="ml-2">
                          查看云端标注图
                        </a>
                      ) : null}
                    </span>
                  }
                  description="原图与标注结果图已保存到你的云端空间，换设备登录也可查看（签名链接 1 小时内有效）。"
                />
              ) : archiveState === 'failed' ? (
                <Alert
                  type="warning" showIcon
                  message="云端归档未完成"
                  description="检测结果已保存在服务器；若需跨设备查看，请确认已登录云端账号后重新检测。"
                />
              ) : null}
              <DetectionViewer result={result} />
            </Space>
          ) : (
            <Card className="pv-shadow-card h-full">
              <Empty
                className="flex min-h-80 flex-col items-center justify-center"
                description={
                  <span className="text-gray-400">
                    上传图片并点击「开始检测」后，
                    <br />
                    标注结果、检测框与运维建议将显示在这里
                  </span>
                }
              >
                <span className="mt-1 block text-xs text-gray-300">
                  支持拖拽或点击选择本地图片
                </span>
              </Empty>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}