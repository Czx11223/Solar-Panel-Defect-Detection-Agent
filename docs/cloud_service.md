# 云服务接入说明（WorkBuddy Cloud Service）

本文记录光伏面板缺陷检测 Agent 的云服务接入方式：登录、数据、存储、大模型四个模块各自承担什么，
以及为什么这样划分。发布与域名相关内容见 [云托管说明](cloud_deploy.md)。

## 1. 应用与配置

| 项 | 值 |
| --- | --- |
| 应用名 | 光伏面板缺陷检测 Agent |
| applicationId | `wbapp_LwXsJCwAADGbvuMaI1RT8A` |
| 发布域名 | `https://pv-defect-agent.app.workbuddy.host` |
| 云服务状态 | 已开通，`billingStatus=normal`、`lifecycleState=active` |

前端公开配置固定写在 `frontend/src/cloud/publicConfig.ts`：

```ts
export const PUBLIC_CONFIG = {
  endpoint: 'https://pv-defect-agent.app.workbuddy.host',
  oauthRelayBaseUrl: 'https://www.workbuddy.cn/v2/as/genie-baas/oauth',
  publishableKey: 'wbpk_LwXsJCwAADGbvuMaI1RT8A_QRGObApv3hY7dKMV3gDeSDmjg3YW8HLX',
} as const
```

这三个值只标识"哪个应用"，不含密钥，可随前端代码一起发布；服务端还会校验请求 `Origin` 必须与该应用
的发布域名一致。**不要另建客户端，也不要从环境变量或 `location` 推导 endpoint**——重新发布沿用同一
applicationId，域名不变，因此可以写死在源码里。

## 2. 四个模块的职责划分

### 2.1 认证（Cloud Auth）：邮箱验证码取代自建注册

- 登录页保留两个页签：「账号密码」走应用自有 JWT（老账号不受影响），「邮箱验证码」走云端 OTP。
- 首次用某个邮箱登录时，云端自动建号，前端把 `cloud.auth.getAccessToken()` 的结果写入本地
  `pv_token`（沿用原有存储键），既有 axios 拦截器无需改动。
- 后端 `app/api/deps.py` 的 `get_current_user` 是**三通道**的，按代价从低到高依次尝试：
  1. 应用 JWT 本地验签（零网络开销，`token_version` 撤销机制不变）；
  2. 云端票据 `X-PV-Ticket`：云端数据库签发、云端复核，后端零密钥（推荐路径，见下）；
  3. 云端 access token 直连自省（兜底，兼容没有票据的旧会话）。
  三条通道最终都落到 `user_repo.get_or_create_by_cloud()`，按 `username = wb_<uid>` 建档。
- **发布网关会改写 `Authorization`**（实测：客户端发的 19 字符令牌到达后端变成 379 字符的网关凭据，
  claims 只有 `exp/iat/iss`），因此前端在 `Authorization` 之外再用自定义头 `X-PV-Token` 送一份令牌，
  后端 `deps.py` 优先读自定义头、其次才读标准 Bearer。缺这条通道时，任何登录方式（云端 OTP 与账号密码）
  在线上都会表现为"登录后被踢出"。

#### 为什么改成云端票据

官方约定是"应用后端通过自己的 Auth 数据面校验令牌，不要手写 `/auth/**`"，同时不得复制云端签名密钥。
实测发现：**把用户令牌交给后端，无论请求 `/auth/v1/user/me` 还是数据面 RPC，云端一律返回**

```
401 invalid_grant: the session is invalid, expired or issued for another client
```

即使同一个令牌在浏览器里刚刚建立会话、`getUser()` 也正常。也就是说这个令牌"只认签发它的那个客户端"，
后端无法拿它做身份自省。于是改为"云端签发、云端复核、后端零密钥"的票据方案：

| 对象 | 位置 | 说明 |
| --- | --- | --- |
| `issue_ticket()` | 云库 RPC（仅 `authenticated`） | 以 `auth.uid()` 为身份、用库内密钥签名，返回 `{uid, exp, sig, email, name}`，有效期 15 分钟 |
| `verify_ticket(p_uid, p_exp, p_email, p_sig)` | 云库 RPC（`anon` 可执行） | 用同一密钥重算 SHA-256 签名并比对，通过则返回 `{uid}` |
| `auth_secret` | 云库表 | 存签名密钥；开启 RLS 且不建任何策略，只有 `SECURITY DEFINER` 函数可读 |
| `X-PV-Ticket` | 请求头 | 前端把票据 JSON 做 base64url（无填充）后随每个请求发送 |

