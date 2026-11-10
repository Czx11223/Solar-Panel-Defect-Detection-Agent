# 光伏面板缺陷检测系统 · 后端API接口文档（OpenAPI）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 适用服务 | backend（FastAPI + YOLOv8 + SQLite） |
| 配套文档 | 服务运行时交互式文档：`http://<host>:8000/docs`（Swagger UI）、`/openapi.json`（OpenAPI Schema） |

## 1 文档说明

本文档为前端开发与联调提供完整的后端接口契约。接口遵循 RESTful 规范，统一前缀 `/api`，响应体统一为 `{code, message, data}` 结构；除注册、登录外，所有接口均需携带 JWT 令牌（`Authorization: Bearer <token>`）。

**模型局限性声明（须展示给终端用户）**：检测结果为 AI 辅助判断，置信度不等于缺陷确诊，置信度低于 0.25 的目标不输出；运维建议供参考，重大缺陷须人工复核。

**数据隐私声明**：用户上传的图像与检测数据仅用于本系统检测服务，不外传、不用于其他用途；图像存储于本地 `storage/` 目录，删除检测记录即同步删除图像文件。

## 2 通用约定

### 2.1 Base URL 与服务信息

| 项 | 值 |
|---|---|
| Base URL | `http://<host>:8000`（开发默认端口 8000，可配） |
| 服务名 | 光伏面板缺陷检测系统 |
| 版本 | 1.0.0 |
| 健康检查 | `GET /`（不要求登录，返回服务与模型状态，不套用统一响应结构） |

### 2.2 鉴权方式

- 登录成功返回 JWT（HS256），有效期为 `PV_TOKEN_EXPIRE_MINUTES`（默认 1440 分钟 / 24 小时）。
- 受保护接口须在请求头携带：`Authorization: Bearer <access_token>`。
- 令牌缺失、无效或过期时返回 `40101`。

### 2.3 统一响应结构

所有 `/api/*` 接口的成功响应统一包装为：

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

- `code`：业务错误码，`0` 表示成功；
- `message`：人类可读信息；
- `data`：业务数据（成功时存在；失败时为 `null`）。

失败响应（HTTP 4xx/5xx）：

```json
{
  "code": 40002,
  "message": "文件大小超过上限 10MB",
  "data": null
}
```

### 2.4 错误码表

| code | HTTP | 含义 | 典型场景 |
|---|---|---|---|
| 0 | 200 | 成功 | — |
| 40001 | 400 | 参数校验失败 | 字段缺失/格式错误、邮箱非法、图像解码失败 |
| 40002 | 400 | 文件大小超限 | 超过 10MB |
| 40003 | 400 | 文件格式不支持 | 非 jpg/jpeg/png/bmp，或扩展名与文件内容（魔数）不符 |
| 40101 | 401 | 未认证 | token 缺失/无效/过期，或修改密码后旧令牌失效 |
| 42901 | 429 | 请求过于频繁 | 登录/注册触发限流，请稍后重试 |
| 40102 | 401 | 用户名或密码错误 | 登录失败、修改密码时原密码错误 |
| 40301 | 403 | 无权限 | 访问他人检测记录/图像 |
| 40401 | 404 | 资源不存在 | 记录或图像不存在 |
| 40901 | 409 | 用户名已存在 | 注册冲突 |
| 40902 | 409 | 邮箱已存在 | 注册或修改邮箱冲突 |
| 50301 | 503 | 模型服务未就绪 | weights 目录无可用模型（pt/onnx） |
| 50302 | 503 | LLM 服务未配置 | 未设置 `PV_LLM_API_KEY`（或 `DASHSCOPE_API_KEY`），Agent 接口不可用 |
| 50000 | 500 | 服务器内部错误 | 未预期异常（服务端记录堆栈，不泄露细节） |

### 2.5 请求/响应格式约定

