/** 历史记录页：分页列表、详情（原图/结果图对比）、CSV导出与日期筛选（docs/api_doc.md 4.7–4.9） */

import { App, Button, Card, DatePicker, Descriptions, Drawer, Space, Spin, Table, Tag } from 'antd'
import { DownloadOutlined, HistoryOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import { useCallback, useEffect, useState } from 'react'

import { exportRecords, fetchRecordDetail, fetchRecords } from '../../api/record'
import { ApiError } from '../../api/client'
import ImageCompare from '../../components/ImageCompare'
import type { RecordDetailResponse, RecordListItem } from '../../types/record'
import { downloadBlob, todayString } from '../../utils/download'

const { RangePicker } = DatePicker

export default function HistoryPage() {
  const { message } = App.useApp()
  const [items, setItems] = useState<RecordListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [exporting, setExporting] = useState(false)
  const [detail, setDetail] = useState<RecordDetailResponse | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchRecords({ page, page_size: pageSize })
      setItems(res.items)
      setTotal(res.total)
    } catch (err) {
      if (err instanceof ApiError) {
        message.error(err.message)
      }
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, message])

  useEffect(() => {
    void load()
  }, [load])

  const openDetail = async (recordId: number) => {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      setDetail(await fetchRecordDetail(recordId))
    } catch (err) {
      if (err instanceof ApiError) {
        message.error(err.message)
      }
    } finally {
      setDetailLoading(false)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const start = range?.[0]?.format('YYYY-MM-DD')
      const end = range?.[1]?.format('YYYY-MM-DD')
      const blob = await exportRecords(start, end)
      downloadBlob(blob, `detect_records_${todayString()}.csv`)
      message.success('导出成功')
    } catch (err) {
      if (err instanceof ApiError) {
        message.error(err.message)
      }
    } finally {
      setExporting(false)
    }
  }

  const columns: ColumnsType<RecordListItem> = [
    { title: '记录ID', dataIndex: 'record_id', key: 'record_id', width: 90 },
    {
      title: '图片名',
      dataIndex: 'image_name',
      key: 'image_name',
      ellipsis: true,
      width: 180,
    },
    {
      title: '缺陷汇总',
      dataIndex: 'defect_summary',
      key: 'defect_summary',
      render: (value: Record<string, number>) => (
        <Space size={4} wrap>
          {Object.entries(value)
            .filter(([, count]) => count > 0)
            .map(([name, count]) => (
              <Tag key={name} color="sky">
                {name} ×{count}
              </Tag>
            ))}
        </Space>
      ),
    },
    {
      title: '推理耗时',
      dataIndex: 'inference_time_ms',
      key: 'inference_time_ms',
      width: 110,
      render: (value: number | null) =>
        value === null ? '-' : <span>{value.toFixed(1)} ms</span>,
    },
    {
      title: '模型版本',
      dataIndex: 'model_version',
      key: 'model_version',
      width: 130,
      ellipsis: true,
    },
    { title: '检测时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => void openDetail(record.record_id)}>
          详情
        </Button>
      ),
    },
  ]

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-50 text-sky-600">
            <HistoryOutlined />
          </span>
          <div>
            <h2 className="mb-0 text-lg font-semibold text-gray-800 md:text-xl">检测历史</h2>
            <p className="mb-0 text-sm text-gray-500">查看历史检测记录，支持按日期范围导出 CSV</p>
          </div>
        </div>
        <Space wrap>
          <RangePicker
            value={range}
            onChange={(dates) => setRange(dates)}
            allowClear
            placeholder={['起始日期', '结束日期']}
          />
          <Button
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={() => void handleExport()}
          >
            导出记录
          </Button>
        </Space>
      </div>
      <Card className="pv-shadow-card !border-sky-100">
        <div className="pv-scroll overflow-x-auto">
          <Table<RecordListItem>
            rowKey="record_id"
            columns={columns}
            dataSource={items}
            loading={loading}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              pageSizeOptions: [10, 20, 50],
              showTotal: (t) => `共 ${t} 条`,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              },
            }}
          />
        </div>
      </Card>
      <Drawer
        title={detail ? `检测记录 #${detail.record_id}` : '检测记录详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width="min(92vw, 960px)"
      >
        {detailLoading ? (
          <div className="flex h-48 items-center justify-center">
            <Spin />
          </div>
        ) : detail ? (
          <div className="flex flex-col gap-4">
            <ImageCompare
              leftLabel="上传原图"
              leftUrl={detail.image_url}
              rightLabel="标注结果图"
              rightUrl={detail.result_image_url}
            />
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="图片名">{detail.image_name}</Descriptions.Item>
              <Descriptions.Item label="检测时间">{detail.created_at}</Descriptions.Item>
              <Descriptions.Item label="图像尺寸">
                {detail.image_size.width} × {detail.image_size.height}
              </Descriptions.Item>
              <Descriptions.Item label="推理耗时">
                {detail.inference_time_ms === null
                  ? '-'
                  : `${detail.inference_time_ms.toFixed(1)} ms`}
              </Descriptions.Item>
              <Descriptions.Item label="模型版本" span={2}>
                {detail.model_version}
              </Descriptions.Item>
            </Descriptions>
            <div>
              <p className="mb-2 text-sm font-medium text-gray-700">
                检测目标（{detail.targets.length} 个）
              </p>
              <div className="pv-scroll overflow-x-auto">
                <Table
                  rowKey={(_, index) => String(index)}
                  size="small"
                  pagination={false}
                  dataSource={detail.targets}
                  columns={[
                    {
                      title: '类别',
                      dataIndex: 'class_name',
                      key: 'class_name',
                      render: (value: string) => <Tag color="sky">{value}</Tag>,
                    },
                    {
                      title: '置信度',
                      dataIndex: 'confidence',
                      key: 'confidence',
                      render: (value: number) => `${(value * 100).toFixed(1)}%`,
                    },
                    {
                      title: '检测框 [x1, y1, x2, y2]',
                      dataIndex: 'bbox',
                      key: 'bbox',
                      render: (value: number[]) => (
                        <code className="text-xs text-gray-600">
                          {value.map((n) => Math.round(n)).join(', ')}
                        </code>
                      ),
                    },
                  ]}
                />
              </div>
            </div>
            <p className="mb-0 text-xs text-gray-400">
              导出数据默认含全部记录；选择日期范围后导出仅含该范围内的记录
            </p>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}