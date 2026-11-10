# 光伏面板缺陷检测系统 RAG 语料库

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》及 docs/ 全部文档 |
| 用途 | RAG 助手知识来源（配合 rag/prompt.md 使用）；按主题分块、条目化组织，便于分块检索 |
| 指标声明 | 全部业务指标与任务书一致，不得修改 |

## 1 项目概述与背景

### 1.1 项目定位

基于 YOLOv8 的光伏面板缺陷检测 Web 应用（B/S 架构）。用户通过浏览器上传光伏面板巡检图像，系统自动检测六类面板状态（清洁、积灰、鸟粪、电损伤、物理损伤、积雪），输出目标框位置、置信度与运维建议。

### 1.2 项目价值

- 业务价值：自动识别异常状态并定位，帮助运维人员快速生成清洗与检修工单，缩短故障处置周期，减少发电量损失。
- 技术价值：实践 YOLOv8 目标检测模型的标注、训练、评估与部署全流程，探索检测模型在工业运维场景中的工程化应用。
- 社会价值：提升光伏电站智能运维水平，延长组件寿命、提高清洁能源产出。

### 1.3 用户与场景

- 主要用户：光伏电站运维/巡检人员，核心诉求是快速获知缺陷类别与位置并安排处置。
- 次要用户：教学实训学员，依托系统学习 AI 工程化链路。
- 系统为单角色：所有登录用户功能一致，数据范围仅限本人。

### 1.4 核心场景

1. 现场巡检检测：巡检人员浏览器打开系统，登录后拖拽或点选上传巡检图像，查看检测框、类别、置信度与运维建议。
2. 事后复盘与工单：打开历史记录回看过往检测结果，对比原图与标注结果图，导出检测记录用于工单与归档。
3. 账户维护：注册新用户、登录、修改个人信息与密码。

## 2 功能与类别定义

### 2.1 功能模块（6 个）

| 模块 | 需求编号 | 功能点 |
|---|---|---|
| 图像上传 | FR-1 | 拖拽上传、点击选择上传、图像预览、格式校验、大小校验 |
| 图像预处理 | FR-2 | 尺寸调整、归一化、格式转换 |
| 缺陷识别 | FR-3 | 基于 COCO 预训练 YOLOv8 六类检测，提供目标框位置与置信度 |
| 结果展示 | FR-4 | 渲染检测框与类别标签、可视化置信度、提供清洗/检修运维建议 |
| 历史记录 | FR-5 | 保存检测历史、查看过往结果、图像对比、检测记录导出 |
| 用户管理 | FR-6 | 注册、登录、个人信息管理、保障用户数据安全 |

### 2.2 六类检测定义与运维建议

| 类别ID | 类别 | 英文标识 | 状态说明 | 运维建议 |
|---|---|---|---|---|
| 0 | 清洁 | Clean | 表面无遮挡、无明显缺陷 | 状态正常，维持现有巡检周期 |
| 1 | 积灰 | Dusty | 灰尘沉积造成遮挡 | 安排清洗作业，恢复发电效率 |
| 2 | 鸟粪 | Bird-drop | 鸟粪沉积，局部遮挡 | 尽快局部清洁，防止长期遮挡引发热斑 |
| 3 | 电损伤 | Electrical-damage | 电弧、热斑导致的烧蚀痕迹 | 安排停机检查与专业检修 |
| 4 | 物理损伤 | Physical-Damage | 破裂、崩边等机械损伤 | 评估损伤程度，安排检修或更换 |
| 5 | 积雪 | Snow-Covered | 积雪覆盖面板 | 视积雪与发电情况安排除雪或等待自然融化 |

运维建议为系统内置文案，随检测结果展示；建议不构成处置决策依据（见局限性声明）。

### 2.3 免责声明要点

检测结果为 AI 辅助判断，置信度不等同于缺陷确诊；重大缺陷（电损伤、物理损伤等）须专业人员人工复核后再处置。免责声明展示于检测结果页底部与关于入口（D9）。

## 3 架构与数据流

### 3.1 分层架构

四层：前端 Web 客户端 → 后端 API 服务层 → AI 推理层 → 数据存储层。前后端分离 B/S 架构。

### 3.2 请求链路

浏览器 → Vite 代理 /api（开发期）→ FastAPI（8000）→ 推理引擎（ONNX Runtime / ultralytics pt）/ SQLite → 统一响应 `{code, message, data}`。

### 3.3 检测数据流

上传 → 内存校验（扩展名+魔数）→ 预处理（letterbox 等比缩放至 640×640、BGR转RGB、像素归一化 0–1）→ YOLOv8 推理（置信度阈值 0.25、NMS IoU 0.45）→ 坐标映射回原图像素 → OpenCV 绘制检测框与类别标签 → 结果与图片落库/落盘 → 返回标注图 base64 与结构化结果。

