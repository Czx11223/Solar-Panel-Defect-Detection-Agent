# 光伏面板缺陷检测系统

基于 YOLOv8 的光伏面板六类缺陷检测 Web 系统，覆盖数据集构建、模型训练、ONNX 部署与 Web 应用的完整链路。本地运行可实现：**用户登录 → 上传光伏图片 → AI 推理检测 → 查看结果 → 查看历史记录**。

## 功能特性

- 六类缺陷检测：清洁、积灰、鸟粪、电损伤、物理损伤、积雪，检测框标注 + 置信度展示
- 检测结果渲染：标注结果图即时预览，按缺陷类别给出运维建议（置信度三档分级）
- 用户体系：注册 / 登录 / 个人信息管理，JWT 鉴权，记录按属主隔离
- 历史记录：分页列表、详情查看、按日期范围导出 CSV（Excel 直接打开不乱码）
- 推理引擎：ONNX Runtime 优先（CPU 单图 ≤ 200ms 为设计目标，需导出 ONNX 后实测），pt 权重自动回退；当前交付包仅含 pt，默认走回退路径
- 前端适配：响应式布局（md 768px 断点），兼容 Chrome / Firefox / Safari / Edge

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | React 18、TypeScript（strict）、Vite 5、TailwindCSS 3、Ant Design 5、react-router-dom 6、axios |
| 后端 | FastAPI、Uvicorn、SQLite 3、PyJWT、Pydantic、ONNX Runtime、OpenCV、Pillow |
| 算法 | Ultralytics YOLOv8、PyTorch、ONNX、matplotlib（可选 torch-pruning） |

## 目录结构

```text
├── algorithm/        # 算法：数据脚本、训练/评估/ONNX导出（train.py / eval.py / export.py）
├── backend/          # FastAPI 后端（app/ 源码、data/ 数据库、storage/ 图像、tests/ 冒烟测试）
├── frontend/         # React 前端（src/ 源码，Vite 开发代理 /api → :8000）
└── docs/             # 需求、架构、数据库、规格、接口、部署等全部文档
```

## 快速启动

环境要求：Python 3.12+、Node.js 18+。

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

部署模型权重（仓库不含权重文件，二选一放置到 `backend/app/ml/weights/`）：

```powershell
# 方案A（性能路径）：先在算法侧导出 ONNX，再拷入（需 algorithm/requirements.txt 环境）
cd ..\algorithm
python export.py --skip-eval --benchmark        # 产出 algorithm/models/best.onnx
cd ..\backend
Copy-Item ..\algorithm\models\best.onnx .\app\ml\weights\

# 方案B（回退路径）：直接放置训练产出的 pt 权重
Copy-Item ..\algorithm\runs\detect\train_final-2\weights\best.pt .\app\ml\weights\best.pt
```

当前仓库 `backend/app/ml/weights/` 内只有一份 `best.pt`，**未包含任何 .onnx**，故默认走 ultralytics 回退推理；「单图 ≤ 200ms」是 ONNX 路径的目标值，需按方案A导出并在目标硬件实测后方可声称达成。

安装与验证：

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt   # 仅开发/测试需要
python -m pytest tests/ -v
uvicorn app.main:app --reload --port 8000
```

启动服务（生产须显式设置 `$env:PV_SECRET_KEY`，见部署手册第 6 章）。验证：访问 http://127.0.0.1:8000/ 健康检查，http://127.0.0.1:8000/docs 交互文档。未部署权重时检测接口返回 50301，其余功能正常。

### 2. 前端

```powershell
cd frontend
npm install
npm run dev
```

### 3. 访问

浏览器打开 http://localhost:5173，注册账号 → 登录 → 上传光伏图片开始检测。详细步骤、环境变量、排错见 [部署运维手册](docs/deploy_manual.md)。

## API 概览

接口基址 `/api`，成功响应统一为 `{code: 0, message: "success", data}`；除注册、登录、健康检查外均需 `Authorization: Bearer <token>`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | / | 健康检查（不鉴权） |
| POST | /api/auth/register | 用户注册 |
| POST | /api/auth/login | 登录，签发 JWT |
| GET | /api/user/profile | 查看个人信息 |
| PUT | /api/user/profile | 修改昵称 / 邮箱 |
| PUT | /api/user/password | 修改密码 |
| POST | /api/detect/image | 上传图片执行检测（multipart） |
| GET | /api/record/list | 检测历史列表（分页） |
| GET | /api/record/{record_id} | 检测记录详情 |
| GET | /api/record/export | 导出检测记录 CSV |
| GET | /api/files/uploads/{filename} | 访问原图（blob 请求） |
| GET | /api/files/results/{filename} | 访问标注结果图（blob 请求） |
| POST | /api/agent/chat | 智能体对话（SSE 流式，LLM + tool calling） |
| GET | /api/agent/sessions | 会话列表 |
| GET | /api/agent/sessions/{id}/messages | 会话消息历史 |
| DELETE | /api/agent/sessions/{id} | 删除会话 |
| GET | /api/agent/status | LLM 就绪状态 |
| GET | /api/agent/tools | 工具清单（供浏览器端 Agent 循环使用） |
| POST | /api/agent/tools/{name} | 执行单个工具，body `{"arguments": {...}}` |

完整字段说明与错误码见 [接口文档](docs/api_doc.md)。

## 测试

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest tests_light/ -v
```

- `tests_light/`：轻量回归，无需 torch / ultralytics / 权重文件 / 真实 LLM（Agent 用 mock 流替身），覆盖 API 全链路、上传防护、限流、令牌撤销、算法/部署后处理一致性与 Agent SSE 对话、工具循环、会话隔离，CI 推荐。
- `tests/`：完整算法链路（合成 pt → 导出 ONNX → 真实推理），需额外安装 `torch`、`ultralytics`、`onnx`、`onnxsim`、`onnxruntime`。

