# 项目说明（参数文档）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档类型 | 项目说明 / 参数文档 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》、docs/spec.md、docs/checklist.md |
| 指标声明 | 本文档全部业务指标与任务书一致，不做任何修改 |

## 1 项目概述

### 1.1 定位

基于 YOLOv8 的光伏面板缺陷检测 Web 应用（B/S 架构）：用户通过浏览器上传光伏面板巡检图像，系统自动检测面板状态与缺陷类别，提供目标框位置、置信度与运维建议。

### 1.2 目标与价值

- 总体目标：实现"数据-模型-应用"全链路——数据准备 → 模型训练评估 → ONNX 部署 → Web 应用
- 业务价值：自动识别异常并定位，快速生成清洗/检修工单，缩短处置周期、减少发电量损失
- 技术价值：实践 YOLOv8 标注、训练、评估、部署全流程工程化方法
- 社会价值：提升电站智能运维水平，助力新能源资产保值增效

### 1.3 用户与场景

| 用户 | 核心诉求 |
|---|---|
| 光伏电站运维/巡检人员（主要） | 快速获知缺陷类别与位置，安排清洗与检修 |
| 教学实训学员（次要） | 完整体验 AI 工程化链路 |

单角色系统：所有登录用户功能一致，数据范围仅限本人。

## 2 模块清单

### 2.1 功能模块（6 个）

| 模块 | 需求编号 | 内容 |
|---|---|---|
| 图像上传 | FR-1 | 拖拽/点选上传、预览、格式与大小校验 |
| 图像预处理 | FR-2 | 尺寸调整、归一化、格式转换 |
| 缺陷识别 | FR-3 | YOLOv8 六类检测，输出目标框位置与置信度 |
| 结果展示 | FR-4 | 渲染检测框与类别标签、置信度可视化、运维建议 |
| 历史记录 | FR-5 | 保存/查看历史、图像对比、记录导出 |
| 用户管理 | FR-6 | 注册、登录、个人信息管理、数据安全 |

### 2.2 技术部分（4 个）

| 部分 | 目录 | 内容 |
|---|---|---|
| 算法 | algorithm/ | 数据脚本、train.py、eval.py、export.py |
| 后端 API | backend/ | FastAPI 服务、SQLite、推理引擎、18 冒烟测试 |
| 前端 Web | frontend/ | React 界面、鉴权拦截、结果可视化、历史导出 |
| 部署运维 | docs/deploy_manual.md | 本地部署、环境变量、排错 |

## 3 技术参数

### 3.1 算法参数

| 参数 | 值 | 说明 |
|---|---|---|
| 检测类别 | 6 类 | Clean / Dusty / Bird-drop / Electrical-damage / Physical-Damage / Snow-Covered |
| 模型规模 | yolov8s | COCO 预训练迁移学习（D16） |
| 输入尺寸 imgsz | 640 | letterbox 等比缩放（backend 参数 PV_IMGSZ） |
| 置信度阈值 | 0.25 | 展示阈值（D7/D22） |
| NMS IoU 阈值 | 0.45 | 框架默认 |
| 数据集划分 | 8:1:1 | 训练/验证/测试，分层抽样 |
| 标注格式 | YOLO txt | LabelImg XML 转换 |
| 类别加权采样 | 因子 ≤3 | 应对类别不均衡（D19，可关闭） |
| 数据增强 | 翻转/±15°旋转/亮度/Mosaic | 离线；在线保留 Mosaic/HSV/翻转、关闭旋转（D14/D23） |
| 优化器 | AdamW，lr0=0.001 | CLI 可切 SGD lr0=0.01（D17） |
| 学习率策略 | 余弦退火 + 早停 | 监控验证集 mAP |
| 损失 | YOLOv8 默认 | 边框+分类联合损失 |
| ONNX 导出 | FP32、opset12、simplify、batch=1 | 可选 --half/--int8 并自动精度核对（D21） |
| 剪枝 | torch-pruning ≥1.6.0，默认关闭 | 安全集合策略：下采样 Conv/SPPF 进出/C2f 出口 cv2；不剪 C2f 内部与 Detect 头（D20） |

### 3.2 后端参数