### 3.4 目录结构

根目录四大部分：algorithm/（算法）、backend/（FastAPI 后端）、frontend/（React 前端）、docs/（文档），另含 rag/（RAG 语料与提示词）。

## 4 算法与数据集

### 4.1 数据来源

Kaggle "Solar Panel Images" 公开数据集（https://www.kaggle.com/datasets/pythonafroz/solar-panel-images），按六类文件夹组织，含清洁、积灰、鸟粪、电损伤、物理损伤、积雪六类可见光 RGB 图像数千张，注册后免费下载。

### 4.2 数据集现状与处理

- 数据集无边界框标注、无预划分，需用 LabelImg 人工标注目标框，再经转换脚本生成 YOLO 格式（convert_labels.py，支持 --preview 抽样可视化抽查）。
- 划分：训练/验证/测试 = 8:1:1 分层抽样，保持各类别比例（split_dataset.py），生成 data.yaml 与 class_weights.json。
- 未标注图像处理：排除并列清单，不当作负样本（负样本会拉低召回，D12）。

### 4.3 数据增强

离线增强（augment.py）：随机翻转、±15°旋转（D14）、亮度扰动、Mosaic 拼接 + 类别加权采样（重复因子 ≤3，D19）。在线增强保留 Mosaic/HSV/翻转，关闭在线旋转避免重复增强（D23）。

### 4.4 类别不均衡应对

训练时加权过采样（默认开启，--no-weighted-sampling 可关闭）+ 类别加权采样清单 class_weights.json。

## 5 模型训练与评估

### 5.1 训练配置

- 模型：yolov8s（COCO 预训练权重迁移学习，D16）；若纯 CPU 延迟超标降级 yolov8n。
- 优化器：默认 AdamW（lr0=0.001），CLI 可切 SGD（lr0=0.01）（D17）。
- 学习率：余弦退火；早停以验证集 mAP 为监控指标。
- 损失：边框回归与分类联合损失（YOLOv8 默认组合）。
- data.yaml 类别名使用英文标识（Clean/Dusty/…），中文由应用层映射（D11）。

### 5.2 评估指标与口径

| 指标 | 验收线 | 口径 |
|---|---|---|
| mAP@0.5 | ≥ 75% | 测试集总体；工程口径（conf 扫描+IoU0.5 全点插值）与官方口径（Ultralytics val）双口径对照 |
| 主要缺陷类别召回率 | 每类 ≥ 80% | 积灰、鸟粪、电损伤、物理损伤、积雪（id 1–5）；conf=0.25、IoU=0.5 工程口径（D22），与部署展示阈值一致 |
| 清洁类 | 参考类 | id 0 为正常状态参考类，不设召回率验收线 |

评估产物：PR 曲线、各类别 AP、召回率、F1，输出 docs/model_eval_report.md（评估报告模板，由 algorithm/eval.py 运行时填充）。

### 5.3 PR 曲线读图

横轴召回率、纵轴精确率，每条曲线对应一个类别，曲线下面积即该类 AP@0.5；曲线越靠右上角综合检出能力越强。业务阈值选取：在目标类别曲线上找满足召回率要求的最低置信度点。

## 6 模型部署

### 6.1 双引擎自动探测（D25）

扫描 backend/app/ml/weights/ 目录：存在任意 `*.onnx` 时优先加载 onnxruntime 引擎（满足 200ms 指标主力）；否则回退 ultralytics pt 引擎；两者皆无则模型服务未就绪（50301）。model_version 取权重文件名。

### 6.2 ONNX 导出（D21）

默认 FP32 + opset12 + simplify + batch=1；`--half`/`--int8` 可选且自动执行 mAP 精度核对，掉点即回退。

### 6.3 剪枝与量化（D20）

- torch-pruning ≥1.6.0 结构化剪枝，默认关闭（--prune 显式开启）。
- 安全集合策略：只剪下采样 Conv、SPPF 进出、C2f 出口 cv2；**不剪 C2f 内部与 Detect 头**。
- INT8 动态量化对 YOLOv8 CNN 结构收益有限，体积压缩以剪枝为主、精度核对兜底。

### 6.4 推理性能基准

口径：端到端单图延迟（letterbox 预处理 + 推理 + NMS 后处理，不含网络传输与前端渲染），onnxruntime CPU 会话，预热后多次测量取均值。验收线 ≤200ms。基准命令：algorithm/export.py --benchmark。

## 7 后端与 API

### 7.1 后端分层

