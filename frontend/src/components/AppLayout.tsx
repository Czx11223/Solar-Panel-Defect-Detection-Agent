/** 全局布局：顶栏（品牌/导航/用户名与退出）+ 内容区 + 页脚；
 * 移动端导航隐藏文字仅留图标（D37），header 紧凑布局避免极窄屏折行；内容区自适应 */

import {
  App,
  Avatar,
  Dropdown,
  Layout,
  Space,
} from 'antd'
import {
  HistoryOutlined,
  HomeOutlined,
  LogoutOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useNavigate, NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../hooks/useAuth'

const { Header, Content, Footer } = Layout

const navItems = [
  { to: '/', label: '缺陷检测', icon: <HomeOutlined /> },
  { to: '/history', label: '检测历史', icon: <HistoryOutlined /> },
  { to: '/chat', label: '智能问答', icon: <RobotOutlined /> },
]

export default function AppLayout() {
  const { profile, logout } = useAuth()
  const navigate = useNavigate()
  const { message } = App.useApp()

  const handleLogout = () => {
    logout()
    message.success('已退出登录')
    navigate('/login', { replace: true })
  }

  return (
    <Layout className="min-h-screen">
      <Header className="flex min-h-14 !h-auto items-center justify-between gap-2 border-b border-sky-100 bg-white/90 !px-3 !py-2 shadow-sm backdrop-blur md:!px-8">
        <div className="flex min-w-0 items-center gap-3 md:gap-6">
          <div className="flex flex-shrink-0 items-center gap-2 whitespace-nowrap text-sm font-semibold text-sky-600 md:text-lg">
            <span className="pv-brand-dot" aria-hidden="true" />
            <span className="hidden sm:inline">光伏缺陷检测</span>
            <span className="sm:hidden">光伏检测</span>
          </div>
          <nav className="flex items-center gap-0.5 md:gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex flex-shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-sm transition-colors md:px-3 ${
                    isActive
                      ? 'bg-sky-50 font-medium text-sky-600'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`
                }
              >
                {item.icon}
                <span className="hidden sm:inline">{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
        <Dropdown
          menu={{
            items: [
              {
                key: 'logout',
                icon: <LogoutOutlined />,
                label: '退出登录',
                onClick: handleLogout,
              },
            ],
          }}
        >
          <button
            type="button"
            className="flex flex-shrink-0 items-center gap-2 rounded-md px-2 py-1 transition-colors hover:bg-gray-50"
          >
            <Avatar size="small" icon={<UserOutlined />} className="bg-gradient-to-br from-sky-400 to-sky-600" />
            <span className="max-w-[6rem] truncate text-sm text-gray-700 md:max-w-[8rem]">
              {profile?.nickname || profile?.username || '未登录'}
            </span>
          </button>
        </Dropdown>
      </Header>
      <Content className="flex-1 bg-gradient-to-b from-sky-50/60 to-gray-50 p-4 md:p-8">
        <div className="pv-fade-up">
          <Outlet />
        </div>
      </Content>
      <Footer className="border-t border-gray-100 text-center text-xs text-gray-400">
        <Space size={4}>光伏面板缺陷检测系统 · AI辅助判断仅供参考，重大缺陷须人工复核</Space>
      </Footer>
    </Layout>
  )
}