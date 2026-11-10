import { createWorkBuddyCloud } from '@tencent-ai/workbuddy-cloud-sdk'
const cloud = createWorkBuddyCloud({
  endpoint: 'https://pv-defect-agent.app.workbuddy.host',
  oauthRelayBaseUrl: 'https://www.workbuddy.cn/v2/as/genie-baas/oauth',
  publishableKey: 'wbpk_LwXsJCwAADGbvuMaI1RT8A_QRGObApv3hY7dKMV3gDeSDmjg3YW8HLX',
})
// 1) 无会话时 getAccessToken / getUser 的行为
try {
  const t = await cloud.auth.getAccessToken()
  console.log('ACCESS_TOKEN_EMPTY?', t === undefined || t === null, 'len=', t ? String(t).length : 0)
} catch (e) { console.log('ACCESS_TOKEN_THROW', e?.message) }
const me = await cloud.auth.getUser()
console.log('GETUSER', JSON.stringify(me.error ?? me.data).slice(0, 160))

// 2) 云端认证接口在无浏览器 cookie 下是否可用
const sent = await cloud.auth.sendOtp({ email: `probe-${Date.now()}@example.com` })
console.log('SENDOTP error=', JSON.stringify(sent.error).slice(0, 200))
console.log('SENDOTP data=', JSON.stringify(sent.data).slice(0, 200))
