# 系统集成与部署规格（Deploy Spec）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 编写角色 | 全栈运维开发工程师 |
| 编制依据 | 《光伏面板缺陷检测系统项目任务书V1.0.0》任务8（系统集成与联调）、任务10（文档编写） |
| 交付范围 | 本地开发部署（不含云服务器部署） |

## 1 任务背景与范围

已完成算法脚本（algorithm/）、FastAPI 后端（backend/）、React 前端（frontend/）三部分代码。本阶段完成系统集成确认与部署文档输出，目标是本地可完整跑通全链路：**用户登录 → 上传光伏图片 → AI推理检测 → 查看结果 → 查看历史记录**。

交付物清单：

| 编号 | 交付物 | 说明 |
|---|---|---|
| T1 | 项目目录梳理 | 确认 algorithm/backend/frontend/docs 四部分代码位于正确目录，输出核查结论 |
| T2 | docs/deploy_manual.md | 部署运维手册：本地部署步骤、依赖安装、启动命令、环境变量说明、常见问题排错 |
| T3 | README.md | 项目简介、技术栈、快速启动步骤、项目局限性声明 |
| T4 | 联调与跨域说明 | 写入 deploy_manual.md 与 README.md，含前后端接口联调注意事项、跨域配置说明 |

约束：仅输出本地开发部署文档，不涉及云服务器；先出本 spec 清单，用户确认后输出全部文档。

## 2 T1 目录梳理核查结论（已核实）

核查时间 2026-09-15，根目录结构：

```text
2026.9.14-9.28/                  # 项目根目录
├── algorithm/                   # 算法：训练、评估、ONNX导出
│   ├── train.py / eval.py / export.py
│   ├── scripts/                 # pv_classes / organize_dataset / convert_labels / split_dataset / augment
│   ├── runs/                    # 运行时产物（detect/），不入版本库
│   └── requirements.txt
├── backend/                     # FastAPI 后端
│   ├── app/                     # main / api / core / db / repositories / schemas / services / ml
│   ├── data/                    # SQLite 数据库（pv_defect.db，启动自动建库）
│   ├── storage/                 # uploads/（原图） results/（标注结果图）
│   ├── tests/                   # pytest 冒烟测试
│   └── requirements.txt
├── docs/                        # 14 份设计/规格/接口文档
├── frontend/                    # React 前端
│   ├── src/                     # api / components / constants / hooks / pages / types / utils
│   ├── dist/ node_modules/      # 构建产物与依赖（不入版本库）
│   └── package.json / vite.config.ts / tailwind.config.ts ...
└── README.md                    # ← 缺失，T3 产出
```

核查结论：

| 检查项 | 结果 | 说明 |
|---|---|---|
| 四大部分目录职责 | 通过 | 无越界文件，与 docs/project_structure.md 一致 |
| 算法产物位置 | 注意 | algorithm/models/ 由 export.py 产出，需人工拷贝至 backend/app/ml/weights/ |
| 部署权重目录 | 警告 | backend/app/ml/weights/ 当前为空，检测接口将返回 50301，须部署 best.onnx（或 best.pt） |
| 前端入口配置 | 通过 | vite 代理 /api → 127.0.0.1:8000，前后端联调路径正确 |
| 根目录 README | 缺失 | T3 创建 |

## 3 T2 docs/deploy_manual.md 章节大纲

| 章节 | 内容要点 |
|---|---|
| 1 文档信息 | 项目、版本、日期、适用环境 |
| 2 系统概述 | 运行架构（vite ↔ uvicorn ↔ SQLite/ONNX）、端口约定（5173/8000） |
| 3 环境准备 | Python 3.12+、Node.js 18+ 版本要求与验证命令 |
| 4 后端部署 | venv 创建 → pip 安装 → 环境变量 → 部署模型权重 → uvicorn 启动 → 健康检查验证 |
| 5 前端部署 | npm install → npm run dev → 生产构建（build + preview） |
| 6 全链路联调验证 | 注册→登录→上传检测→历史→导出 五步验收清单 |
| 7 环境变量说明 | 表格：PV_SECRET_KEY / PV_UPLOAD_MAX_MB / PV_IMGSZ / PV_ORT_THREADS / PV_PWD_ITERATIONS / PV_TOKEN_EXPIRE_MINUTES / VITE_API_BASE |
| 8 数据与文件说明 | SQLite、storage/ 目录、weights 部署位置、运行日志 |
| 9 常见问题排错 | 端口占用、50301 模型未就绪、CORS、PowerShell 执行策略、Node 版本、依赖安装失败、40101 登录过期、上传失败等 |
| 10 系统重置 | 删库、清空 storage/、恢复默认 |

## 4 T3 README.md 章节大纲

| 章节 | 内容要点 |
|---|---|
| 1 项目简介 | 一句话定位 + 全链路描述 |
| 2 功能特性 | 六类缺陷检测、JWT 鉴权、历史记录、CSV 导出、运维建议 |
| 3 技术栈 | 前端/后端/算法 三栏表格 |
| 4 目录结构 | 简版目录树（与第2节一致） |
| 5 快速启动 | 5 步：环境 → 后端依赖 → 权重部署 → 前端依赖 → 访问 |
| 6 API 概览 | 接口速查（链接 docs/api_doc.md） |
| 7 项目局限性声明 | 7.1 巡检结果使用声明；7.2 模型局限性；7.3 隐私与数据安全说明 |
| 8 文档索引 | docs/ 目录各文档链接 |

## 5 T4 接口联调与跨域说明要点

写入 deploy_manual.md 第6章与 README 相关章节：

| 主题 | 要点 |
|---|---|
| 开发期跨域方案 | 前端走 Vite proxy（/api → http://127.0.0.1:8000，changeOrigin），浏览器同源、无跨域问题 |
| 后端 CORS 兜底 | config.py 默认 allow_origins=["*"]、allow_credentials=False；鉴权走 Authorization 头而非 Cookie，收紧时仅需配置来源白名单 |
| 统一响应格式 | /api/* 成功响应包装为 {code:0, message:"success", data}；CSV 导出与图像文件流（blob）不包装 |
| 鉴权与过期 | 前端请求头注入 Bearer token；40101 触发清 token 并跳转登录页 |
| 鉴权图片访问 | /api/files/* 需 blob + objectURL 方式请求以携带鉴权头 |
| 模型未就绪 | 权重缺失时检测接口返回 50301，其余接口正常 |

## 6 决策点（需用户确认）

| 编号 | 决策点 | 建议 |
|---|---|---|
| D1 | 环境变量配置方式 | 仅文档说明（推荐，避免新增任务书外文件）或附带 .env.example 模板 |
| D2 | README 接口概览形式 | 精简速查表（推荐）或仅链接 api_doc.md |
| D3 | README 局限性声明细节 | 含 7.1 巡检结果使用声明（引用任务书语义）、7.2 模型局限、7.3 隐私保护，均为必含项 |

## 7 任务清单（确认后执行）

- [ ] T1 目录梳理结论写入 deploy_manual.md 附录或系统概述
- [ ] T2 创建 docs/deploy_manual.md（按第3节大纲）
- [ ] T3 创建根目录 README.md（按第4节大纲）
- [ ] T4 联调与跨域说明并入 T2/T3 对应章节
- [ ] 全文核对命令、路径、环境变量与实际代码一致

## 8 验收标准

1. 按 deploy_manual.md 步骤操作，本地可启动前后端并完成全链路（权重部署后）。
2. README.md 含任务书要求的巡检结果使用声明、模型局限性、隐私保护说明。
3. 所有命令、端口、环境变量、文件路径与实际代码一致。
