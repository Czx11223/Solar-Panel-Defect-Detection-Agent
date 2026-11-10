# 前端Web界面规格说明书（Frontend Web Spec）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 阶段 | 阶段5：前端Web界面开发 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 文档状态 | 已确认（2026-09-15，D31–D38按建议默认值执行） |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》任务7；docs/spec.md 第4章接口设计；docs/api_doc.md；docs/project_structure.md；docs/tasks.md 阶段5 |

## 1 阶段目标与交付物

基于 **React + TypeScript + TailwindCSS + Ant Design** 实现响应式Web前端（适配PC与移动端浏览器），包含登录注册页、检测首页、历史记录页三个页面，对接阶段4 FastAPI后端全部业务接口。本阶段交付前端代码与构建配置，不含部署上线（阶段6）。

| # | 交付物 | 类型 | 说明 |
|---|---|---|---|
| 1 | frontend/package.json | 依赖清单 | React 18 / Vite / TS / antd 5 / Tailwind 3 等锁定版本 |
| 2 | frontend/ 完整代码 | 前端代码 | pages、components、api层、路由与鉴权守卫、类型定义 |
| 3 | docs/frontend_web_spec.md | 规格说明 | 本文档 |

## 2 运行环境与依赖

| 项 | 内容 |
|---|---|
| 运行时 | Node.js 18+（构建期），浏览器Chrome/Firefox/Safari/Edge最新两版本 |
| 框架 | React 18（函数组件 + Hooks） |
| 构建 | Vite 5 + TypeScript 5（严格模式，禁 any 滥用） |
| UI | Ant Design 5（交互组件）+ TailwindCSS 3（布局与自定义样式，D31分工） |
| 路由 | react-router-dom 6 |
| HTTP | axios（拦截器统一token注入、解包、错误处理） |
| 代码规范 | ESLint + @typescript-eslint（no-explicit-any 为 error） |

后端对接契约以 [docs/api_doc.md](api_doc.md) 为准：统一前缀 `/api`，响应结构 `{code, message, data}`，JWT 放 `Authorization: Bearer <token>`。

## 3 前端目录结构

基于 project_structure.md 前端规划，TypeScript化（`App.jsx`→`App.tsx`、`main.jsx`→`main.tsx`），新增 `api/`、`types/`、`hooks/`：

```text
frontend/
├── public/                          # 静态资源（favicon等）
├── src/
│   ├── main.tsx                     # 入口：挂载App、antd中文locale、全局样式
│   ├── App.tsx                      # 路由表 + 鉴权路由守卫
│   ├── api/                         # axios实例、拦截器、接口函数
│   │   ├── client.ts                # axios实例：baseURL、token注入、401处理、统一解包
│   │   ├── auth.ts                  # 注册/登录/个人信息
│   │   ├── detect.ts                # 上传检测
│   │   └── record.ts                # 历史列表/详情/导出/图像blob获取
│   ├── types/                       # 与后端schema对齐的TS类型
│   │   ├── auth.ts                  # LoginRequest/RegisterRequest/TokenResponse等
│   │   ├── detect.ts                # DetectResponse/TargetItem/AdviceItem
│   │   └── record.ts                # RecordListResponse/RecordDetailResponse
│   ├── components/
│   │   ├── ImageUploader/           # 拖拽+点击上传、格式/大小校验、预览
│   │   ├── DetectionViewer/         # 标注图展示 + targets表格 + advice列表
│   │   ├── ProtectedRoute.tsx       # 鉴权路由守卫
│   │   ├── AppLayout.tsx            # 顶栏（品牌/用户名/退出）+ 内容区
│   │   └── ImageCompare/            # 原图/结果图对比（历史详情）
│   ├── pages/
│   │   ├── Login/                   # 登录页
│   │   ├── Register/                # 注册页
│   │   ├── Detect/                  # 检测首页（上传+结果展示）
│   │   └── History/                 # 历史记录页（列表+详情+导出）
│   ├── hooks/                       # useAuth（token读写/用户信息）、useDetect等
│   ├── utils/
│   │   ├── storage.ts               # localStorage封装（token存取）
│   │   ├── download.ts              # blob下载（带鉴权的CSV/图片导出）
│   │   └── image.ts                 # 图片blob→objectURL、释放
│   └── index.css                    # Tailwind指令 + 全局样式
├── index.html
├── vite.config.ts                   # 开发代理 /api → 后端、构建目标
├── tsconfig.json                    # 严格模式
├── tailwind.config.ts
├── postcss.config.js
├── package.json
└── .gitignore
```