| 参数 | 值 | 说明 |
|---|---|---|
| Web 框架 | FastAPI + Uvicorn | 端口 8000 |
| 上传上限 | 10MB（PV_UPLOAD_MAX_MB） | 超限返回 40002 |
| 上传格式 | jpg/jpeg/png/bmp | 扩展名+魔数双重校验 |
| 密码哈希 | PBKDF2-HMAC-SHA256，600000 迭代，16B 随机盐（PV_PWD_ITERATIONS） | 标准库实现（D26） |
| JWT 有效期 | 1440 分钟（PV_TOKEN_EXPIRE_MINUTES） | 过期返回 40101 |
| JWT 密钥 | PV_SECRET_KEY | 缺省开发密钥+告警 |
| ORT 线程 | 4（PV_ORT_THREADS） | onnxruntime CPU 线程数 |
| CORS | allow_origins=["*"]、allow_credentials=False | 开发默认放开，收紧改 config.py |
| 统一响应 | {code, message, data} | 健康检查/CSV/图像流除外 |

### 3.3 前端参数

| 参数 | 值 | 说明 |
|---|---|---|
| 框架 | React 18 + TypeScript（strict） | 禁止 any |
| 构建 | Vite 5（Node 18+） | 开发端口 5173 |
| UI | Ant Design 5 + TailwindCSS 3 | antd 管组件、Tailwind 管布局（D31） |
| 路由 | HashRouter | 部署子路径刷新不 404（D34） |
| API 基址 | VITE_API_BASE，默认 /api | 开发期走 Vite 代理 → 127.0.0.1:8000 |
| token 存储 | localStorage（pv_token） | 不入 cookie（D35） |
| 响应式断点 | Tailwind md(768px) | 移动端表格横向滚动（D37） |
| 上传校验 | 与后端一致 | jpg/jpeg/png/bmp、≤10MB，超限即时拦截（D36） |

### 3.4 部署参数

| 参数 | 值 | 说明 |
|---|---|---|
| 后端启动 | uvicorn app.main:app --reload --port 8000 | 在 backend/ 目录执行 |
| 前端启动 | npm run dev | 访问 http://localhost:5173 |
| 权重部署位 | backend/app/ml/weights/ | ONNX 优先、pt 回退 |
| 数据库 | backend/data/pv_defect.db | 启动自动建库（幂等） |
| 图像存储 | backend/storage/uploads\|results/YYYYMMDD/ | 按日期归档 |
| 环境变量 | PV_SECRET_KEY / PV_UPLOAD_MAX_MB / PV_IMGSZ / PV_ORT_THREADS / PV_PWD_ITERATIONS / PV_TOKEN_EXPIRE_MINUTES / VITE_API_BASE | 后端不支持 .env 文件，系统环境设置 |

## 4 系统架构与数据流

四层架构：前端 Web 客户端 → 后端 API 服务层 → AI 推理层 → 数据存储层。

请求链路：浏览器 → Vite 代理 /api → FastAPI → 推理引擎（ONNX/pt）/ SQLite → 统一响应返回。

检测数据流：上传 → 内存校验（扩展名+魔数）→ 预处理（letterbox 640/归一化/格式转换）→ 推理 → NMS 后处理 → 坐标映射回原图 → OpenCV 渲染标注图 → 结果与图片落库/落盘 → 返回 base64 标注图与结构化结果。

## 5 数据库设计

SQLite3，两表（详见 docs/db_design.md）：

| 表 | 关键字段 | 说明 |
|---|---|---|
| user | id、username（唯一）、password_hash、email（部分唯一）、nickname、created_at | PBKDF2 哈希，不落明文 |
| detect_record | id、user_id（外键→user.id，级联删除）、filename、result（JSON）、defect_summary、advice、inference_time_ms、model_version、created_at | 属主隔离在查询层生效 |

索引：username 唯一索引、email 部分唯一索引、(user_id, created_at DESC) 复合索引、created_at 单列索引。连接须 `PRAGMA foreign_keys=ON`。

## 6 API 接口清单

接口基址 /api，除注册/登录/健康检查外均需 `Authorization: Bearer <token>`（详见 docs/api_doc.md）：