后端只做两件事：解 base64 → 调 `verify_ticket` 复核 → 用返回的 `uid` 建号。**后端不持有任何云端密钥**，
也不会再把用户令牌发往云端 auth 端点。

安全性：

- `uid` 来自云端 `auth.uid()`，前端无法指定要冒充谁；
- 签名覆盖 `uid / exp / email`，改任一字段都会被云端拒绝（实测改 `uid`、改 `sig` 均返回 401）；
- 票据 15 分钟过期，后端本地先判 `exp`，过期票据连云端都不请求；
- 校验结果按 `uid+exp+sig` 缓存 `PV_CLOUD_AUTH_TTL` 秒，避免每个请求都打云端；
- 令牌与票据只放请求头，绝不进 URL（官方规范要求）。

排查工具：设置 `PV_DIAG=1` 会挂载 `GET /api/diag/auth`（回显令牌来源/长度/指纹/声明名）
与 `GET /api/diag/selftest`（服务端自签应用 JWT 走真实 HTTP 回环，验证自定义头通道）。
上线默认关闭。
- 注册页已改为说明页：不再收集用户名密码，账号由 OTP 自动创建。`PV_ALLOW_REGISTER` 仍只控制旧的
  账号密码注册接口，生产默认关闭。

### 2.2 数据库（Cloud Database）：会话与消息搬到云端

新建三张表，全部开启 RLS，属主字段 `owner_id` 默认取 `auth.uid()`，前端**绝不发送** `owner_id`：

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| `agent_session` | 会话 | `id`、`title`、`message_count`、`updated_at` |
| `agent_message` | 消息（含思维链与工具调用） | `session_id`、`role`、`content`、`reasoning`、`tool_calls`(JSONB)、`tool_call_id`、`tokens_in/out` |
| `detect_asset` | 检测图像资产索引 | `record_id`、`kind`(original/annotated)、`storage_path`、`size_bytes` |

每张表 4 条策略（SELECT / INSERT / UPDATE / DELETE，均以 `owner_id = auth.uid()` 为条件），已核验共
12 条策略全部生效；并建了 `(owner_id, session_id, id)`、`(owner_id, updated_at DESC)`、
`(owner_id, record_id)` 三个索引。

前端访问入口集中在 `frontend/src/cloud/chat.ts`（会话与消息的增删查）与 `cloud/archive.ts`（检测资产登记）。

### 2.3 存储（Cloud Storage）：原图与标注图归档

- 路径统一 `cloud.storage.userPath(uid, relativePath)`，实际落点 `users/<uid>/records/<record_id>/original.*`
  与 `.../annotated.jpg`，天然按用户隔离。
- 谁上传谁负责鉴权：**归档在前端做**，因为只有浏览器持有云端会话，服务端不代理云端存储请求。
  归档失败不影响本次检测结果，页面只降级提示"未归档"。
- 历史回看用 `createSignedUrl(path, ttl)` 生成有时效的下载地址（默认 10 分钟，检测页用 1 小时），
  不暴露长期可访问的裸链接。

### 2.4 大模型（Cloud LLM）：keyless 调用，工具仍在服务端

这是本次改动最大的一处：**Agent 循环从前端发起**。

```
浏览器 ──(云端服务自动注入身份)──> Cloud LLM  kimi-k3-1 / auto（流式 + tool_calls）
   │                                        ▲
   │ tool_calls                             │ 回灌 tool 消息
   ▼                                        │
GET  /api/agent/tools       ← 工具 JSON Schema（只在服务端维护一份）
POST /api/agent/tools/{name} → 本地 SQLite：检测记录查询、统计、知识库检索、检测图读取
```

- 模型选择 `PREFERRED_MODELS = ['kimi-k3-1', 'auto']`，挑第一个 `supportsToolCall !== false` 且未禁用的。
- 事件协议与旧的服务端 SSE 完全一致（`meta/reasoning/delta/tool_call/tool_result/done/error`），
  页面渲染逻辑无需改动，`src/api/agent.ts` 只是把实现换成 `runAgent()`。
- 多轮工具循环必须把 `reasoning_content` 与 `tool_calls` 原样回传，否则上下文断裂；这部分由
  `src/agent/loop.ts` 的 `buildMessages` / `streamRound` 处理，最多 6 轮，超限后去掉 tools 收尾。
- 视觉工具 `interpret_image` 改为浏览器直接把结果图转 data URL 交给云端多模态（Kimi 原生视觉），
  失败才回落到服务端实现（服务端配了百炼 Key 时可用）。

带来的收益：服务端不再需要 `DASHSCOPE_API_KEY` 就能提供对话能力；密钥不出现在任何前端产物里
（已核验构建产物中无 `dashscope` 字样）。