## 4 页面功能与接口对接

### 4.1 页面清单与接口映射

| 页面 | 核心功能 | 对接接口 |
|---|---|---|
| 登录页 | 表单校验、登录、token本地存储、错误提示 | POST /api/auth/login |
| 注册页 | 表单校验、注册成功引导登录 | POST /api/auth/register |
| 检测首页 | 拖拽/点击上传、格式校验、预览、检测调用（loading）、标注图与检测框展示、运维建议 | POST /api/detect/image |
| 历史记录页 | 分页列表、详情（原图/结果图对比）、导出CSV | GET /api/record/list、GET /api/record/{id}、GET /api/record/export、GET /api/files/{uploads\|results}/{filename} |
| 全局（Header） | 展示当前用户名、退出登录 | GET /api/user/profile |

统一错误码映射（与 api_doc.md 2.4 一致）：40001参数校验、40002超限、40003格式不支持、40101未认证（清token跳登录）、40102账号密码错误、40301无权限、40401不存在、40901/40902重名冲突、50301模型未就绪、50000服务器错误。前端按 code 给出中文提示并聚焦到对应表单字段（如注册页用户名已存在聚焦 username）。

### 4.2 登录注册页

- 登录表单：用户名、密码；注册表单：用户名、密码、确认密码、邮箱（选填）、昵称（选填）。
- 校验规则与后端一致：用户名2–30字符（字母/数字/下划线/中文/连字符）、密码8–64字符且须含字母与数字；确认密码一致性前端校验；邮箱格式校验。
- 登录成功：token 写入 localStorage（D35，key `pv_token`）→ 跳转检测首页；注册成功：提示后跳转登录页（不自动登录，减少歧义）。
- 错误展示：40102在表单顶部提示"用户名或密码错误"；40901/40902定位到字段提示"用户名已存在/邮箱已被使用"；网络异常（axios无响应/超时）提示"网络连接失败，请检查后端服务"。
- 响应式：移动端单列卡片、PC端居中双栏（表单+品牌区）。

### 4.3 检测首页

上传区（ImageUploader）：

1. 拖拽上传 + 点击选择（antd Upload.Dragger 改造）；
2. 前端即时校验：扩展名 jpg/jpeg/png/bmp、大小 ≤10MB（与后端 D2 一致），超限/格式不符即时提示且不发请求；
3. 图片预览（缩略图 + 原尺寸信息：宽高、大小、格式）；
4. 校验通过后调用 `POST /api/detect/image`（multipart，字段名 `file`）。

检测调用与结果展示：

- 请求期间进入 loading：按钮禁用 + Spin 覆盖，禁止重复提交；
- 成功响应后展示三块：
  - 标注结果图（`rendered_image_base64` data URL 直接渲染）；
  - 检测框明细表（antd Table）：类别名称、置信度（Progress条）、检测框坐标 `[x1,y1,x2,y2]`、缺陷汇总徽标；
  - 运维建议（AdviceItem 列表）：按级别（高/中/低）着色标签 + 建议文本；无缺陷时显示"面板状态正常，无需维护"。
- 附信息：模型版本、推理耗时（`inference_time_ms`，提示"推理耗时 XX ms"）、记录ID。
- 错误处理：40002/40003在上传区提示；40001提示"图片解码失败"；50301提示"模型服务未就绪，请稍后重试"；50000/网络异常统一错误提示并保留已上传预览，便于重试。

### 4.4 历史记录页