- 除上传检测外，请求体与响应体均为 `application/json`，UTF-8 编码。
- `POST /api/detect/image` 为 `multipart/form-data`，字段名 `file`。
- 时间格式：`YYYY-MM-DD HH:MM:SS`（东八区，SQLite 生成）。
- 分页：`page` 从 1 开始；`page_size` 默认 10、上限 50。

## 3 接口总览

| # | 方法 | 路径 | 功能 | 需登录 |
|---|---|---|---|---|
| 1 | POST | /api/auth/register | 用户注册 | 否 |
| 2 | POST | /api/auth/login | 用户登录，返回 JWT token | 否 |
| 3 | GET | /api/user/profile | 查看个人信息 | 是 |
| 4 | PUT | /api/user/profile | 修改个人信息（昵称/邮箱） | 是 |
| 5 | PUT | /api/user/password | 修改密码（校验原密码） | 是 |
| 6 | POST | /api/detect/image | 上传图片执行缺陷检测 | 是 |
| 7 | GET | /api/record/list | 检测历史列表（分页，时间倒序） | 是 |
| 8 | GET | /api/record/{record_id} | 检测记录详情 | 是 |
| 9 | GET | /api/record/export | 导出检测历史记录（CSV） | 是 |
| 10 | GET | /api/files/uploads/{filename} | 上传原图访问（属主校验） | 是 |
| 11 | GET | /api/files/results/{filename} | 标注结果图访问（属主校验） | 是 |
| 12 | POST | /api/agent/chat | 智能体对话（SSE 流式，tool calling） | 是 |
| 13 | GET | /api/agent/sessions | 会话列表（分页） | 是 |
| 14 | GET | /api/agent/sessions/{session_id}/messages | 会话消息历史 | 是 |
| 15 | DELETE | /api/agent/sessions/{session_id} | 删除会话（级联删除消息） | 是 |
| 16 | GET | /api/agent/status | LLM 就绪状态 | 是 |

## 4 接口详述

### 4.1 POST /api/auth/register 用户注册

无需登录。

请求体（JSON）：

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| username | string | 是 | 2–30 字符，字母/数字/下划线/中文/连字符，全系统唯一 |
| password | string | 是 | 8–64 字符，须同时包含字母与数字 |
| email | string | 否 | 合法邮箱格式；填写时须未被他人使用 |
| nickname | string | 否 | ≤50 字符 |

示例：

```json
{
  "username": "zhangsan",
  "password": "Abc123456",
  "email": "z@example.com",
  "nickname": "张三"
}
```

成功响应 data：

```json
{
  "user_id": 1,
  "username": "zhangsan"
}
```

失败场景：用户名已存在 `40901`；邮箱已被使用 `40902`；字段校验失败 `40001`。

> 安全说明：密码仅保存 pbkdf2_hmac（SHA-256、600000 次迭代、16 字节随机盐）哈希，任何日志与响应均不出现明文。

### 4.2 POST /api/auth/login 用户登录

无需登录。

请求体（JSON）：

| 字段 | 类型 | 必填 |
|---|---|---|
| username | string | 是 |
| password | string | 是 |

示例：

```json
{ "username": "zhangsan", "password": "Abc123456" }
```

成功响应 data：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

- `expires_in`：令牌有效期（秒），与配置一致（默认 86400）。
- 后续请求携带 `Authorization: Bearer <access_token>`。

失败场景：用户名或密码错误 `40102`。

### 4.3 GET /api/user/profile 查看个人信息

需登录。

成功响应 data：

```json
{
  "user_id": 1,
  "username": "zhangsan",
  "email": "z@example.com",
  "nickname": "张三",
  "created_at": "2026-09-15 10:00:00"
}
```

### 4.4 PUT /api/user/profile 修改个人信息

需登录。

请求体（JSON，可只提交其中一项；`email` 传 `null` 表示清空）：

| 字段 | 类型 | 约束 |
|---|---|---|
| nickname | string | ≤50 字符，不能为空字符串 |
| email | string | 合法邮箱格式；改为他人在用返回 `40902` |

示例：

