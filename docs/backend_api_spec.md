# 后端API服务规格说明书（Backend API Spec）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 阶段 | 阶段4：后端API服务开发 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 文档状态 | 已确认（2026-09-15，D24–D30按建议默认值执行） |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》任务6；docs/spec.md 第4章接口设计、第8章安全设计；docs/db_design.md；docs/architecture.md；docs/tasks.md 阶段4 |

## 1 阶段目标与交付物

基于FastAPI开发前后端分离RESTful后端服务：用户注册登录与JWT鉴权、图片上传校验与预处理、YOLOv8（pt/ONNX双引擎）推理、检测框与运维建议输出、标注图base64返回、检测记录入库与历史查询导出。本阶段只交付后端代码与接口文档，不包含前端与联调（阶段6）。

| # | 交付物 | 类型 | 说明 |
|---|---|---|---|
| 1 | backend/requirements.txt | 依赖清单 | 后端锁定依赖版本 |
| 2 | backend/app/ 完整代码 | 后端代码 | main、config、security、db、repositories、schemas、api路由、services |
| 3 | backend/storage/ | 存储目录 | uploads（原图）、results（标注图），按日期子目录组织 |
| 4 | backend/tests/ | 测试 | pytest冒烟用例（注册→登录→鉴权→检测→列表→导出全链路） |
| 5 | docs/api_doc.md | 接口文档 | 完整OpenAPI接口文档（配合FastAPI /docs交互文档） |
| 6 | docs/backend_api_spec.md | 规格说明 | 本文档 |

接口路径按本轮任务指令对齐（D24），与spec.md第4章既有清单的差异与同步方式见第4章与第7章。

## 2 运行环境与依赖

| 项 | 内容 |
|---|---|
| Python | 3.12+ |
| 直接依赖 | fastapi、uvicorn[standard]、python-multipart、PyJWT、pydantic、email-validator、onnxruntime、opencv-python、pillow、numpy、ultralytics（pt引擎回退） |
| 数据库 | 标准库sqlite3（任务书技术栈锁定，D30不引入ORM） |
| 密码哈希 | 标准库hashlib.pbkdf2_hmac（D26，零第三方依赖） |

每个模块文件头部写明：功能说明、运行环境、关键逻辑说明。所有可调参数集中在 config.py，通过环境变量覆盖，开箱即用。

## 3 后端目录结构

沿用 project_structure.md 的 backend/ 规划，按 D30 将 models/（ORM）调整为 repositories/（原生SQL DAO），其余不变：

```text
backend/
├── app/
│   ├── main.py                   # 应用入口：CORS、路由注册、全局异常、启动事件（建库+加载模型）
│   ├── api/                      # 路由层
│   │   ├── auth.py               # POST /api/auth/register、POST /api/auth/login
│   │   ├── user.py               # 个人信息查看/修改、修改密码
│   │   ├── detect.py             # POST /api/detect/image 上传校验与检测编排
│   │   └── record.py             # 历史列表/详情/导出、图像访问（属主校验）
│   ├── core/
│   │   ├── config.py             # 配置：上传上限、阈值、路径、JWT密钥与过期时间（环境变量覆盖）
│   │   ├── pv_classes.py         # 六类映射表（class_id/英文标识/中文名，与algorithm侧一致）
│   │   ├── security.py           # pbkdf2密码哈希、JWT签发与校验、get_current_user依赖
│   │   └── errors.py             # 业务错误码定义
│   ├── db/
│   │   ├── database.py           # SQLite连接依赖（PRAGMA foreign_keys=ON，每请求独立连接）
│   │   └── init_db.py            # 建库建表（user、detect_record，DDL与db_design.md一致）
│   ├── repositories/
│   │   ├── user_repo.py          # user表DAO
│   │   └── record_repo.py        # detect_record表DAO
│   ├── schemas/                  # Pydantic请求/响应模型
│   │   ├── auth.py               # 注册/登录请求、token响应
│   │   ├── user.py               # 个人信息请求/响应
│   │   ├── detect.py             # 检测请求/响应
│   │   └── record.py             # 历史列表/详情/导出
│   ├── services/
│   │   ├── upload_check.py       # 文件格式/大小/解码校验（扩展名+魔数双重）
│   │   ├── preprocess.py         # 图像预处理：解码、letterbox、归一化、格式转换
│   │   ├── inference.py          # 推理引擎：ONNX优先（onnxruntime），pt回退（ultralytics）
│   │   ├── render.py             # 标注图渲染（OpenCV绘制检测框与类别标签）
│   │   └── advice.py             # 运维建议匹配（六类建议模板+置信度分级）
│   └── ml/
│       └── weights/              # 部署权重：best.onnx（优先）/ best.pt（回退），由algorithm产出拷贝
├── storage/
│   ├── uploads/                  # 原图（YYYYMMDD/子目录）
│   └── results/                  # 标注结果图（YYYYMMDD/子目录）
├── tests/                        # pytest冒烟用例
└── requirements.txt              # 后端依赖
```