FastAPI 分层：main.py（入口/CORS/统一响应/lifespan）、api/（路由）、core/（配置/错误码/安全）、db/（SQLite 连接与建库）、repositories/（DAO）、schemas/（Pydantic）、services/（upload_check/preprocess/inference/render/advice）、ml/weights/（模型权重）。

### 7.2 接口清单（11 个）

| 方法 | 路径 | 功能 | 鉴权 |
|---|---|---|---|
| GET | / | 健康检查 | 否 |
| POST | /api/auth/register | 注册 | 否 |
| POST | /api/auth/login | 登录，签发 JWT | 否 |
| GET | /api/user/profile | 查看个人信息 | 是 |
| PUT | /api/user/profile | 修改昵称/邮箱 | 是 |
| PUT | /api/user/password | 修改密码（验证原密码） | 是 |
| POST | /api/detect/image | 上传图像执行检测（multipart，字段 file） | 是 |
| GET | /api/record/list | 历史列表（分页，时间倒序） | 是 |
| GET | /api/record/{record_id} | 记录详情 | 是 |
| GET | /api/record/export | 导出 CSV（utf-8-sig） | 是 |
| GET | /api/files/uploads/{filename} | 原图访问（属主校验） | 是 |
| GET | /api/files/results/{filename} | 标注结果图访问（属主校验） | 是 |

### 7.3 统一响应与错误码

- 成功：`{code: 0, message: "success", data: ...}`；健康检查 /、CSV 导出、图像文件流不包装。
- 错误码表：40001 参数校验失败/解码失败；40002 文件超限；40003 格式不支持/魔数不符；40101 未认证；40102 用户名或密码错误；40301 无权限；40401 资源不存在；40901 用户名已存在；40902 邮箱已存在；50301 模型未就绪；50000 服务器内部错误。

### 7.4 鉴权机制

- JWT Bearer Token（D4），密钥 PV_SECRET_KEY 环境变量（缺省开发密钥+告警日志），有效期 24h（D27）。
- 前端 axios 拦截器自动注入 Authorization 头；40101 触发清 token 并跳转登录页。
- 密码 PBKDF2-HMAC-SHA256 加盐哈希（600000 迭代、16B 随机盐，D26），不落明文。

### 7.5 图片链路（D29）