代价：Agent 页依赖云端（登录态 + 云端模型），**本地 `localhost` 调试对话会被 Origin 校验拦下**，
调试对话请访问发布域名；本地其余功能（检测、记录、导出、登录老账号）不受影响。

## 3. 后端新增接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/agent/tools` | 返回全部工具的 OpenAI function calling 声明 |
| POST | `/api/agent/tools/{name}` | 执行单个工具，body `{"arguments": {...}}`，返回 `{ok, data, error}` |

两者都需要登录态；未知工具名或工具内部异常统一转成 `ok=false` 回灌模型，不抛 500。

## 4. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PV_CLOUD_ENDPOINT` | 空 | 云服务端点；留空则只用应用 JWT，不启用云端令牌校验 |
| `PV_CLOUD_APP_KEY` | 空 | 应用公开凭据（publicConfig.publishableKey）；数据面与 auth 请求必需 |
| `PV_CLOUD_AUTH` | `true` | 是否启用云端身份校验（票据与令牌自省） |
| `PV_CLOUD_AUTH_TTL` | 300 | 票据/自省结果缓存秒数 |
| `PV_CLOUD_AUTH_TIMEOUT` | 6.0 | 云端校验请求超时秒数 |

票据方案不需要任何新环境变量：签名密钥只存在于云库 `auth_secret` 表，后端不持有。

生产（`D:\peixunwenjian\pv_deploy\.env`）已写入：

```
PV_CLOUD_ENDPOINT=https://pv-defect-agent.app.workbuddy.host
PV_CLOUD_APP_KEY=wbpk_LwXsJCwAADGbvuMaI1RT8A_QRGObApv3hY7dKMV3gDeSDmjg3YW8HLX
PV_CLOUD_AUTH=true
```

## 5. 验证记录

| 检查项 | 方式 | 结果 |
| --- | --- | --- |
| 云端模型可调用 | Node 直连 SDK，流式请求 | 返回 `tool_calls`，`finish_reason=tool_calls` |
| 多轮工具回灌 | 回传 `reasoning_content` + `tool_calls` + tool 消息 | 模型继续生成最终回答，链路闭合 |
| 网关是否改写 Authorization | 发标记令牌打 `/api/diag/auth`，比对指纹 | 发出 19 字符；到达后端 379 字符、claims 仅 `exp/iat/iss` → 确认被网关替换 |
| 自定义头是否保留 | 线上发 1000 字符 `X-PV-Token` | 后端读到 `来源=x-pv-token 长度=1000`，原样送达 |
| 应用令牌全链路 | `GET /api/diag/selftest`：服务端自签 JWT 走真实 HTTP 回环 | `{"ok":true,"status":200,"code":0}` |
| 用户令牌后端自省 | 用真实/占位令牌请求 `/auth/v1/user/me` 与 `rpc/whoami` | 一律 `invalid_grant: ... issued for another client` → 该令牌不认后端客户端 |
| 票据签发（匿名） | `rpc/issue_ticket` 不带会话 | `403 unauthenticated` |
| 票据签名校验 | 伪造 `sig` / 过期 `exp` | `403 invalid ticket signature` / `403 ticket expired` |
| 票据端到端 | 云端密钥构造合法票据 → 线上 `/api/agent/tools` | `200` 返回工具清单；改 `uid` 或改 `sig` 均 `401` |
| 工具端点鉴权 | 未带任何凭据 | `40101 缺少认证令牌` |
| 后端回归 | `pytest tests_light` | **43 passed**（新增票据解析 5 例、票据通道 2 例） |
| 前端类型与规范 | `tsc --noEmit`、`npm run build`、`npm run lint` | 全部通过 |
| 云数据库 RLS | 云端查表与策略 | 3 张业务表 RLS 开启、12 条策略生效；`auth_secret` 无任何策略 |
| 线上产物 | 发布后拉取首页 | 资源哈希与本地构建一致 |

## 6. 后续维护

- **换应用或换域名**：改 `publicConfig.ts` 三个值 + `.env` 的 `PV_CLOUD_ENDPOINT`，重新构建发布。
  数据库表和 RLS 无需重建。
- **加表**：用 cloud service 的 migrate 建表，务必 `ENABLE ROW LEVEL SECURITY`、`GRANT` 给
  `authenticated, anon`、再补四条 `owner_id = auth.uid()` 策略，否则前端读写会静默返回空。
- **清理测试数据**：`agent_session` / `agent_message` 按 `owner_id` 删除即可，`detect_asset` 里残留的
  `storage_path` 需配合对象存储一起删。
