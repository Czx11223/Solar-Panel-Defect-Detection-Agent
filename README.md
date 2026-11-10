# 光伏面板缺陷检测系统

基于 YOLOv8 的光伏面板六类缺陷检测 Web 系统，覆盖数据集构建、模型训练、ONNX 部署、Web 应用与运维问答 Agent 的完整链路。本地运行可实现：**用户登录 → 上传光伏图片 → AI 推理检测 → 查看结果 → 查看历史记录 → 就巡检问题对话问答**。

## 功能特性

- **六类缺陷检测**：清洁、积灰、鸟粪、电损伤、物理损伤、积雪，检测框标注 + 置信度展示
- **检测结果渲染**：标注结果图即时预览，按缺陷类别给出运维建议（置信度三档分级）
- **智能问答 Agent**：SSE 流式对话，支持工具调用（图片检测、记录查询、知识库检索、视觉分析），会话与消息持久化，单轮最多 `PV_AGENT_MAX_ROUNDS` 轮工具循环
- **知识库检索（RAG）**：`rag/pv_system_corpus.md` 语料按二级标题分块入库，jieba 分词 + BM25 检索，零外部服务依赖
- **用户体系**：注册 / 登录 / 个人信息管理，JWT 鉴权，记录按属主隔离；改密后旧令牌立即失效（token_version 撤销）
- **历史记录**：分页列表、详情查看、按日期范围导出 CSV（Excel 直接打开不乱码）
- **推理引擎**：ONNX Runtime 优先、ultralytics pt 自动回退；按权重目录内容自动选择引擎，两者皆无时检测接口返回 50301，其余功能正常
- **前端适配**：响应式布局（md 768px 断点），兼容 Chrome / Firefox / Safari / Edge
- **云托管可选**：接入 WorkBuddy Cloud Service 后支持云端账号登录、云数据库会话/记录、云对象存储图片，前端可 keyless 直连云端大模型
- **部署形态**：Vite 开发代理（前后端分离）或 `backend/webapp_dist/` 单端口托管两种方式

## 技术栈

| 层次 | 技术 |
|---|---|
| 前端 | React 18、TypeScript（strict）、Vite 5、TailwindCSS 3、Ant Design 5、react-router-dom 6（HashRouter）、axios、react-markdown、腾讯云 Cloud SDK |
| 后端 | FastAPI、Uvicorn、SQLite 3、PyJWT、Pydantic、ONNX Runtime、OpenCV、Pillow、python-dotenv |
| Agent | openai SDK（百炼 OpenAI 兼容端点）、jieba、rank-bm25、SSE 流式 |
| 算法 | Ultralytics YOLOv8、PyTorch、ONNX、matplotlib（可选 torch-pruning） |

## 目录结构

```text
├── algorithm/        # 算法：数据脚本、训练/评估/ONNX导出（train.py / eval.py / export.py）
├── backend/          # FastAPI 后端（app/ 源码、data/ 数据库、storage/ 图像、scripts/ 工具、tests/ 与 tests_light/）
├── frontend/         # React 前端（src/ 源码，Vite 开发代理 /api → :8000）
├── rag/              # Agent 知识库语料（pv_system_corpus.md）与提示词（prompt.md）
├── docs/             # 需求、架构、数据库、规格、接口、模型、部署、测试等全部文档
└── runs/             # 根目录训练/评估运行产物（不入版本库）
```

`backend/app/` 内部分层：`api/`（路由）、`services/`（推理、预处理、后处理）、`repositories/`（数据访问）、`agent/`（LLM 客户端、循环、提示词、工具集）、`core/`（配置、安全、云鉴权）、`ml/weights/`（权重目录）。

## 快速启动

环境要求：Python 3.12+、Node.js 18+。

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**部署模型权重**（权重不入版本库：`.gitignore` 已排除 `*.pt` / `*.onnx`，目录内仅 `README.md` 入库）：

```powershell
# 方案A（推荐，ONNX 路径）：先在算法侧导出 ONNX，再拷入（需 algorithm/requirements.txt 环境）
cd ..\algorithm
python export.py --skip-eval --benchmark        # 产出 algorithm/models/best.onnx
cd ..\backend
Copy-Item ..\algorithm\models\best.onnx .\app\ml\weights\

# 方案B（回退路径）：放置训练产出的 pt 权重，另需安装 PT 引擎依赖
Copy-Item ..\algorithm\runs\detect\train_final-2\weights\best.pt .\app\ml\weights\best.pt
python -m pip install -r requirements-pt.txt
```