```json
{ "nickname": "李四", "email": "l@example.com" }
```

成功响应 data：更新后的个人信息（结构同 4.3）。

### 4.5 PUT /api/user/password 修改密码

需登录。

请求体（JSON）：

| 字段 | 类型 | 约束 |
|---|---|---|
| old_password | string | 须与当前密码一致，否则返回 `40102` |
| new_password | string | 8–64 字符，须含字母与数字 |

示例：

```json
{ "old_password": "Abc123456", "new_password": "Xyz789012" }
```

成功响应 data：

```json
{ "message": "密码修改成功" }
```

> 说明：密码修改后旧密码立即失效；已签发的 token 在有效期内仍可使用（演示级简化，不做主动吊销）。

### 4.6 POST /api/detect/image 上传图片执行缺陷检测

需登录。请求为 `multipart/form-data`，字段名 `file`（单张图片）。

| 字段 | 类型 | 约束 |
|---|---|---|
| file | file | jpg/jpeg/png/bmp，≤10MB |

**服务端校验链路**（前端校验仅作体验优化，服务端为最终防线）：

1. 大小校验：超过 10MB 返回 `40002`；
2. 格式校验：扩展名 + 文件魔数双重校验（防伪造扩展名），仅支持 jpg/jpeg/png/bmp，不符返回 `40003`；
3. 解码校验：实际解码失败返回 `40001`。

**处理链路**（图片全程内存处理）：读取字节 → 内存解码 → 预处理（letterbox 等比缩放至 640×640、归一化 0–1、BGR 转 RGB）→ 推理（ONNX 优先 / pt 回退）→ 坐标映射回原图像素 → 绘制检测框与标签 → JPEG 编码（质量 90）→ base64 → 原图与结果图持久化至 `storage/`（按日期子目录）→ 检测记录入库。

成功响应 data：