| 方法 | 路径 | 功能 | 鉴权 |
|---|---|---|---|
| GET | / | 健康检查 | 否 |
| POST | /api/auth/register | 注册 | 否 |
| POST | /api/auth/login | 登录（签发 JWT） | 否 |
| GET | /api/user/profile | 查看个人信息 | 是 |
| PUT | /api/user/profile | 修改昵称/邮箱 | 是 |
| PUT | /api/user/password | 修改密码（验原密码） | 是 |
| POST | /api/detect/image | 上传图像并检测 | 是 |
| GET | /api/record/list | 历史列表（分页倒序） | 是 |
| GET | /api/record/{record_id} | 记录详情 | 是 |
| GET | /api/record/export | 导出 CSV（utf-8-sig） | 是 |
| GET | /api/files/uploads/{filename} | 原图访问（属主校验） | 是 |
| GET | /api/files/results/{filename} | 标注结果图访问（属主校验） | 是 |

错误码表：

| code | HTTP | 含义 |
|---|---|---|
| 0 | 200 | 成功 |
| 40001 | 400 | 参数校验失败/图像解码失败 |
| 40002 | 400 | 文件大小超限（>10MB） |
| 40003 | 400 | 文件格式不支持/魔数不符 |
| 40101 | 401 | 未认证（token 缺失/无效/过期） |
| 40102 | 401 | 用户名或密码错误 |
| 40301 | 403 | 无权限（访问他人记录/图像） |
| 40401 | 404 | 资源不存在 |
| 40901 | 409 | 用户名已存在 |
| 40902 | 409 | 邮箱已存在 |
| 50301 | 503 | 模型服务未就绪（权重缺失） |
| 50000 | 500 | 服务器内部错误（不泄露细节） |

## 7 性能与质量指标

### 7.1 任务书硬指标（验收线）

| 指标 | 目标 | 口径 |
|---|---|---|
| mAP@0.5 | ≥ 75% | 测试集总体，工程+官方双口径 |
| 主要缺陷类别召回率 | 每类 ≥ 80% | 积灰/鸟粪/电损伤/物理损伤/积雪，conf=0.25、IoU=0.5 |
| 单图推理耗时 | ≤ 200ms | CPU onnxruntime，letterbox+推理+NMS，预热多次取均值，不含传输与渲染 |

### 7.2 测试实测结果（2026-09-15，docs/test_report.md）

| 项 | 结果 |
|---|---|
| 后端冒烟 | 18/18 通过（10.38s） |
| 前端 E2E | 8 用例通过 |
| 错误码覆盖 | 12 个中 10 个（40902/50000 待补测） |
| 并发简单测试 | 20 线程×100 请求：列表接口 100% 成功（平均 42ms/最大 71ms）；检测接口并发下稳定返回 503（权重未就绪，异常处理正常） |
| 兼容性 | Chrome 通过；Firefox/Safari/Edge 清单待执行 |
| 真实模型指标 | 待权重部署后复核（export.py --benchmark + model_eval_report.md） |

## 8 安全设计

| 环节 | 措施 |
|---|---|
| 密码存储 | PBKDF2 加盐哈希（600000 迭代），不落明文、日志不泄露 |
| 登录态 | JWT Bearer Token，24h 过期，密钥环境变量注入 |
| 权限隔离 | 记录与图像按属主校验，越权返回 40301/404 |
| 上传防护 | 扩展名+魔数双重校验，防伪造扩展名绕过 |
| 传输加密 | 全站 HTTPS（生产部署由反向代理终止 TLS）；开发期 HTTP |
| 隐私保护 | 用户数据仅用于本系统检测服务，不外传；上传图像不用于模型训练 |

## 9 部署参数（本地开发）

部署步骤详见 docs/deploy_manual.md，要点：

```powershell
# 后端
cd backend
python -m venv .venv && .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item ..\algorithm\models\best.onnx .\app\ml\weights\   # 部署权重
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev        # 访问 http://localhost:5173
```

## 10 决策记录（D1–D38）