引擎加载规则：扫描 `backend/app/ml/weights/`，**`*.onnx` 优先于 `*.pt`**，单个引擎加载失败自动降级尝试下一个；两者皆无时 `/api/detect/image` 返回 50301，注册、登录、历史等功能不受影响。详见 [权重目录说明](backend/app/ml/weights/README.md)。

**构建知识库**（Agent 的 `search_knowledge` 工具依赖，幂等可重复执行）：

```powershell
python scripts/build_kb.py
```

**安装与验证**：

```powershell
python -m pip install -r requirements-dev.txt   # 仅开发/测试需要
python -m pytest tests_light/ -v
uvicorn app.main:app --reload --port 8000
```

启动后：http://127.0.0.1:8000/ 为健康检查，http://127.0.0.1:8000/docs 为交互文档。生产须显式设置 `$env:PV_SECRET_KEY`（`PV_ENV=production` 时缺失将拒绝启动），见部署运维手册第 6 章。

### 2. 前端

```powershell
cd frontend
npm install
npm run dev
```

### 3. 访问

浏览器打开 http://localhost:5173，注册账号 → 登录 → 上传光伏图片开始检测；侧栏「智能问答」进入 Agent 对话。详细步骤、环境变量、排错见 [部署运维手册](docs/deploy_manual.md)。

## API 概览

接口基址 `/api`，成功响应统一为 `{code: 0, message: "success", data}`。令牌读取顺序：自定义头 `X-PV-Token` → 标准 `Authorization: Bearer`；除注册、登录、健康检查外均需鉴权。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | / | 健康检查（不鉴权） |
| POST | /api/auth/register | 用户注册（`PV_ALLOW_REGISTER=false` 时返回 40301） |
| POST | /api/auth/login | 登录，签发 JWT |
| GET | /api/user/profile | 查看个人信息 |
| PUT | /api/user/profile | 修改昵称 / 邮箱 |
| PUT | /api/user/password | 修改密码（旧令牌随之失效） |
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
| GET | /api/diag/auth | 鉴权链路诊断（**仅 `PV_DIAG=1` 时挂载**，返回令牌长度/指纹，不含原文） |
| GET | /api/diag/selftest | 应用令牌链路自检（同上，仅诊断模式挂载） |

完整字段说明与错误码见 [接口文档](docs/api_doc.md)。