```json
{
  "record_id": 18,
  "model_version": "yolov8s-v1.0",
  "inference_time_ms": 88.5,
  "image_size": { "width": 1920, "height": 1080 },
  "targets": [
    {
      "class_id": 1,
      "class_name": "积灰",
      "confidence": 0.87,
      "bbox": [120, 340, 980, 720]
    }
  ],
  "defect_summary": { "积灰": 1 },
  "advice": [
    {
      "level": "high",
      "level_name": "高",
      "class_name": "积灰",
      "count": 1,
      "max_confidence": 0.87,
      "text": "面板表面存在积灰，建议安排清洗（高压水枪或清洁机器人），积灰会降低发电效率。 处置优先级：立即处理。"
    }
  ],
  "rendered_image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ...",
  "result_image_url": "/api/files/results/20260915/r18.jpg"
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| record_id | int | 检测记录 ID（已入库） |
| model_version | string | 模型版本标识（权重文件名去扩展名） |
| inference_time_ms | float | 单图推理耗时（预处理完成至推理结束，不含网络传输与渲染） |
| image_size | object | 原图尺寸 `{width, height}` |
| targets | array | 检测目标列表；未检出为空数组。元素：`class_id`（0清洁/1积灰/2鸟粪/3电损伤/4物理损伤/5积雪）、`class_name`（中文名）、`confidence`（0–1）、`bbox`（原图像素坐标系 `[x1,y1,x2,y2]`） |
| defect_summary | object | 缺陷类别汇总 `{中文类名: 数量}`（清洁类不计入） |
| advice | array | 运维建议列表，按风险从高到低排序。元素：`level`（high/mid/low）、`level_name`（高/中/低）、`class_name`、`count`、`max_confidence`、`text` |
| rendered_image_base64 | string | 标注结果图 base64（data URL，JPEG） |
| result_image_url | string | 标注结果图访问地址（需登录，属主校验） |

**置信度分级与处置语义**：

| 置信度 | 级别 | 处置语义 |
|---|---|---|
| ≥ 0.75 | 高（high） | 立即处理 |
| 0.5–0.75 | 中（mid） | 近期安排 |
| < 0.5 | 低（low） | 持续观察 |

**边界行为**：未检出目标时 `targets` 为空数组、`defect_summary` 为空对象、`advice` 输出"面板状态正常，无需维护"提示；检测记录仍保存。模型未就绪（weights 目录无 pt 也无 onnx）时返回 `50301`。

**运行指标**：单张图片推理 ≤200ms（ONNX CPU 引擎，测试硬件见任务书 D6）。

### 4.7 GET /api/record/list 检测历史列表

需登录。查询参数：

| 参数 | 类型 | 必填 | 约束 |
|---|---|---|---|
| page | int | 否 | 默认 1，≥1 |
| page_size | int | 否 | 默认 10，1–50 |

成功响应 data（仅当前用户记录，按检测时间倒序）：

```json
{
  "total": 42,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "record_id": 18,
      "image_name": "panel_03.jpg",
      "defect_summary": { "积灰": 1 },
      "inference_time_ms": 88.5,
      "model_version": "yolov8s-v1.0",
      "result_image_url": "/api/files/results/20260915/r18.jpg",
      "created_at": "2026-09-15 10:00:00"
    }
  ]
}
```

### 4.8 GET /api/record/{record_id} 检测记录详情

需登录。路径参数 `record_id`（int）。

成功响应 data：列表项全部字段 + 以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| image_url | string | 上传原图访问地址（需登录，属主校验） |
| targets | array | 完整检测目标列表（结构同 4.6） |
| image_size | object | 原图尺寸 |

失败场景：记录不存在 `40401`；记录存在但非本人 `40301`。

### 4.9 GET /api/record/export 导出检测历史记录（CSV）

需登录。查询参数（均可选，日期范围过滤）：

| 参数 | 类型 | 约束 |
|---|---|---|
| start | string | 起始日期，`YYYY-MM-DD` |
| end | string | 结束日期，`YYYY-MM-DD` |

响应：`text/csv` 附件下载（`charset=utf-8-sig`，Excel 直接打开中文不乱码），`Content-Disposition: attachment; filename="detect_records_<日期>.csv"`。

CSV 列：`记录ID, 检测时间, 文件名, 清洁, 积灰, 鸟粪, 电损伤, 物理损伤, 积雪, 总目标数, 推理耗时ms, 模型版本, 原图路径, 结果图路径`。

空数据导出仅含表头；日期格式非法返回 `40001`。

### 4.10 GET /api/files/uploads/{filename} 上传原图访问

需登录。返回原图二进制（`Content-Type` 按实际格式）。

属主校验：仅能访问本人检测记录关联的原图；非本人或文件不存在统一返回 `40401`（避免文件名探测）。

### 4.11 GET /api/files/results/{filename} 标注结果图访问

需登录。返回标注结果图二进制（JPEG）。属主校验规则同 4.10。

### 4.12 智能体接口（/api/agent/*）

LLM Agent 模块（阿里云百炼 · Kimi-K3.1-Pro，OpenAI 兼容协议 + tool calling）。所有接口需登录；未配置 API Key 时 chat 返回 `50302`。

| 接口 | 说明 |
|---|---|
| POST /api/agent/chat | 请求体 `{message, session_id?}`。响应为 `text/event-stream`（SSE），事件序列：`meta`（会话 id）→ 多个 `reasoning` / `delta` / `tool_call` / `tool_result` → `done`（含 token 用量）。断开连接即中止循环 |
| GET /api/agent/sessions | `{page, page_size?}` → 会话列表（含 message_count、最后消息摘要） |
| GET /api/agent/sessions/{id}/messages | 消息历史（role: user / assistant / tool，含 reasoning、tool_calls、tool 结果摘要） |
| DELETE /api/agent/sessions/{id} | 删除会话并级联删除消息；非本人返回 `40401` |
| GET /api/agent/status | `{llm_ready, model, message}` — LLM 配置探测 |

内置工具（由模型按需调用，服务端执行并做属主隔离，用户身份由服务端注入、模型无法伪造）：

1. `detect_image(record_id)` — 对本人检测记录重新出结论（目标框 + 置信度 + 运维建议）
2. `list_records(start_date?, end_date?, class_name?)` — 按时间/缺陷类型查询记录
3. `get_statistics(start_date?, end_date?)` — 记录数与缺陷类型聚合统计
4. `search_knowledge(query)` — 光伏项目知识库 BM25 检索（语料：`backend/scripts/build_kb.py` 从 rag 语料构建）
5. `interpret_image(record_id)` — 将标注结果图交由多模态模型做自然语言图像解读

工具循环上限 6 轮（`PV_AGENT_MAX_ROUNDS`），超限模型会基于已有信息作答。

## 5 数据模型（JSON Schema 摘要）

### 5.1 检测目标 TargetItem

```json
{
  "class_id": 1,
  "class_name": "积灰",
  "confidence": 0.87,
  "bbox": [120, 340, 980, 720]
}
```

类别映射：`0 清洁 / 1 积灰 / 2 鸟粪 / 3 电损伤 / 4 物理损伤 / 5 积雪`（与算法侧 data.yaml 一致）。

### 5.2 运维建议 AdviceItem

```json
{
  "level": "high",
  "level_name": "高",
  "class_name": "积灰",
  "count": 1,
  "max_confidence": 0.87,
  "text": "面板表面存在积灰，建议安排清洗（高压水枪或清洁机器人），积灰会降低发电效率。 处置优先级：立即处理。"
}
```

### 5.3 检测记录存储结构（detect_result JSON）

```json
{
  "image_size": { "width": 1920, "height": 1080 },
  "targets": [ { "class_id": 1, "class_name": "积灰", "confidence": 0.87, "bbox": [120, 340, 980, 720] } ]
}
```

## 6 前端调用示例

### 6.1 注册并登录

```bash
# 注册
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456","email":"z@example.com"}'

