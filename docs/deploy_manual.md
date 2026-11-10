# 部署运维手册（Deploy Manual）

| 项目 | 内容 |
|---|---|
| 项目名称 | 光伏面板缺陷检测系统 |
| 文档版本 | V1.0.0 |
| 编写日期 | 2026-09-15 |
| 适用环境 | Windows 本地开发环境（示例命令为 PowerShell） |
| 交付范围 | 本地开发部署，不含云服务器部署 |

## 1 系统概述

系统由三部分构成，本地开发期各自独立运行、通过 HTTP 联调：

| 进程 | 技术 | 端口 | 目录 |
|---|---|---|---|
| 前端 Web | Vite 开发服务器（React） | 5173 | frontend/ |
| 后端 API | Uvicorn（FastAPI） | 8000 | backend/ |
| 推理引擎 | ONNX Runtime / Ultralytics | 进程内 | backend/app/ml/weights/ |
| 数据存储 | SQLite 3 | 文件 | backend/data/ |

请求链路：浏览器 → http://localhost:5173 → Vite 代理 `/api` → http://127.0.0.1:8000 → 推理引擎与 SQLite。开发期前端请求经 Vite proxy 转发，浏览器视角为同源请求，不触发跨域。

## 2 环境准备

| 依赖 | 最低版本 | 验证命令 |
|---|---|---|
| Python | 3.12+ | `python --version` |
| Node.js | 18+（Vite 5 要求） | `node --version` |
| npm | 随 Node 安装 | `npm --version` |

## 3 后端部署

### 3.1 安装依赖

在 `backend/` 目录创建虚拟环境并安装依赖：

```powershell
cd d:\peixunwenjian\2026.9.14-9.28\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # 激活虚拟环境（PowerShell）
pip install -r requirements.txt
```

若 PowerShell 禁止执行脚本（Activate.ps1 报错），改用直接路径调用，或先执行 `Set-ExecutionPolicy -Scope Process Bypass` 再激活：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3.2 配置环境变量（可选）

后端通过系统环境变量读取配置，未设置时使用开发默认值并打印告警日志。仅本地开发可全部省略，直接启动；`PV_SECRET_KEY` 建议显式设置（当前会话内生效）：

```powershell
$env:PV_SECRET_KEY = "your-random-secret"
```

完整环境变量清单见第 6 章。后端不支持读取 `.env` 文件，变量须通过系统/会话环境设置。

### 3.3 部署模型权重

将权重放入 `backend/app/ml/weights/`。引擎按目录内容自动加载：存在任意 `*.onnx` 时优先加载 ONNX 引擎，否则回退加载 `*.pt`（ultralytics，需额外安装 `requirements-pt.txt`）；`model_version` 取文件名（不含扩展名）。

权重**不随版本库分发**，须由算法阶段产出后手工放置：

```powershell
# 方案A：导出 ONNX（在 algorithm/ 目录，需完整算法环境）
cd ..\algorithm
python export.py --skip-eval --benchmark        # 自动选取 runs/ 下最新 best.pt，产出 models/best.onnx
cd ..\backend
Copy-Item ..\algorithm\models\best.onnx .\app\ml\weights\

# 方案B：直接使用训练产出的 pt 权重（回退路径）
Copy-Item ..\algorithm\runs\detect\train_final-2\weights\best.pt .\app\ml\weights\best.pt
```

> **现状说明**：当前交付包内 `weights/` 只有一份 `best.pt`（约 6 MB），与 `algorithm/runs/detect/train_final-2/weights/best.pt`（约 89 MB，yolov8s 训练产出）并非同一文件。上线前须确认部署权重与 `docs/model_eval_report.md` 所评估的权重一致，并重新登记 `model_version`。
>
> 「单图推理 ≤ 200ms」是 ONNX 路径的目标值，仅在完成方案A并在目标硬件用 `export.py --benchmark` 实测后方可声称达成；PT 回退路径的延迟随 CPU 性能变化。

权重目录为空时系统仍可启动，但检测接口返回 50301（"模型服务未就绪"），其余接口不受影响。

### 3.4 启动服务

在 `backend/` 目录（虚拟环境已激活）执行：

```powershell
uvicorn app.main:app --reload --port 8000
```

启动日志中看到以下输出即成功：

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

未部署权重时额外出现告警：`未找到可用模型权重（...\ml\weights），检测接口将返回50301`。