## 环境变量

支持两种配置方式，优先级：**真实环境变量 > `backend/.env` 文件 > 代码缺省值**。本地开发与单机部署推荐复制 `backend/.env.example` 为 `.env` 统一管理（`.env` 已被 `.gitignore` 排除，严禁提交）；systemd / Docker / 云平台注入的环境变量不受影响。生产部署完整步骤见 [部署清单](docs/deploy_checklist.md)。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PV_SECRET_KEY` | 开发缺省值 | JWT 签名密钥；`PV_ENV=production` 时未设置将拒绝启动 |
| `PV_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 允许来源，逗号分隔 |
| `PV_TOKEN_EXPIRE_MINUTES` | 1440 | 令牌有效期（分钟） |
| `PV_UPLOAD_MAX_MB` / `PV_UPLOAD_MAX_PIXELS` | 10 / 40000000 | 上传大小上限 / 解码前像素总量上限 |
| `PV_CONF_THRESHOLD` / `PV_IOU_THRESHOLD` | 0.25 / 0.45 | 置信度阈值 / NMS IoU |
| `PV_IMGSZ` / `PV_ORT_THREADS` | 640 / 4 | 输入边长 / ONNX CPU 线程数 |
| `PV_LOGIN_RATE_LIMIT` / `PV_REGISTER_RATE_LIMIT` / `PV_RATE_LIMIT_WINDOW` | 8 / 30 / 60 | 登录(按 IP+用户名)、注册(按 IP) 限流次数与窗口秒数 |
| `PV_PWD_ITERATIONS` | 600000 | PBKDF2 迭代次数 |
| `PV_LLM_API_KEY`（或 `DASHSCOPE_API_KEY`） | 空 | 阿里云百炼 API Key；未设置时智能体接口返回 50302，其余功能不受影响 |
| `PV_LLM_BASE_URL` | 百炼 OpenAI 兼容端点 | LLM 服务地址 |
| `PV_LLM_MODEL` | kimi-k3.1-pro | 模型 ID |
| `PV_LLM_REASONING_EFFORT` | high | 推理强度（low / high / max） |
| `PV_AGENT_MAX_ROUNDS` | 6 | 单次对话工具调用轮数上限 |
| `PV_KB_TOP_K` | 4 | 知识库检索返回条数 |
| `PV_CLOUD_ENDPOINT` | 空 | 云服务端点（取 publicConfig.endpoint）；设置后启用云端令牌校验 |
| `PV_CLOUD_APP_KEY` | 空 | 应用公开凭据（publicConfig.publishableKey）；云端自省请求必需 |
| `PV_CLOUD_AUTH` | `true` | 是否接受云端 access token 登录（与 `PV_CLOUD_ENDPOINT` 同时生效） |
| `PV_CLOUD_AUTH_TTL` | 300 | 云端令牌自省结果的缓存秒数 |

## 项目局限性声明

### 巡检结果使用声明

本系统检测结果仅为 AI 辅助判断，目标置信度不等同于缺陷确诊结论，系统给出的运维建议仅供参考。对电损伤、物理损伤等可能影响电站安全的缺陷，须由专业人员依据现场情况人工复核确认，再安排检修处置。检测结果不构成任何第三方维修、理赔或责任认定的依据。

### 模型局限性

- 训练数据来自 Kaggle "Solar Panel Images" 公开数据集，经人工标注（LabelImg）构建，样本规模、拍摄条件（光照、角度、组件型号）覆盖有限，模型在未见场景上的泛化能力存在边界
- 六类样本分布不均，虽采用类别加权采样缓解，少数类（如积雪、电损伤）的检出率仍可能低于多数类
- 质量指标目标为 mAP@0.5 ≥ 75%、缺陷类召回率 ≥ 80%（具体数值以正式评估报告为准），不同部署硬件的推理耗时存在差异
- 模型以固定输入尺寸（640）推理，极小目标与严重遮挡场景可能漏检

### 隐私与数据安全说明

- 数据本地化：上传图片、标注结果与检测记录仅存储于本机（SQLite 与 backend/storage/），不向任何第三方服务上传
- 访问控制：全部业务接口经 JWT 鉴权，历史记录与图像按属主隔离，访问他人资源返回 404/403
- 密码安全：密码经 PBKDF2 加盐哈希存储，数据库不落明文
- 生产部署须显式设置 `PV_SECRET_KEY`，避免使用开发默认密钥

## 文档索引

| 文档 | 说明 |
|---|---|
| [需求文档](docs/prd.md) | 需求分析 |
| [架构设计](docs/architecture.md) | 系统架构与数据流 |
| [数据库设计](docs/db_design.md) | 表结构与关系 |
| [技术方案规格](docs/spec.md) | 技术选型与决策记录 |
| [数据集说明](docs/dataset_readme.md) | 数据准备流程 |
| [模型训练规格](docs/model_train_spec.md) | 训练 / 评估 / 导出方案 |
| [模型评估报告](docs/model_eval_report.md) | 指标与 PR 曲线 |
| [后端 API 规格](docs/backend_api_spec.md) | 后端服务规格 |
| [接口文档](docs/api_doc.md) | 接口字段与错误码 |
| [前端规格](docs/frontend_web_spec.md) | Web 界面规格与决策记录 |
| [部署运维手册](docs/deploy_manual.md) | 本地部署步骤与排错 |
| [云托管说明](docs/cloud_deploy.md) | 单端口托管与线上更新流程 |
| [云服务接入](docs/cloud_service.md) | 云端登录 / 数据库 / 存储 / 大模型的接入方式 |
| [任务分解](docs/tasks.md) / [检查清单](docs/checklist.md) | 阶段任务与验收 |
