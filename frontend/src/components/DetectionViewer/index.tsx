/** 检测结果展示：标注图 + 检测框明细表 + 运维建议（docs/api_doc.md 4.6/5.1/5.2） */

import {
  Alert,
  Card,
  Descriptions,
  Progress,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type { AdviceItem, DetectResponse, TargetItem } from '../../types/detect'

const LEVEL_COLORS: Record<AdviceItem['level'], string> = {
  high: 'red',
  mid: 'orange',
  low: 'blue',
}

interface DetectionViewerProps {
  result: DetectResponse
}

const targetColumns: ColumnsType<TargetItem> = [
  {
    title: '类别',
    dataIndex: 'class_name',
    key: 'class_name',
    render: (value: string) => <Tag color="blue">{value}</Tag>,
  },
  {
    title: '置信度',
    dataIndex: 'confidence',
    key: 'confidence',
    width: 160,
    render: (value: number) => (
      <Progress percent={Math.round(value * 100)} size="small" strokeColor="#0284c7" />
    ),
  },
  {
    title: '检测框 [x1, y1, x2, y2]',
    dataIndex: 'bbox',
    key: 'bbox',
    render: (value: number[]) => (
      <code className="whitespace-nowrap text-xs text-gray-600">
        {value.map((n) => Math.round(n)).join(', ')}
      </code>
    ),
  },
]

export default function DetectionViewer({ result }: DetectionViewerProps) {
  return (
    <Card
      className="pv-shadow-card h-full !border-sky-100"
      title="检测结果"
      extra={
        <Space size={16}>
          <span className="text-xs text-gray-500">
            推理耗时 <b className="text-sky-600">{result.inference_time_ms?.toFixed(1) ?? '-'} ms</b>
          </span>
          <span className="text-xs text-gray-500">
            模型 <b className="text-gray-700">{result.model_version}</b>
          </span>
        </Space>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <img
            src={result.rendered_image_base64}
            alt="标注结果图"
            className="pv-img-card w-full border border-gray-200"
          />
          <Descriptions size="small" column={1} className="mt-3">
            <Descriptions.Item label="记录ID">{result.record_id}</Descriptions.Item>
            <Descriptions.Item label="图像尺寸">
              {result.image_size.width} × {result.image_size.height}
            </Descriptions.Item>
          </Descriptions>
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <Typography.Text strong className="mb-2 block">
              检测框明细（{result.targets.length} 个目标）
            </Typography.Text>
            {result.targets.length === 0 ? (
              <Alert type="info" showIcon message="未检出缺陷目标" />
            ) : (
              <div className="overflow-x-auto">
                <Table<TargetItem>
                  rowKey={(_, index) => String(index)}
                  columns={targetColumns}
                  dataSource={result.targets}
                  pagination={false}
                  size="small"
                />
              </div>
            )}
          </div>
          <div>
            <Typography.Text strong className="mb-2 block">
              运维建议
            </Typography.Text>
            <Space direction="vertical" className="w-full" size={8}>
              {result.advice.map((item, index) => (
                <div
                  key={`${item.class_name}-${index}`}
                  className="rounded-xl border border-sky-100 bg-gradient-to-br from-sky-50/70 to-white p-3"
                >
                  <Space size={8} className="mb-1">
                    <Tag color={LEVEL_COLORS[item.level]}>{item.level_name}</Tag>
                    <span className="text-sm font-medium">{item.class_name}</span>
                    {item.count > 0 && (
                      <span className="text-xs text-gray-500">
                        检出 {item.count} 处 · 最高置信度 {Math.round(item.max_confidence * 100)}%
                      </span>
                    )}
                  </Space>
                  <p className="mb-0 text-sm text-gray-700">{item.text}</p>
                </div>
              ))}
            </Space>
          </div>
        </div>
      </div>
    </Card>
  )
}