### 3.5 验证

| 检查项 | 方法 | 预期 |
|---|---|---|
| 健康检查 | 浏览器访问 http://127.0.0.1:8000/ | 返回 `{app, version, docs, model_version}`，部署权重后 `model_version` 非 null |
| 交互文档 | 访问 http://127.0.0.1:8000/docs | Swagger UI 展示全部接口 |
| 冒烟测试 | `python -m pytest tests` | 18 个用例全部通过 |

## 4 前端部署

### 4.1 安装依赖

在 `frontend/` 目录执行：

```powershell
cd d:\peixunwenjian\2026.9.14-9.28\frontend
npm install
```

### 4.2 启动开发服务器

```powershell
npm run dev
```

启动成功后访问 http://localhost:5173。开发服务器自动将 `/api` 请求代理到 `http://127.0.0.1:8000`（配置见 `frontend/vite.config.ts` 的 `server.proxy`），无需额外配置即可与后端联调。

### 4.3 生产构建（可选）

```powershell
npm run build        # tsc --noEmit 类型检查 + vite build，产物输出至 dist/
npm run preview      # 本地预览构建产物（默认端口 4173）
```

构建产物 `frontend/dist/` 为纯静态文件，本地预览时 `/api` 不再有开发代理，须通过 `VITE_API_BASE` 指向后端地址（见第 6 章）或由同域反向代理接管。

### 4.4 配置后端地址（可选）

前端默认以 `/api` 作为请求基址（走开发代理）。如需直连后端，在 `frontend/` 下新建 `.env.local`：

```
VITE_API_BASE=http://127.0.0.1:8000/api
```

修改后需重启 `npm run dev`。直连模式跨域策略见第 5.3 节。

## 5 全链路联调验证

按顺序执行以下验收步骤，全部通过即视为本地全链路跑通。

| 步骤 | 操作 | 预期结果 |
|---|---|---|
| 1 | 启动后端（3.4），部署权重（3.3） | 健康检查 `model_version` 非 null |
| 2 | 启动前端（4.2） | http://localhost:5173 打开登录页 |
| 3 | 注册新用户 | 注册成功，自动进入登录流程 |
| 4 | 登录 | 登录成功，进入检测主页 |
| 5 | 上传光伏面板图片（jpg/jpeg/png/bmp，≤10MB） | 页面展示标注结果图、目标列表、置信度与运维建议 |
| 6 | 进入历史记录页 | 展示刚完成的检测记录（含缩略图、缺陷汇总、推理耗时） |
| 7 | 查看记录详情 | 展示完整目标列表与原图 |
| 8 | 导出 CSV | 下载 `detect_records_YYYYMMDD.csv`，Excel 打开中文正常 |

### 5.1 接口联调注意事项

- **统一响应格式**：所有 `/api/*` 成功 JSON 响应包装为 `{code: 0, message: "success", data: ...}`；业务错误返回对应 `code` 与 `message`。健康检查 `/`、CSV 导出、图像文件流不参与包装。
- **鉴权头**：登录后获取 `access_token`，后续请求置于 `Authorization: Bearer <token>`。前端 axios 拦截器已自动注入。
- **登录过期**：接口返回 `code: 40101` 时前端自动清除本地 token 并跳转登录页。
- **鉴权图片访问**：`/api/files/*` 返回图像文件流，须以 blob + objectURL 方式请求（直接 `<img src>` 无法携带鉴权头），前端 `getBlob` 已封装。
- **路由注册顺序**：`/record/export` 必须先于 `/record/{record_id}` 注册，否则 `export` 会被解析为记录 ID（当前代码已正确排序，改动路由时注意）。
- **模型未就绪**：权重缺失时仅检测接口返回 50301，登录、历史等接口正常，便于联调排障。

### 5.2 跨域配置说明

| 场景 | 跨域行为 | 说明 |
|---|---|---|
| 开发期（推荐） | 无跨域 | 前端经 Vite proxy 转发 `/api` 到 127.0.0.1:8000，浏览器同源 |
| 直连后端 | 由后端 CORS 放行 | 后端默认 `allow_origins=["*"]`、`allow_credentials=False`，任何来源可访问 |
| 收紧 CORS | 需改代码 | 修改 `backend/app/core/config.py` 中 `cors_origins`（当前无环境变量覆盖项） |

