# 生产部署清单（通用版）

适用：Linux 云服务器（systemd + Nginx）。Docker / 云平台部署时按对应方式注入环境变量，其余步骤相同。
开发调试与单机部署的配置统一走 `backend/.env`（模板见 `.env.example`）；systemd / Docker 注入的环境变量优先级更高。

## 1. 前置条件

- 服务器：Python ≥ 3.12、Node.js ≥ 20（仅构建前端时需要）、Nginx
- 阿里云百炼 API Key（Agent 功能需要；不启用可跳过）
- 模型权重：`backend/app/ml/weights/` 下放置 `best.onnx`（优先）或 `best.pt`（回退，需另装 `requirements-pt.txt`）

## 2. 后端部署

```bash
# 目录规划示例：/opt/pv/backend
cd /opt/pv/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # PT 回退另装 requirements-pt.txt

# 配置：模板 → .env，填 PV_SECRET_KEY 与 DASHSCOPE_API_KEY
cp .env.example .env && chmod 600 .env && vim .env
```

构建知识库（Agent 知识检索用，一次即可；语料更新后重跑）：

```bash
.venv/bin/python scripts/build_kb.py
```

systemd 服务 `/etc/systemd/system/pv-backend.service`：

```ini
[Unit]
Description=PV Defect Detection Backend
After=network.target

[Service]
WorkingDirectory=/opt/pv/backend
ExecStart=/opt/pv/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
EnvironmentFile=-/opt/pv/backend/.env
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

> `EnvironmentFile=-` 前的 `-` 表示文件可缺省；`.env` 里的变量与 unit 内 `Environment=` 均可注入，真实环境变量优先于 `load_dotenv`。

```bash
systemctl daemon-reload && systemctl enable --now pv-backend
```

## 3. 前端部署

```bash
# 本地或 CI 构建后上传 dist/，或在服务器构建
cd frontend
# 生产 API 地址：同域部署时设置 VITE_API_BASE=/api 即可走 Nginx 反代
VITE_API_BASE=/api npm run build
# 产物 frontend/dist/ → 服务器 /opt/pv/frontend-dist/
```

Nginx 站点配置要点：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    root /opt/pv/frontend-dist;
    location / { try_files $uri $uri/ /index.html; }   # SPA 路由回退

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        # Agent SSE 必需：关闭缓冲、延长读超时
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
    location /api/agent/chat {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

## 4. 上线前核查（逐项打勾）

- [ ] `PV_ENV=production` 且 `PV_SECRET_KEY` 已设置（缺失将拒绝启动，属预期保护）
- [ ] `PV_CORS_ORIGINS` 收敛到真实前端域名（默认只放行 localhost:5173）
- [ ] `.env` 权限 600、不在 git 仓库内（`.gitignore` 已排除，`git status` 确认无 `.env`）
- [ ] `weights/` 已放置模型文件；`GET /` 健康检查 `model_version` 非空
- [ ] 知识库已构建（`kb_chunk` 表非空，Agent 才能答项目知识类问题）
- [ ] SQLite 数据目录（`backend/data/`）与图像目录（`backend/storage/`）已纳入备份计划
- [ ] HTTPS 已启用（JWT 明文传输依赖 TLS 保护）

## 5. 部署后验证

```bash
curl http://127.0.0.1:8000/                                   # 健康检查
curl -X POST https://your-domain.com/api/auth/register ...    # 注册/登录链路
# 登录后：GET /api/agent/status 应返回 llm_ready=true（配置了 DASHSCOPE_API_KEY 时）
# 前端：上传图片检测 → 历史查询 → /chat 页对话（触发 detect_image 工具）
```

常见问题：Agent 回答不调用工具 → 检查 `PV_LLM_REASONING_EFFORT`（建议 high）；SSE 卡住 → 确认 Nginx `proxy_buffering off`；50301 → weights 目录无模型；50302 → 未配置百炼 Key。