## 4 接口契约

### 4.1 接口总览

RESTful风格，统一前缀 /api，响应体统一JSON `{code, message, data}`（文件上传请求为 multipart/form-data）。接口路径按本轮任务指令对齐（D24），个人信息管理接口补齐模块清单要求，历史详情与图像访问为前端历史页必需（db_design.md 已设计 image_path/result_image_path 字段）：

| # | 方法 | 路径 | 功能 | 需登录 |
|---|---|---|---|---|
| 1 | POST | /api/auth/register | 用户注册 | 否 |
| 2 | POST | /api/auth/login | 用户登录，返回JWT token | 否 |
| 3 | GET | /api/user/profile | 查看个人信息 | 是 |
| 4 | PUT | /api/user/profile | 修改个人信息（昵称/邮箱） | 是 |
| 5 | PUT | /api/user/password | 修改密码（验证原密码） | 是 |
| 6 | POST | /api/detect/image | 上传图片执行缺陷检测 | 是 |
| 7 | GET | /api/record/list | 当前用户检测历史列表（分页，时间倒序） | 是 |
| 8 | GET | /api/record/{record_id} | 检测记录详情 | 是 |
| 9 | GET | /api/record/export | 导出检测历史记录（CSV，D3） | 是 |
| 10 | GET | /api/files/uploads/{filename} | 上传原图访问（属主校验） | 是 |
| 11 | GET | /api/files/results/{filename} | 标注结果图访问（属主校验） | 是 |

### 4.2 统一响应与错误码

- 成功：HTTP 200，`{"code": 0, "message": "success", "data": {...}}`
- 业务失败：HTTP 4xx/5xx + `{"code": 业务码, "message": "中文可读原因", "data": null}`
- 参数校验失败（FastAPI/Pydantic）：HTTP 422，映射为 code=40001
- 未捕获异常：全局处理器兜底，HTTP 500，code=50000，日志记录堆栈，响应不泄露内部细节

| code | 含义 | 典型场景 |
|---|---|---|
| 0 | 成功 | — |
| 40001 | 参数校验失败 | 字段缺失、邮箱格式错误、图像解码失败 |
| 40002 | 文件大小超限 | 超过10MB（D2） |
| 40003 | 文件格式不支持 | 非jpg/jpeg/png/bmp，或扩展名与魔数不符 |
| 40101 | 未认证 | token缺失/无效/过期 |
| 40102 | 用户名或密码错误 | 登录失败 |
| 40301 | 无权限 | 访问他人记录/图像 |
| 40401 | 资源不存在 | 记录不存在 |
| 40901 | 用户名已存在 | 注册冲突 |
| 40902 | 邮箱已存在 | 注册/改邮箱冲突 |
| 50301 | 模型服务未就绪 | weights目录无可用模型 |
| 50000 | 服务器内部错误 | 未预期异常 |

### 4.3 接口详述

#### 4.3.1 POST /api/auth/register 用户注册

请求体（JSON）：

```json
{"username": "zhangsan", "password": "Abc123456", "email": "z@example.com", "nickname": "张三"}
```

- username：2–30字符，唯一；password：8–64字符（须含字母与数字）；email选填（D8），填写时须合法且唯一；nickname选填
- 密码仅存pbkdf2加盐哈希（D26），任何日志与响应不落明文

响应 data：`{"user_id": 1, "username": "zhangsan"}`

#### 4.3.2 POST /api/auth/login 用户登录

请求体（JSON）：`{"username": "zhangsan", "password": "Abc123456"}`

响应 data：`{"access_token": "<JWT>", "token_type": "bearer", "expires_in": 86400}`

- JWT：HS256，payload含 `sub`（user_id）、`exp`（24h，D27）；后续请求携带 `Authorization: Bearer <token>`

#### 4.3.3 GET /api/user/profile 查看个人信息