鉴权依赖 `Authorization` 请求头而非 Cookie，与 `allow_credentials` 无关，收紧 CORS 白名单不影响登录鉴权。

## 6 环境变量说明

### 6.1 后端（backend/app/core/config.py）

| 变量 | 默认值 | 说明 |
|---|---|---|
| PV_SECRET_KEY | pv-dev-secret-key-please-override | JWT 签名密钥。未设置时启动打印告警，仅限本地开发；正式使用须设为随机字符串 |
| PV_UPLOAD_MAX_MB | 10 | 上传图片大小上限（MB） |
| PV_IMGSZ | 640 | 模型输入边长 |
| PV_ORT_THREADS | 4 | ONNX Runtime CPU 推理线程数 |
| PV_PWD_ITERATIONS | 600000 | 密码 PBKDF2 哈希迭代次数 |
| PV_TOKEN_EXPIRE_MINUTES | 1440 | JWT 有效期（分钟），默认 24 小时 |

### 6.2 前端（frontend/.env.local，可选）

| 变量 | 默认值 | 说明 |
|---|---|---|
| VITE_API_BASE | /api | API 请求基址。默认走 Vite 开发代理；直连后端时设为 `http://127.0.0.1:8000/api` |

## 7 数据与文件说明

| 路径 | 内容 | 备注 |
|---|---|---|
| backend/data/pv_defect.db | SQLite 数据库（user、detect_record 表） | 首次启动自动创建（幂等） |
| backend/storage/uploads/YYYYMMDD/ | 上传原图 | 按检测日期归档，文件流接口需鉴权 |
| backend/storage/results/YYYYMMDD/ | 标注结果图（JPEG） | 同上 |
| backend/app/ml/weights/ | 部署模型权重（best.onnx / best.pt） | 引擎按目录扫描自动加载 |
| backend/tests/ | pytest 冒烟测试 | 18 用例，合成权重全链路 |
| backend/data、storage/uploads、storage/results | 运行时数据 | 已被 .gitignore 排除，不入版本库 |

运行日志输出至控制台（logging INFO 级别），无独立日志文件。

## 8 常见问题排错

| 症状 | 可能原因 | 处理 |
|---|---|---|
| PowerShell 提示"禁止运行脚本" | 执行策略限制 | 用 `npm.cmd` 代替 `npm`；虚拟环境直接用 `.venv\Scripts\python.exe`；或执行 `Set-ExecutionPolicy -Scope Process Bypass` |
| 检测接口返回 50301 | 权重目录为空或加载失败 | 部署权重（3.3）后重启后端；检查 onnxruntime 是否安装、onnx 文件是否损坏 |
| 前端提示"网络连接失败，请检查后端服务" | 后端未启动或端口不一致 | 确认 uvicorn 运行在 8000 端口；代理目标与 vite.config.ts 一致 |
| 访问 5173 端口被占用 | 端口冲突 | 修改 vite.config.ts 的 `server.port`，或释放占用进程 |
| 上传被拒绝（格式/大小） | 超出校验 | 仅支持 jpg/jpeg/png/bmp，≤10MB（PV_UPLOAD_MAX_MB 可调） |
| 登录后请求返回 40101 | token 过期 | 重新登录；有效期可用 PV_TOKEN_EXPIRE_MINUTES 调整 |
| 浏览器控制台 CORS 报错 | 直连后端且后端被改动 | 开发期走 Vite 代理；确认后端 cors_origins 配置 |
| npm install 缓慢或失败 | 网络原因 | 设置镜像：`npm config set registry https://registry.npmmirror.com` |
| pip 安装缓慢或失败 | 网络原因 | 使用镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| CSV 用 Excel 打开中文乱码 | 编码问题 | 后端已输出 utf-8-sig，重新导出即可；旧文件请用"数据-自文件导入" |
| npm run build 类型报错 | TypeScript 类型不符 | 按报错修正 `frontend/src` 代码后重试 |

## 9 系统重置

停止前后端进程后，删除运行时数据即可恢复初始状态，下次启动自动重建：

```powershell
Remove-Item .\backend\data\pv_defect.db
Remove-Item .\backend\storage\uploads\* -Recurse
Remove-Item .\backend\storage\results\* -Recurse
```

如需彻底重新部署，可同时删除 `backend/.venv` 与 `frontend/node_modules` 后按第 3、4 章重装。