- 列表：分页表格（antd Table + Pagination），列：记录ID、文件名、缺陷汇总（Badge计数）、推理耗时、模型版本、检测时间、操作（查看详情）；时间倒序由后端保证。
- 详情：抽屉（Drawer）展示原图与结果图对比（ImageCompare，左右/上下切换），targets 明细、advice、图像尺寸、模型版本、推理耗时。
- 图像访问鉴权：`/api/files/*` 需要 Authorization 头，`<img src>` 无法携带 → 用 axios 以 `responseType: 'blob'` 拉取后 `URL.createObjectURL` 渲染，组件卸载时 `revokeObjectURL` 释放（避免内存泄漏，10MB上限原图尤需注意）。
- 导出：`GET /api/record/export` 同样需鉴权 → axios blob 获取 → 创建 `<a download>` 触发下载（utils/download.ts）；提供日期范围筛选（start/end，YYYY-MM-DD），默认导出全部。
- 属主隔离说明：后端已做属主校验，前端仅需保证携带有效 token。

### 4.5 鉴权路由与全局布局

- AppLayout：顶部导航（品牌名、当前页高亮、用户名下拉[个人信息只读展示/退出]），内容区自适应；移动端导航收起到 Drawer。
- 路由表：`/login`、`/register` 为公开路由；`/`（检测首页）、`/history` 为受保护路由，未登录访问跳转 `/login`（携带 `redirect` 参数，登录后回跳）。
- 全局401拦截：任一接口返回40101 → 清空 token → 跳转登录页 + 提示"登录已过期，请重新登录"。
- 登录态校验：路由守卫读 localStorage token（无 token 视为未登录）；Header 用户名通过 `GET /api/user/profile` 拉取，失败不阻塞页面。

## 5 关键设计

### 5.1 API 封装层（client.ts）

- axios 实例：`baseURL = import.meta.env.VITE_API_BASE ?? '/api'`，开发环境经 Vite 代理（vite.config.ts 代理 `/api` → `http://127.0.0.1:8000`），生产由反向代理或同域部署；
- 请求拦截：从 storage 取 token，存在则注入 `Authorization: Bearer <token>`；
- 响应拦截：统一解包 `{code, message, data}`；`code !== 0` 时构造带 `code/message` 的业务错误对象 reject（供页面按 code 分支）；HTTP 401 触发登出回调；
- 网络层异常（超时、连接失败）归一为"网络连接失败"文案。

### 5.2 类型安全约束

- 所有后端响应定义在 `src/types/`，与 api_doc.md 数据模型一一对应；
- `tsconfig` 开启 `strict: true`，`noImplicitAny`；
- ESLint 规则 `@typescript-eslint/no-explicit-any: error`；事件对象、表单泛型、axios 响应均使用显式类型，不落 any。

### 5.3 响应式与兼容性

- Tailwind 移动优先断点：`<768px` 单列（上传区/结果区纵向堆叠），`≥768px` 双栏（左上传右结果）；表格在移动端横向滚动容器内；
- 构建目标 `es2020` + 原生 ES 模块，Vite 产物自动降级语法；antd 5 按需样式；
- 浏览器兼容自查项：Chrome/Firefox/Safari/Edge 最新两版本（`URL.createObjectURL`、`FileReader`、`crypto.randomUUID` 均为现代浏览器支持）。

### 5.4 图片内存与性能

- 上传预览用 `URL.createObjectURL(file)`（不读 base64），卸载时释放；
- 检测返回的标注图 base64 直接渲染，不做二次转码；
- 历史详情图片用 blob + objectURL，关闭详情时统一 revoke，控制内存峰值。

## 6 决策点（D31–D38，待确认）

以下决策点不改变任务书功能范围与技术栈，仅确定实现参数。延续项目惯例（D1–D30），未获明确意见时按建议默认值执行。