## 测试

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest tests_light/ -v
```

- `tests_light/`：轻量回归，无需 torch / ultralytics / 权重文件 / 真实 LLM（Agent 用 mock 流替身），覆盖 API 全链路、上传防护、限流、令牌撤销、算法/部署后处理一致性、Agent SSE 对话与工具循环、会话隔离，以及云端令牌鉴权（`test_cloud_auth.py` / `test_cloud_session.py`），CI 推荐。
- `tests/`：完整算法链路（合成 pt → 导出 ONNX → 真实推理），需额外安装 `torch`、`ultralytics`、`onnx`、`onnxsim`、`onnxruntime`；`concurrency_smoke.py` 为并发冒烟脚本。

历史测试结论见 [测试报告](docs/test_report.md)。

## 环境变量

支持两种配置方式，优先级：**真实环境变量 > `backend/.env` 文件 > 代码缺省值**。本地开发与单机部署推荐复制 `backend/.env.example` 为 `.env` 统一管理（`.env` 已被 `.gitignore` 排除，严禁提交）；systemd / Docker / 云平台注入的环境变量不受影响。生产部署完整步骤见 [部署清单](docs/deploy_checklist.md)。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PV_SECRET_KEY` | 开发缺省值 | JWT 签名密钥；`PV_ENV=production` 时未设置将拒绝启动 |
| `PV_ENV` | `dev` | 运行环境标识，`production` 触发密钥强校验 |
| `PV_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 允许来源，逗号分隔 |
| `PV_TOKEN_EXPIRE_MINUTES` | 1440 | 令牌有效期（分钟） |
| `PV_ALLOW_REGISTER` | `true` | 注册开关，关闭后注册接口返回 40301（公开部署防滥用） |
| `PV_UPLOAD_MAX_MB` / `PV_UPLOAD_MAX_PIXELS` | 10 / 40000000 | 上传大小上限 / 解码前像素总量上限（防解压炸弹） |
| `PV_CONF_THRESHOLD` / `PV_IOU_THRESHOLD` | 0.25 / 0.45 | 置信度阈值 / NMS IoU |
| `PV_IMGSZ` / `PV_ORT_THREADS` | 640 / 4 | 输入边长 / ONNX CPU 线程数 |
| `PV_LOGIN_RATE_LIMIT` / `PV_REGISTER_RATE_LIMIT` / `PV_RATE_LIMIT_WINDOW` | 8 / 30 / 60 | 登录(按 IP+用户名)、注册(按 IP) 限流次数与窗口秒数 |
| `PV_PWD_ITERATIONS` | 600000 | PBKDF2 迭代次数 |
| `PV_LLM_API_KEY`（或 `DASHSCOPE_API_KEY`） | 空 | 阿里云百炼 API Key；未设置时智能体接口返回 50302，其余功能不受影响 |
| `PV_LLM_BASE_URL` | 百炼 OpenAI 兼容端点 | LLM 服务地址 |
| `PV_LLM_MODEL` | kimi-k3.1-pro | 模型 ID |
| `PV_LLM_REASONING_EFFORT` | high | 推理强度（low / high / max，max 更慢更贵） |
| `PV_AGENT_MAX_ROUNDS` | 6 | 单次对话工具调用轮数上限 |
| `PV_AGENT_CHAT_RATE_LIMIT` / `PV_AGENT_HISTORY_LIMIT` | 20 / 20 | 对话限流次数 / 携带历史消息条数 |
| `PV_KB_TOP_K` | 4 | 知识库检索返回条数 |
| `PV_CLOUD_ENDPOINT` | 空 | 云服务端点（取 publicConfig.endpoint）；设置后启用云端令牌校验 |
| `PV_CLOUD_APP_KEY` | 空 | 应用公开凭据（publicConfig.publishableKey）；云端自省请求必需 |
| `PV_CLOUD_AUTH` | `true` | 是否接受云端 access token 登录（与 `PV_CLOUD_ENDPOINT` 同时生效） |
| `PV_CLOUD_AUTH_TTL` / `PV_CLOUD_AUTH_TIMEOUT` | 300 / 6.0 | 云端令牌自省结果缓存秒数 / 自省请求超时 |
| `PV_CLOUD_MODEL` | `kimi-k3-1` | 云端模型目录提示（仅展示用） |
| `PV_DIAG` | `0` | 设为 `1` 时挂载 `/api/diag/*` 鉴权诊断端点，排查完请关闭 |

## 模型效果与当前状态

评估对象：YOLOv8n，`runs/detect/runs/train_n2/weights/best.pt`（early-stop@epoch72），工作点 conf=0.25、IoU=0.5。

| 指标 | 实测 | 验收线 | 结论 |
|---|---|---|---|
| mAP@0.5（工程口径） | 0.8199 | ≥ 0.75 | 达标 |
| mAP@0.5（官方口径，Ultralytics val） | 0.8951 | ≥ 0.75 | 达标 |
| 电损伤召回率@0.25 | 0.7000 | ≥ 0.80 | **未达标** |
| 物理损伤召回率@0.25 | 0.7143（官方口径 0.7954） | ≥ 0.80 | **未达标** |

未达标原因已完成归因：**验证/测试集标签为全幅占位框**（历史脚本 `gen_pseudo_labels.py` 生成），模型学到的是「整幅图纹理 → 类别」而非「局部缺陷 → 类别」，故电损伤热斑、物理损伤裂纹被误判为鸟粪/清洁类。已排除降低阈值、调整 NMS IoU、评估口径、模型状态污染四类假设。修复路径（人工补标局部框 → 数据清洗去重 → 重新训练 → 重出报告）见 [评估诊断报告](docs/model_eval_diag.md) 与 [数据集修复说明](docs/dataset_repair_report.md)。

结论：**mAP 达标，两个局部缺陷类别召回率未达标**；当前测试集指标不能代表模型对真实局部缺陷的检测能力，交付说明中须明示此数据质量限制。

## 项目局限性声明

### 巡检结果使用声明

本系统检测结果仅为 AI 辅助判断，目标置信度不等同于缺陷确诊结论，系统给出的运维建议仅供参考。对电损伤、物理损伤等可能影响电站安全的缺陷，须由专业人员依据现场情况人工复核确认，再安排检修处置。检测结果不构成任何第三方维修、理赔或责任认定的依据。Agent 对话中的回答由大模型生成，同样不构成技术裁决依据。

### 模型局限性

- 训练数据来自 Kaggle "Solar Panel Images" 公开数据集，经人工标注（LabelImg）构建，样本规模、拍摄条件（光照、角度、组件型号）覆盖有限，模型在未见场景上的泛化能力存在边界
- 六类样本分布不均，虽采用类别加权采样缓解，少数类（如积雪、电损伤）的检出率仍低于多数类；电损伤/物理损伤召回率未达 80%（见上节）
- 全幅占位框遗留问题导致定位能力受限，模型对局部小目标的位置精度不足
- 模型以固定输入尺寸（640）推理，极小目标与严重遮挡场景可能漏检
- 「单图 ≤ 200ms」为 ONNX + CPU 路径的设计目标，须在目标硬件用 `export.py --benchmark` 实测后方可声称达成

### 隐私与数据安全说明

- 数据本地化：默认形态下上传图片、标注结果与检测记录仅存储于本机（SQLite 与 `backend/storage/`）；启用云服务后，会话/记录/图片按 `docs/cloud_service.md` 的约定存入云端，账号与图片不再出本机的前提不再成立
- 访问控制：全部业务接口经 JWT 鉴权，历史记录与图像按属主隔离，访问他人资源返回 404/403
- 密码安全：密码经 PBKDF2 加盐哈希存储，数据库不落明文
- 令牌撤销：改密后 `token_version` 递增，已签发令牌立即失效
- 生产部署须显式设置 `PV_SECRET_KEY`，避免使用开发默认密钥；`PV_DIAG` 排查完毕后须关闭

## 文档索引

**需求与方案**

| 文档 | 说明 |
|---|---|
| [需求文档](docs/prd.md) | 需求分析 |
| [技术方案规格](docs/spec.md) | 技术选型与决策记录 |
| [项目规格总纲](docs/project_spec_doc.md) | 全量规格汇总 |
| [架构设计](docs/architecture.md) | 系统架构与数据流 |
| [数据库设计](docs/db_design.md) | 表结构与关系 |
| [项目结构](docs/project_structure.md) | 目录职责划分 |

**数据与模型**

| 文档 | 说明 |
|---|---|
| [数据集说明](docs/dataset_readme.md) | 数据准备流程 |
| [数据集规格](docs/dataset_spec.md) | 标注口径与划分规则 |
| [数据集修复说明](docs/dataset_repair_report.md) | 占位框问题与重标流水线 |
| [人工标注指南](docs/manual_annotation_guide.md) | LabelImg 标注操作（电损伤/物理损伤） |
| [模型训练规格](docs/model_train_spec.md) | 训练 / 评估 / 导出方案 |
| [模型评估报告](docs/model_eval_report.md) | 指标模板与双口径结果 |
| [评估诊断报告](docs/model_eval_diag.md) | 召回率未达标归因与修复路径 |

**接口与前端**

| 文档 | 说明 |
|---|---|
| [后端 API 规格](docs/backend_api_spec.md) | 后端服务规格 |
| [接口文档](docs/api_doc.md) | 接口字段与错误码 |
| [前端规格](docs/frontend_web_spec.md) | Web 界面规格与决策记录 |

**部署与运维**

| 文档 | 说明 |
|---|---|
| [部署运维手册](docs/deploy_manual.md) | 本地部署步骤与排错 |
| [部署规格](docs/deploy_spec.md) | 部署形态与配置约定 |
| [部署清单](docs/deploy_checklist.md) | 上线前逐项核对 |
| [云托管说明](docs/cloud_deploy.md) | 单端口托管与线上更新流程 |
| [云服务接入](docs/cloud_service.md) | 云端登录 / 数据库 / 存储 / 大模型接入方式 |

**测试与验收**

| 文档 | 说明 |
|---|---|
| [测试规格](docs/test_spec.md) | 测试域与用例设计 |
| [测试报告](docs/test_report.md) | 功能 / 性能 / 兼容性实测结论 |
| [任务分解](docs/tasks.md) | 阶段任务 |
| [检查清单](docs/checklist.md) | 逐项验收 |
| [文档交付规格](docs/final_docs_spec.md) | 交付文档清单与规范 |

**教学**

| 文档 | 说明 |
|---|---|
| [AI 协作开发教程](docs/ai_dev_tutorial.md) | 以本项目为蓝本的全链路复盘 |