| 编号 | 决策点 | 结论 |
|---|---|---|
| D1 | 数据集标注策略 | 全量标注，工作量过大按类均衡抽样 |
| D2 | 上传大小上限 | 10MB |
| D3 | 历史导出格式 | CSV |
| D4 | 登录态方案 | JWT Bearer Token |
| D5 | 数据库存储加密 | 敏感字段应用层加密 + 部署层磁盘加密 |
| D6 | 推理性能测试硬件 | 待明确（GPU 或纯 CPU） |
| D7 | 置信度展示阈值 | 0.25 |
| D8 | 注册邮箱 | 选填 |
| D9 | 免责声明位置 | 检测结果页底部 + 关于入口 |
| D10 | 前端静态托管 | 开发期 Vite，部署期 Nginx |
| D11 | data.yaml 类别名语言 | 英文标识，中文应用层映射 |
| D12 | 未标注图像处理 | 排除并列清单 |
| D13 | 增强样本存放 | 并入 train（augm_ 前缀） |
| D14 | 旋转角度策略 | ±15° 随机 |
| D15 | 标注可视化抽查 | 提供 --preview |
| D16 | 模型规模 | yolov8s（CPU 超标降级 yolov8n） |
| D17 | 优化器 | 默认 AdamW lr0=0.001，可切 SGD |
| D18 | 脚本命名 | train/eval/export.py，产物入 algorithm/models/ |
| D19 | 训练加权过采样 | 默认开启（因子≤3） |
| D20 | 剪枝落地 | torch-pruning ≥1.6.0 默认关闭；安全集合策略 |
| D21 | ONNX 精度 | 默认 FP32；--half/--int8 可选并自动 mAP 核对 |
| D22 | 召回率口径 | conf=0.25+IoU=0.5 工程口径，并列官方口径 |
| D23 | 在线增强策略 | 保留 Mosaic/HSV/翻转，关闭在线旋转 |
| D24 | 接口路径风格 | 按任务指令对齐（detect/image、record/list、record/export） |
| D25 | 推理引擎 | 双引擎自动探测：onnx 优先、pt 回退 |
| D26 | 密码哈希算法 | 标准库 pbkdf2_hmac |
| D27 | JWT 参数 | 环境变量密钥 + 24h 过期 |
| D28 | 运维建议策略 | 六类模板 + 置信度三档分级 |
| D29 | 图片处理链路 | 内存优先，原图/结果图按日期落盘 |
| D30 | 数据库访问层 | 原生 sqlite3 + DAO，不引入 ORM |
| D31 | antd 与 Tailwind 分工 | antd 组件 / Tailwind 布局 |
| D32 | 构建工具 | Vite 5（Node 18+） |
| D33 | 状态管理 | 不引入全局状态库 |
| D34 | 路由模式 | HashRouter |
| D35 | token 存储 | localStorage，不入 cookie |
| D36 | 前端上传校验深度 | 格式+大小与后端一致，魔数仅后端 |
| D37 | 响应式断点 | md(768px) 主切换 |
| D38 | 个人信息功能范围 | Header 展示用户名+退出，接口保留 |

## 11 局限性声明

1. **巡检结果使用声明**：检测结果为 AI 辅助判断，置信度不等同于缺陷确诊结论，运维建议仅供参考。对电损伤、物理损伤等可能影响电站安全的缺陷，须由专业人员人工复核后安排检修处置。检测结果不构成第三方维修、理赔或责任认定依据。
2. **模型局限性**：模型基于可见光 RGB 六类数据训练，类别范围外缺陷（热斑、隐裂、遮挡、玻璃炸裂）不在检测能力内；极端光照、夜间、雨雾、严重模糊与过远拍摄场景性能可能显著下降；极小目标与严重遮挡场景可能漏检；指标基于测试集统计，实际部署仍可能漏检。
3. **隐私保护**：上传图像与检测记录仅存储于本机（SQLite + storage/），不向任何第三方上传；记录与图像按属主隔离；密码哈希存储不落明文；生产部署须显式设置 PV_SECRET_KEY。

## 12 文档索引

| 文档 | 内容 |
|---|---|
| docs/prd.md | 产品需求 |
| docs/architecture.md | 系统架构 |
| docs/db_design.md | 数据库设计 |
| docs/spec.md | 技术方案规格（D1–D10） |
| docs/dataset_spec.md / dataset_readme.md | 数据准备规格与流程（D11–D15） |
| docs/model_train_spec.md / model_eval_report.md | 训练评估规格与报告模板（D16–D22） |
| docs/backend_api_spec.md / api_doc.md | 后端规格与接口文档（D23–D30） |
| docs/frontend_web_spec.md | 前端规格（D31–D38） |
| docs/deploy_manual.md / deploy_spec.md | 部署运维手册与规格 |
| docs/test_report.md / test_spec.md | 测试报告与规格 |
| docs/tasks.md / checklist.md | 任务分解与检查清单 |
| docs/ai_dev_tutorial.md | AI 协作教程 |
| docs/report_ppt_outline.md | 项目汇报 PPT 大纲 |
| rag/pv_system_corpus.md / rag/prompt.md | RAG 语料库与提示词 |
