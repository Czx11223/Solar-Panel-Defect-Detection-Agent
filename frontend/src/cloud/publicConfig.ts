/**
 * 云服务公开配置（WorkBuddy Cloud Service `publicConfig`）。
 *
 * 三个值由 workbuddy_cloud_service 的 activate 结果下发，可安全随前端代码发布：
 * 它们只标识"哪个应用"，不含任何密钥或环境凭据；服务端还会校验请求 Origin
 * 必须与该应用的发布域名一致。重新发布沿用同一应用 ID，域名不变，故可随源码固定。
 *
 * 注意：不要另建客户端、不要从环境变量或 location 推导 endpoint。
 */
export const PUBLIC_CONFIG = {
  endpoint: 'https://pv-defect-agent.app.workbuddy.host',
  oauthRelayBaseUrl: 'https://www.workbuddy.cn/v2/as/genie-baas/oauth',
  publishableKey: 'wbpk_LwXsJCwAADGbvuMaI1RT8A_QRGObApv3hY7dKMV3gDeSDmjg3YW8HLX',
} as const

/** 云端模型选择：优先 Kimi-K3（与原 kimi-k3.1-pro 同族，支持工具调用与视觉），否则回退自动路由。 */
export const PREFERRED_MODELS = ['kimi-k3-1', 'auto'] as const
