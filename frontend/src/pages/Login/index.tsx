/** 登录页：云服务邮箱验证码登录（默认）+ 旧版账号密码登录（兼容既有账号）。
 *
 *  验证码通道由 WorkBuddy 云服务托管：新邮箱首次验证即自动注册，无需单独注册步骤；
 *  登录成功后把云端 access token 写入本地，后端同时接受云端 token 与应用 JWT。
 */

import { App, Button, Divider, Form, Input, Tabs, Typography } from 'antd'
import {
  LockOutlined, MailOutlined, SafetyCertificateOutlined, UserOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { login } from '../../api/auth'
import { ApiError } from '../../api/client'
import { sendEmailCode, verifyEmailCode } from '../../cloud/auth'
import type { PendingOtp } from '../../cloud/auth'
import { PASSWORD_RE, USERNAME_RE } from '../../constants/validation'
import { useAuth } from '../../hooks/useAuth'
import type { LoginRequest } from '../../types/auth'
import { getToken } from '../../utils/storage'

interface LocationState {
  from?: string
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export default function LoginPage() {
  const [submitting, setSubmitting] = useState(false)
  const [sending, setSending] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [pending, setPending] = useState<PendingOtp | null>(null)
  const { login: saveToken } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = App.useApp()
  const from = (location.state as LocationState | null)?.from ?? '/'

  useEffect(() => {
    if (countdown <= 0) return undefined
    const timer = window.setTimeout(() => setCountdown((n) => n - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [countdown])

  const [otpForm] = Form.useForm<{ email: string; code: string }>()

  const handlePasswordLogin = async (values: LoginRequest) => {
    setSubmitting(true)
    try {
      const res = await login(values)
      saveToken(res.access_token)
      message.success('登录成功')
      navigate(from, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        message.error(err.code === 40102 ? '用户名或密码错误' : err.message)
      } else {
        message.error('登录失败，请稍后重试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const sendCode = async (email: string) => {
    setSending(true)
    try {
      const challenge = await sendEmailCode(email)
      setPending(challenge)
      setCountdown(60)
      message.success('验证码已发送，请查收邮箱')
    } catch (err) {
      message.error((err as Error).message || '验证码发送失败')
    } finally {
      setSending(false)
    }
  }

  const submitOtp = async (email: string, code: string) => {
    if (!pending || pending.email !== email) {
      message.warning('请先获取当前邮箱的验证码')
      return
    }
    setSubmitting(true)
    try {
      await verifyEmailCode(pending, code)
      // verifyEmailCode 内部已用票据兑换并落盘应用 JWT，这里直接同步到组件状态
      const token = getToken()
      if (token) saveToken(token)
      setPending(null)
      message.success('登录成功')
      navigate(from, { replace: true })
    } catch (err) {
      message.error((err as Error).message || '验证码校验失败')
    } finally {
      setSubmitting(false)
    }
  }

  const otpPanel = (
    <Form
      form={otpForm}
      name="otp-login"
      size="large"
      onFinish={(v: { email: string; code: string }) => void submitOtp(v.email, v.code)}
    >
      <Form.Item
        name="email"
        rules={[
          { required: true, message: '请输入邮箱' },
          { pattern: EMAIL_RE, message: '请输入正确的邮箱地址' },
        ]}
      >
        <Input prefix={<MailOutlined />} placeholder="邮箱" autoComplete="email" />
      </Form.Item>
      <Form.Item className="!mb-3">
        <div className="flex gap-2">
          <Form.Item
            name="code"
            noStyle
            rules={[
              { required: true, message: '请输入验证码' },
              { pattern: /^\d{4,8}$/, message: '验证码为 4–8 位数字' },
            ]}
          >
            <Input placeholder="邮箱验证码" autoComplete="one-time-code" />
          </Form.Item>
          <Button
            htmlType="button"
            onClick={() => {
              const email = String(otpForm.getFieldValue('email') ?? '').trim()
              if (!EMAIL_RE.test(email)) {
                message.warning('请先填写正确的邮箱')
                return
              }
              void sendCode(email)
            }}
            loading={sending}
            disabled={countdown > 0}
            className="shrink-0"
          >
            {countdown > 0 ? `${countdown}s` : '获取验证码'}
          </Button>
        </div>
      </Form.Item>
      <Form.Item className="!mb-2">
        <Button
          type="primary"
          htmlType="submit"
          block
          loading={submitting}
          className="h-11 !bg-gradient-to-r !from-sky-500 !to-sky-600 shadow-md shadow-sky-200"
        >
          登录 / 注册
        </Button>
      </Form.Item>
      <p className="text-center text-xs text-gray-400">
        未注册的邮箱验证后自动创建账号，由 WorkBuddy 云服务托管登录态
      </p>
    </Form>
  )

  const passwordForm = (
    <Form<LoginRequest> name="login" size="large" onFinish={handlePasswordLogin}>
      <Form.Item
        name="username"
        rules={[
          { required: true, message: '请输入用户名' },
          { pattern: USERNAME_RE, message: '用户名须为2–30字符（字母/数字/下划线/中文/连字符）' },
        ]}
      >
        <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
      </Form.Item>
      <Form.Item
        name="password"
        rules={[
          { required: true, message: '请输入密码' },
          { pattern: PASSWORD_RE, message: '密码为8–64字符，须含字母与数字' },
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          placeholder="密码"
          autoComplete="current-password"
        />
      </Form.Item>
      <Form.Item className="!mb-2">
        <Button
          type="primary"
          htmlType="submit"
          block
          loading={submitting}
          className="h-11 !bg-gradient-to-r !from-sky-500 !to-sky-600 shadow-md shadow-sky-200"
        >
          登录
        </Button>
      </Form.Item>
    </Form>
  )

  return (
    <div className="pv-auth-bg flex items-center justify-center p-4">
      <div className="pv-auth-card pv-fade-up w-full max-w-md p-6 sm:p-8">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-sky-600 shadow-lg shadow-sky-200">
            <SafetyCertificateOutlined className="text-2xl text-white" />
          </div>
          <Typography.Title level={3} className="!mb-1 !text-sky-600">
            光伏面板缺陷检测系统
          </Typography.Title>
          <Typography.Text type="secondary">登录后即可上传图片进行缺陷检测</Typography.Text>
        </div>

        <Tabs
          defaultActiveKey="otp"
          items={[
            { key: 'otp', label: '邮箱验证码', children: otpPanel },
            { key: 'password', label: '账号密码', children: passwordForm },
          ]}
        />

        <Divider className="!my-4" />
        <div className="text-center text-sm text-gray-500">
          旧账号仍可使用账号密码登录；
          <Link to="/register" className="font-medium text-sky-600 hover:underline">
            注册说明
          </Link>
        </div>
      </div>
    </div>
  )
}