响应 data：`{"user_id":1,"username":"zhangsan","email":"z@example.com","nickname":"张三","created_at":"2026-09-15 10:00:00"}`

#### 4.3.4 PUT /api/user/profile 修改个人信息

请求体（JSON）：`{"nickname": "李四", "email": "l@example.com"}`（可只提交其中一项；邮箱改为他人在用返回40902）

响应 data：更新后的个人信息。

#### 4.3.5 PUT /api/user/password 修改密码

请求体（JSON）：`{"old_password": "Abc123456", "new_password": "Xyz789012"}`

- 旧密码错误返回40102；成功后强制下次请求使用新token（不主动吊销旧token，属演示级简化）

#### 4.3.6 POST /api/detect/image 上传图片执行缺陷检测

请求：multipart/form-data，字段名 `file`（单张图片）。

校验链路（服务端为最终防线，前端校验仅作体验优化）：
1. 大小 ≤ 10MB（D2），超限返回40002
2. 格式：扩展名 + 文件魔数双重校验，仅支持 jpg/jpeg/png/bmp，否则返回40003
3. 解码校验：PIL/OpenCV实际解码失败返回40001

处理链路：全内存（D29）：`await file.read()` → BytesIO → OpenCV解码 → BGR转RGB → letterbox等比缩放至640×640（灰边114，与训练一致）→ 归一化0–1 → 推理 → 坐标映射回原图 → OpenCV渲染标注图 → base64编码（JPEG质量90）→ 持久化原图与结果图 → 入库。

响应 data：

```json
{
  "record_id": 18,
  "model_version": "yolov8s-v1.0",
  "inference_time_ms": 88.5,
  "image_size": {"width": 1920, "height": 1080},
  "targets": [
    {"class_id": 1, "class_name": "积灰", "confidence": 0.87, "bbox": [120, 340, 980, 720]}
  ],
  "defect_summary": {"积灰": 1},
  "advice": [
    {"level": "high", "level_name": "高", "class_name": "积灰", "count": 1,
     "max_confidence": 0.87, "text": "面板表面存在积灰，建议近期安排清洗，积灰会降低发电效率。"}
  ],
  "rendered_image_base64": "data:image/jpeg;base64,...",
  "result_image_url": "/api/files/results/20260915/r18.jpg"
}
```

- 未检出目标时 targets 为空数组、defect_summary 为空对象、advice 输出清洁类提示，记录仍保存（PRD FR-3.4）
- inference_time_ms 从预处理完成至推理结束，不含网络传输与渲染（与D6指标口径一致）
- 模型不可用时（weights目录无pt也无onnx）返回50301

#### 4.3.7 GET /api/record/list 检测历史列表

查询参数：`page`（默认1）、`page_size`（默认10，上限50）。

响应 data：

```json
{
  "total": 42, "page": 1, "page_size": 10,
  "items": [
    {"record_id": 18, "image_name": "panel_03.jpg", "defect_summary": {"积灰": 1},
     "inference_time_ms": 88.5, "model_version": "yolov8s-v1.0",
     "result_image_url": "/api/files/results/20260915/r18.jpg",
     "created_at": "2026-09-15 10:00:00"}
  ]
}
```

仅返回当前用户记录（属主隔离），按 created_at 倒序。

#### 4.3.8 GET /api/record/{record_id} 检测记录详情

响应 data：列表项字段 + `image_url`（原图访问路径）+ 完整 `targets`（detect_result 解析）。非本人记录返回40301，不存在返回40401。

#### 4.3.9 GET /api/record/export 导出检测历史记录

查询参数：`start`/`end`（可选，日期范围，YYYY-MM-DD）。

- 导出当前用户全部（或时间范围内）记录为CSV（D3），`Content-Type: text/csv; charset=utf-8-sig`（Excel直接打开中文不乱码），`Content-Disposition: attachment; filename=detect_records_<日期>.csv`
- CSV列：记录ID、检测时间、文件名、缺陷汇总（积灰数量/鸟粪数量/电损伤数量/物理损伤数量/积雪数量/清洁数量）、总目标数、推理耗时ms、模型版本、原图路径、结果图路径
- 空数据导出仅含表头

#### 4.3.10/4.3.11 GET /api/files/uploads|results/{filename} 图像访问

- 按记录查询图像归属，非本人返回40301；文件不存在返回40401
- 返回图像二进制（Content-Type按扩展名）；历史页用此地址做原图/结果图对比

## 5 关键设计

### 5.1 统一响应与全局异常