| 编号 | 决策点 | 说明 | 建议默认值 |
|---|---|---|---|
| D31 | antd与Tailwind分工 | 两套样式体系职责边界，避免冲突 | antd 5 负责交互组件（表单/表格/消息/Drawer），Tailwind 负责布局、间距与自定义视觉；二者不混用于同一元素 |
| D32 | 构建工具版本 | Vite 大版本 | Vite 5（Node 18+，生态稳定） |
| D33 | 状态管理方案 | 是否引入全局状态库 | 不引入（Redux/Zustand等）；登录态用 localStorage + hooks（useAuth），页面数据用局部 state，规模小无需全局store |
| D34 | 路由模式 | Hash vs Browser | HashRouter（部署子路径下刷新不404，阶段6再评估BrowserRouter+服务端回退） |
| D35 | token存储 | 任务书要求"JWT token本地存储" | localStorage（key: `pv_token`）；不入cookie（避免CSRF面） |
| D36 | 上传校验边界 | 前端校验深度 | 格式+大小与后端完全一致（jpg/png/jpeg/bmp、≤10MB），超限即时拦截不发请求；魔数等深度校验仅后端做 |
| D37 | 响应式断点 | 断点划分 | Tailwind默认断点，以 md(768px) 为主切换阈值；表格横向滚动兜底 |
| D38 | 个人信息功能范围 | 后端有profile接口，任务书页面清单未含个人信息页 | 仅 Header 展示用户名+退出；不实现资料编辑/改密页面（后端接口保留供后续扩展） |

## 7 任务清单（2026-09-15 全部完成）

- [x] T1 frontend 工程骨架：package.json、vite.config.ts、tsconfig、tailwind/postcss配置、index.html、目录结构
- [x] T2 API层与类型：client.ts（拦截器）、auth/detect/record 接口函数、src/types/ 全部类型定义
- [x] T3 全局基础设施：main.tsx、App.tsx 路由表、ProtectedRoute 守卫、AppLayout、useAuth
- [x] T4 登录/注册页：表单校验、token存储、错误分支提示、响应式布局
- [x] T5 检测页上传区：ImageUploader（拖拽/点击/校验/预览/loading）
- [x] T6 检测结果展示：DetectionViewer（标注图/targets表格/advice列表/指标信息）
- [x] T7 历史记录页：分页列表、详情Drawer（ImageCompare图片对比）、CSV导出、日期筛选
- [x] T8 错误处理与兼容自查：网络异常/401/业务错误统一提示、移动端断点走查、构建目标
- [x] T9 构建验证：`tsc --noEmit` + `vite build` 通过；无 any 类型违规
- [x] T10 文档同步：tasks.md 阶段5勾选、project_structure.md 更新

## 8 风险与规避

| 风险 | 影响 | 规避 |
|---|---|---|
| 标注图 base64 体积大（10MB原图 → 高质量JPEG） | 前端内存与渲染开销 | 后端JPEG质量90已控体积；前端直接渲染不二次转码；图片blob统一revoke |
| `/api/files/*` 与导出需鉴权，`<img>`/`window.open` 无法携带Header | 历史页图片/导出可能401 | axios blob + objectURL 方案（5.4、4.4），统一封装在 api/record.ts |
| 移动端表格拥挤 | 可读性下降 | 横向滚动容器 + 关键列移动端隐藏（Tailwind `hidden md:table-cell`） |
| 前端校验与后端不一致 | 用户迷惑/无效请求 | 校验规则常量与后端对齐（2–30用户名、8–64密码、10MB、4种格式）并注释来源（D2/D26） |

## 9 交付验收口径

- [x] `npm run build`（= `tsc --noEmit && vite build`）零错误（chunk体积警告已通过分包+阈值调整处理）
- [x] 三个页面在 PC 与移动端（375/414）断点下可完整操作（浏览器实测：登录/注册/鉴权守卫/检测页/历史页全流程通过）
- [x] 全链路（注册→登录→上传→检测→历史→导出）对接本机 FastAPI 后端联调通过（浏览器E2E冒烟，8项全部通过；检测接口待真实模型部署后复核）
- [x] 未登录访问受保护路由重定向登录；token 失效后任一请求触发登出回跳（拦截器40101分支）

## 10 文档同步（T10已完成）

- [x] docs/tasks.md：阶段5任务勾选；
- [x] docs/project_structure.md：frontend/ 目录结构按本文档第3章更新。
