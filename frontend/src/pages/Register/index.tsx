/** 注册说明页：账号由云服务邮箱验证码自动创建，不再单独收集用户名密码。 */

import { Button, Result, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'

export default function RegisterPage() {
  const navigate = useNavigate()

  return (
    <div className="pv-auth-bg flex items-center justify-center p-4">
      <div className="pv-auth-card pv-fade-up w-full max-w-md p-6 sm:p-8">
        <Result
          status="info"
          title="无需单独注册"
          subTitle="在登录页选择「邮箱验证码」，输入邮箱并完成验证即自动创建账号，"
          extra={[
            <Button type="primary" key="go" onClick={() => navigate('/login', { replace: true })}>
              去登录
            </Button>,
          ]}
        />
        <Typography.Paragraph type="secondary" className="!mb-0 text-center text-xs">
          账号与登录态由 WorkBuddy 云服务托管；旧的用户名密码账号仍可在「账号密码」页签登录。
        </Typography.Paragraph>
      </div>
    </div>
  )
}