errors.py 定义业务错误码（见4.2）；异常处理器（main.py注册）覆盖：RequestValidationError→40001、HTTPException→按状态码映射、未知异常→50000并记录堆栈。路由层不散落try/except，业务校验抛BizError（自定义异常，携带code/status/message）。

### 5.2 JWT鉴权与密码哈希

- 密码：pbkdf2_hmac（SHA-256，迭代600000次，16字节随机盐，盐随哈希存储格式 `pbkdf2$iter$salt_hex$hash_hex`）；校验用hmac.compare_digest防时序攻击（D26）
- JWT：PyJWT，HS256，SECRET_KEY从环境变量 `PV_SECRET_KEY` 读取，未设置时用开发默认密钥并打印告警日志（D27）；过期时间 `PV_TOKEN_EXPIRE_MINUTES` 默认1440
- get_current_user依赖：解析Bearer token → 查user表 → 注入request.state.user；用户已删除则40101

### 5.3 图片全内存链路

上传文件读取到内存BytesIO后立即处理：解码、预处理、推理、渲染全程不落临时磁盘（D29）；原图与结果图按需持久化至 storage/{uploads,results}/YYYYMMDD/（历史记录与图像访问需要，属持久化存储而非临时堆积）；响应中的标注图以base64返回（前端即时展示，不依赖文件访问接口）。文件名：原图保留用户文件名（重名时加时间戳前缀），结果图 `r<record_id>.jpg`。

### 5.4 模型加载与推理

- 双引擎（D25）：启动事件中扫描 ml/weights/，存在 `*.onnx` 则加载onnxruntime引擎（CPU，线程数可配）；否则加载 `*.pt`（ultralytics YOLO）；两者皆无则标记服务未就绪（detect返回50301），其余接口不受影响
- ONNX推理：预处理（letterbox 640 + 归一化）→ session.run → 输出 `(1, 4+nc, N)` → 反letterbox坐标映射回原图像素 → NMS（置信度阈值0.25 D7，IoU阈值0.45）→ 组装目标列表
- PT推理：YOLO.predict（框架内置预处理与NMS，`imgsz=640, conf=0.25, iou=0.45`）
- 模型常驻内存，单请求不重复加载；推理耗时记录inference_time_ms，作为≤200ms指标复核数据（测试硬件按D6）

### 5.5 运维建议匹配

advice.py维护六类建议模板（静态配置），检测后按类别聚合：每类输出数量、最高置信度、处置建议；置信度三档分级影响处置优先级：

| 置信度 | 级别 | 处置语义 |
|---|---|---|
| ≥ 0.75 | 高 | 立即处理 |
| 0.5–0.75 | 中 | 近期安排 |
| < 0.5 | 低 | 持续观察 |

建议文本示例（正式文本随代码交付）：

- 清洁：面板状态正常，无需维护
- 积灰：面板表面存在积灰，建议清洗，积灰会降低发电效率
- 鸟粪：检测到鸟粪附着，建议及时清除并评估防鸟措施
- 电损伤：检测到疑似电损伤，建议停机检修并由专业人员排查电路，防范火灾风险
- 物理损伤：检测到物理损伤，建议评估结构安全，必要时更换组件
- 积雪：检测到积雪覆盖，建议关注承重与发电效率，条件允许时及时除雪

advice列表按风险从高到低排序；未检出缺陷时输出清洁类提示。

### 5.6 属主隔离

记录查询、详情、导出、图像访问均以当前登录用户user_id为过滤条件；图像访问接口按文件名反查记录归属，杜绝越权访问（spec.md 第8章权限隔离要求）。

## 6 数据存储

表结构、DDL、索引、外键与detect_result JSON结构完全沿用 [db_design.md](db_design.md)（user表、detect_record表）；init_db.py按该文档DDL建表，启动时自动执行（幂等）。新增约定：

- detect_result 存 `{image_size, targets}`（与db_design 4.4一致）
- defect_summary 存 `{"积灰":1,"鸟粪":2}`（中文类名键，历史列表直接展示）
- 删除记录时应用层同步删除对应图像文件（数据库不负责文件删除，见db_design 4.3）

## 7 待确认决策点

以下决策点不改变任务书功能范围与技术栈，仅确定实现参数。未获明确意见时按"建议默认值"执行（延续D1–D23惯例）。

