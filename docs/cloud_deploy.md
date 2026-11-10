# 云托管部署说明（单端口形态）

本项目已发布为公网可访问的在线应用，采用「FastAPI 单端口同时托管前端」的形态，
不依赖 Nginx、不依赖外部数据库（SQLite 随项目一起上传）。

## 1 线上地址

| 项目 | 值 |
| --- | --- |
| 应用名称 | 光伏面板缺陷检测 Agent |
| 访问链接 | 由「设置—数据管理—应用」中的应用卡片复制 |
| 部署形态 | http-service（Python + uvicorn） |
| 健康检查 | `/health` |
| 接口文档 | `/docs` |

> 分享链接必须带 `?sharecode=...` 参数，首次访问后浏览器会获得访问凭据（Cookie）；
> 直接用域名根路径访问会被网关判定为「链接不完整」。

## 2 部署目录结构

线上运行的目录是源码的**运行子集**，不含训练脚本与前端源码：

```
pv_deploy/
├─ serve.py             # 启动入口：读取 PORT 环境变量后启动 uvicorn
├─ requirements.txt     # 运行期最小依赖（ONNX 推理路径）
├─ app/                 # FastAPI 应用（含 app/ml/weights/best.onnx）
├─ webapp_dist/         # 前端构建产物（由 frontend 构建后复制）
├─ scripts/build_kb.py  # 知识库重建脚本
├─ data/pv_defect.db    # SQLite（用户 / 检测记录 / Agent 会话 / 知识库分块）
├─ storage/             # 上传原图与标注结果图
└─ .env                 # 运行期环境变量（含密钥，禁止提交到仓库）
```

## 3 启动方式

平台只暴露一个 HTTP 端口，并通过 `PORT` 环境变量注入端口号。
启动命令不要写 `--port $PORT`（部分执行环境不做变量展开，会得到空参数而启动失败），
统一使用：

```bash
python serve.py
```

`serve.py` 内部完成三件事：注入项目根到 `sys.path`、读取 `PORT`、以 `0.0.0.0` 绑定启动 uvicorn。

本地复现线上环境：

```bash
cd pv_deploy
pip install -r requirements.txt
PORT=8000 python serve.py
# 打开 http://127.0.0.1:8000/health
```

## 4 更新线上内容

代码或前端有改动时，按顺序执行：

1. 前端：`cd frontend && npm run build`，把 `dist/` 覆盖到 `pv_deploy/webapp_dist/`；
2. 后端：把 `backend/app/` 覆盖到 `pv_deploy/app/`；
3. 数据库结构有变更时同步 `pv_deploy/data/pv_defect.db`（或迁移脚本）；
4. 重新发布（发布会覆盖同一个链接，链接本身不变）。

## 5 部署态的行为差异

| 配置 | 线上值 | 说明 |
| --- | --- | --- |
| `PV_ENV` | `production` | 生产模式，弱密钥启动直接拒绝 |
| `PV_ALLOW_REGISTER` | `false` | 关闭自助注册，仅库中已有账号可登录 |
| 前端托管 | 启用 | `/` 返回 SPA，`/assets` 为静态资源，其余路径回退 `index.html` |
| 健康检查 | `/health` | 根路径已被前端占用 |

需要开放注册做演示时，把 `PV_ALLOW_REGISTER` 改为 `true` 并重新发布；
开放后任何拿到链接的人都能注册并消耗大模型调用额度，演示结束建议改回。

## 6 注意事项

- `.env` 内含 `PV_SECRET_KEY` 与大模型 API Key，只存在于部署目录，不要纳入版本库；
- SQLite 采用 WAL 模式，`data/` 目录下可能出现 `-wal` / `-shm` 文件，属正常现象；
- 单实例部署下 Agent 会话与检测记录都落在同一个 SQLite 文件，扩容多实例前需先迁移到集中式数据库。