# 登录获取 token
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"Abc123456"}'
```

### 6.2 上传检测

```bash
curl -X POST http://127.0.0.1:8000/api/detect/image \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@panel_03.jpg"
```

### 6.3 查询历史与导出

```bash
curl "http://127.0.0.1:8000/api/record/list?page=1&page_size=10" \
  -H "Authorization: Bearer <access_token>"

curl -o records.csv "http://127.0.0.1:8000/api/record/export?start=2026-09-01&end=2026-09-15" \
  -H "Authorization: Bearer <access_token>"
```

## 7 部署与运行

| 项 | 说明 |
|---|---|
| Python | 3.12+ |
| 安装依赖 | `pip install -r requirements.txt` |
| 启动服务 | `uvicorn app.main:app --reload --port 8000`（在 backend/ 目录） |
| 模型部署 | 将算法侧导出产物（`best.onnx` 优先 / `best.pt` 回退）拷贝至 `backend/app/ml/weights/`；无模型时服务可启动，检测接口返回 50301 |
| 环境变量 | `PV_SECRET_KEY`（JWT 密钥，生产必设）、`PV_UPLOAD_MAX_MB`、`PV_IMGSZ`、`PV_ORT_THREADS`、`PV_TOKEN_EXPIRE_MINUTES`、`PV_PWD_ITERATIONS`、`PV_CORS_ORIGINS` |
| 数据库 | SQLite，启动时自动建库建表（`backend/data/pv_defect.db`，幂等） |
| 存储目录 | `backend/storage/uploads/`（原图）、`backend/storage/results/`（标注图），按 `YYYYMMDD/` 子目录组织 |
| 运行自检 | `cd backend && python -m pytest tests/ -v`（合成权重冒烟测试，不下载网络资源） |

## 8 修订记录

| 版本 | 日期 | 说明 |
|---|---|---|
| V1.0.0 | 2026-09-15 | 初版：依据 backend_api_spec.md 接口契约与代码实现输出；与 FastAPI /docs 交互文档保持一致 |