上传全程内存处理（BytesIO），原图/结果图按日期子目录持久化至 backend/storage/（uploads/、results/），标注图以 base64 返回；/api/files/* 图像需带鉴权头、前端以 blob + objectURL 加载。

## 8 数据库设计

### 8.1 表结构

- user 表：id（主键自增）、username（唯一）、password_hash、email（部分唯一，选填 D8）、nickname、created_at。
- detect_record 表：id（主键自增）、user_id（外键 → user.id，ON DELETE CASCADE）、filename、result（JSON 存储检测结果）、defect_summary、advice、inference_time_ms、model_version、created_at。

### 8.2 索引与约束

username 唯一索引、email 部分唯一索引、(user_id, created_at DESC) 复合索引、created_at 单列索引；连接须 `PRAGMA foreign_keys=ON`；SQLite 连接使用 check_same_thread=False（async 路由兼容）。

## 9 前端实现

### 9.1 技术栈

React 18 + TypeScript（strict，禁止 any）+ Vite 5（Node 18+）+ TailwindCSS 3 + Ant Design 5 + react-router-dom 6 + axios。antd 5 负责交互组件，Tailwind 负责布局与自定义视觉（D31）。

### 9.2 关键实现

- 鉴权：axios 拦截器注入 Bearer token；40101 清 token 跳登录；token 存 localStorage（pv_token，D35），不入 cookie。
- 上传：拖拽/点选，格式+大小与后端完全一致（jpg/jpeg/png/bmp、≤10MB），超限即时拦截（D36）；魔数等深度校验仅后端。
- 结果展示：后端返回标注图 base64 直接渲染，展示目标列表与置信度、运维建议、免责声明。
- 鉴权图片：/api/files/* 用 blob + objectURL（直接 img src 无法携带鉴权头）。
- 历史：分页列表、详情（原图/结果图对比）、CSV 导出（blob 下载）。
- 路由：HashRouter（D34）；响应式 Tailwind md(768px) 断点，移动端表格横向滚动（D37）。
- 状态管理：不引入全局状态库，登录态用 localStorage + hooks（D33）。

## 10 测试与质量

### 10.1 测试资产

- 后端：backend/tests/ 18 个 pytest 冒烟用例（健康检查、鉴权、注册/登录、个人信息、检测全链路与校验分支、历史、属主隔离、ONNX 引擎路径）。
- 前端：8 个 E2E 冒烟用例（登录注册、上传校验、检测结果、历史导出等页面流）。
- 并发：backend/tests/concurrency_smoke.py（标准库多线程，无第三方依赖）。

### 10.2 实测结果（2026-09-15）

- 后端冒烟 18/18 通过（10.38s）。
- 并发简单测试：20 线程×100 请求，列表接口 100% 成功（平均 42ms、最大 71ms）；检测接口并发下稳定返回 503（模型未就绪，异常处理正常）。
- 错误码覆盖：12 个中 10 个已验证（40902 邮箱已存在、50000 内部错误待补测）。

### 10.3 已知问题（问题清单）

P1（高，环境性）模型权重未部署，检测接口 50301，真实推理与三项指标未验证；P2 png/bmp 正常上传仅代码审查；P3 CSV 日期过滤未覆盖；P4 错误码 40902/50000 未覆盖；P5 浏览器矩阵仅 Chrome 实测；P6 UI/UX 设计文档暂缓。

## 11 部署运维

### 11.1 本地部署

后端：`cd backend` → `python -m venv .venv` → 激活 → `pip install -r requirements.txt` → 权重拷入 `app/ml/weights/` → `uvicorn app.main:app --reload --port 8000`。前端：`cd frontend` → `npm install` → `npm run dev`（http://localhost:5173）。

### 11.2 环境变量

PV_SECRET_KEY（JWT 密钥，正式使用必须设置）、PV_UPLOAD_MAX_MB（上传上限，默认 10）、PV_IMGSZ（输入尺寸，默认 640）、PV_ORT_THREADS（ORT 线程，默认 4）、PV_PWD_ITERATIONS（哈希迭代，默认 600000）、PV_TOKEN_EXPIRE_MINUTES（token 有效期，默认 1440）、VITE_API_BASE（前端 API 基址，默认 /api 走代理）。后端不支持 .env 文件。

### 11.3 跨域配置

开发期前端走 Vite 代理（/api → http://127.0.0.1:8000，changeOrigin），浏览器同源无跨域；后端 CORS 默认 allow_origins=["*"]、allow_credentials=False；鉴权走 Authorization 头而非 Cookie，收紧白名单不影响登录。

### 11.4 常见排错

50301 权重缺失；40101 token 过期；40002/40003 上传超限/格式不符；PowerShell 禁止运行脚本（用 npm.cmd / python.exe 直调或 Set-ExecutionPolicy -Scope Process Bypass）；/record/export 404（路由须先于 /record/{record_id} 注册）；SQLite 跨线程（check_same_thread=False）。

## 12 决策记录与经验

### 12.1 决策记录摘要（D1–D38）

- 参数类：上传上限 10MB（D2）、导出 CSV（D3）、JWT Bearer（D4）、置信度 0.25（D7）、邮箱选填（D8）、yolov8s+AdamW（D16/D17）、加权过采样（D19）、ONNX FP32（D21）、pbkdf2 哈希（D26）、token 24h（D27）、Vite 5（D32）、HashRouter（D34）、localStorage 存 token（D35）、md 768px 断点（D37）。
- 方案类：双引擎自动探测（D25）、内存优先图片链路（D29）、原生 sqlite3+DAO（D30）、antd/Tailwind 分工（D31）、不引入全局状态库（D33）、前端校验与后端一致（D36）。
- 目录/路径类：接口路径按任务指令对齐（D24）、train/eval/export.py 命名（D18）。

### 12.2 踩坑经验（实测）

1. torch-pruning 1.6.0 移除 check_dependency() API，改用 group.prune() 自动同步耦合层。
2. YOLOv8 C2f 动态 split + 残差相加导致剪枝依赖错位，采用安全集合策略规避。
3. preprocess.py 调用 letterbox 传了已移除的 stride 参数导致 ONNX 预处理崩溃，需按新签名调用。
4. SQLite async 路由跨线程需 check_same_thread=False。
5. /record/export 必须注册在 /record/{record_id} 之前。
6. PowerShell 执行策略限制：用 npm.cmd / python.exe 直调。
7. Kaggle 数据集无边界框标注，需 LabelImg 人工标注。
8. INT8 动态量化对 YOLOv8 CNN 收益有限，体积压缩以剪枝为主。

### 12.3 局限性声明（问答必引用）

1. 巡检结果使用声明：AI 辅助判断，置信度≠缺陷确诊，重大缺陷须人工复核；不构成维修、理赔或责任认定依据。
2. 模型局限性：仅识别可见光六类；热斑、隐裂、遮挡、玻璃炸裂等类别外缺陷不在能力范围；极端光照/夜间/雨雾/模糊/过远场景性能下降；极小目标与严重遮挡可能漏检。
3. 隐私保护：图片与记录仅存本机，不上传第三方；属主隔离；密码哈希存储；生产须设置 PV_SECRET_KEY。