| 编号 | 决策点 | 说明 | 建议默认值 |
|---|---|---|---|
| D24 | 接口路径风格 | 本轮任务指令路径（detect/image、record/list、record/export）与spec.md第4章既有路径（detect、history）不一致 | 按本轮任务指令对齐，补全个人信息/详情/图像访问接口；同步更新spec.md第4章与tasks.md |
| D25 | 推理引擎 | pt（ultralytics）与onnx（onnxruntime）选择；onnx为200ms指标主力 | 双引擎自动探测：weights目录有onnx优先加载，否则回退pt；两者皆无服务未就绪（50301） |
| D26 | 密码哈希算法 | db_design.md写bcrypt/argon2；passlib与bcrypt 4.x存在版本兼容问题 | 标准库hashlib.pbkdf2_hmac（SHA-256/600k迭代/随机盐，零依赖无兼容风险，仍属加盐哈希） |
| D27 | JWT参数 | 密钥来源与过期时间 | SECRET_KEY环境变量（缺省dev密钥+告警日志）；过期24h |
| D28 | 运维建议策略 | 建议文本与置信度的关系 | 六类静态建议模板 + 置信度三档分级（高/中/低）影响处置优先级；清洁类输出无需维护 |
| D29 | 图片处理链路 | 用户要求内存处理优先，避免临时磁盘堆积 | 上传全程内存处理（BytesIO）；原图/结果图按日期子目录持久化至storage（历史展示所需）；标注图base64返回 |
| D30 | 数据库访问层 | project_structure.md原规划SQLAlchemy ORM，任务书技术栈锁定sqlite3 | 原生sqlite3标准库 + repositories DAO（不引入ORM）；project_structure.md中models/调整为repositories/ |

## 8 安全与合规

- 密码不落明文（D26加盐哈希）；传输层HTTPS部署期由反向代理终止TLS（spec.md 第9章）
- JWT密钥与过期控制（D27）；记录与图像按用户隔离（5.6）
- 上传校验防伪造：扩展名+魔数双重校验；解码失败拒绝
- 数据隐私（任务书约束，须写入接口文档与前端界面）：用户图像与检测数据仅用于本系统检测服务，不外传、不用于其他用途；图像存储于本地storage目录，删除记录即删除文件
- 模型局限性（须写入docs/api_doc.md与前端结果页）：检测置信度≠缺陷确诊，阈值0.25以下目标不展示，运维建议供参考，重大缺陷须人工复核

## 9 冒烟测试计划

环境：本机Python 3.12+，uvicorn启动；模型用本地合成随机权重pt（ultralytics构建nc=6随机DetectionModel保存，不下载任何网络权重与数据集）。

用例（pytest，tests/）：

1. 健康检查与未认证访问：无token访问detect/record返回40101
2. 注册：成功；用户名重复40901；邮箱格式非法40001
3. 登录：成功返回token；密码错误40102
4. 个人信息：查看/修改/修改密码全链路
5. 检测（合成权重pt引擎）：合法jpg成功，返回targets结构/defect_summary/advice/base64图/record_id；大小超限40002；伪造扩展名40003；非图片内容40001
6. 历史：list分页与倒序、detail、export CSV内容与表头
7. 属主隔离：用户B访问用户A的记录/图像返回40301
8. 模型缺失分支：临时移走权重，detect返回50301

## 10 任务清单（2026-09-15 全部完成）

- [x] T1 backend/requirements.txt 与目录骨架（storage、ml/weights占位）
- [x] T2 core：config.py、pv_classes.py、errors.py、security.py（pbkdf2+JWT）
- [x] T3 db：database.py、init_db.py、repositories（user_repo、record_repo）
- [x] T4 schemas：auth、user、detect、record（Pydantic模型）
- [x] T5 路由：auth（注册/登录）、user（个人信息/修改密码）
- [x] T6 services：upload_check.py、preprocess.py
- [x] T7 services：inference.py（onnx/pt双引擎）、render.py、advice.py
- [x] T8 路由：detect.py（校验→预处理→推理→渲染→建议→入库→base64返回）
- [x] T9 路由：record.py（list/detail/export CSV/图像访问属主校验）
- [x] T10 main.py：CORS、全局异常、启动事件（lifespan：init_db+加载模型）
- [x] T11 docs/api_doc.md 完整接口文档
- [x] T12 冒烟测试：tests/ 用例 + 合成权重全链路运行（18用例全部通过）
- [x] T13 文档同步：spec.md第4章接口清单、tasks.md阶段4勾选、project_structure.md（repositories/调整）
