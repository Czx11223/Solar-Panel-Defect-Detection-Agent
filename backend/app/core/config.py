"""应用配置：集中管理全部可调参数，支持环境变量覆盖。

运行环境：Python 3.12+，FastAPI应用内引用。
关键设计：
- 全部可调参数集中在config模块，环境变量优先级最高，缺省值为开发默认；
- 生产部署须通过环境变量设置 PV_SECRET_KEY（缺省密钥仅限开发，启动时打印告警）；
- 路径类配置基于backend/目录自动定位，无需手工修改。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("pv.config")

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"                             # SQLite数据库文件目录
STORAGE_DIR = BASE_DIR / "storage"                       # 图像存储根目录
UPLOAD_DIR = STORAGE_DIR / "uploads"                     # 原图存储目录
RESULT_DIR = STORAGE_DIR / "results"                     # 标注结果图目录
MODEL_DIR = BASE_DIR / "app" / "ml" / "weights"          # 部署模型权重目录

# ---- .env 文件加载（必须在任何 os.getenv 之前）----
# 优先级：真实环境变量 > backend/.env > 代码缺省值。
# .env 仅用于本地开发与单机部署；systemd/Docker/云平台注入的环境变量天然优先。
try:
    from dotenv import load_dotenv

    _env_file = BASE_DIR / ".env"
    if _env_file.is_file():
        load_dotenv(_env_file, override=False)
        logger.info("已加载配置文件 %s", _env_file)
except ImportError:  # python-dotenv 为可选依赖，缺失时仅用真实环境变量
    pass

# 六类固定顺序：与algorithm侧data.yaml一致（0清洁/1积灰/2鸟粪/3电损伤/4物理损伤/5积雪）
CLASS_NAMES_ZH = ["清洁", "积灰", "鸟粪", "电损伤", "物理损伤", "积雪"]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    # ---- 服务 ----
    app_name: str = "光伏面板缺陷检测系统"
    version: str = "1.0.0"

    # ---- 上传校验（D2：上限10MB；格式jpg/jpeg/png/bmp）----
    upload_max_mb: int = field(default_factory=lambda: _env_int("PV_UPLOAD_MAX_MB", 10))
    # 解码前校验像素总量，防「小文件→超大位图」的解压炸弹（40MP ≈ 120MB RGB）
    upload_max_pixels: int = field(default_factory=lambda: _env_int("PV_UPLOAD_MAX_PIXELS", 40_000_000))
    allowed_extensions: tuple = (".jpg", ".jpeg", ".png", ".bmp")
    # 文件魔数（前8字节）白名单：JPEG(FFD8FF)、PNG(89504E47)、BMP(424D)
    magic_prefixes: tuple = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"BM")

    # ---- 推理参数（均可由环境变量覆盖）----
    imgsz: int = field(default_factory=lambda: _env_int("PV_IMGSZ", 640))
    conf_threshold: float = field(default_factory=lambda: _env_float("PV_CONF_THRESHOLD", 0.25))
    iou_threshold: float = field(default_factory=lambda: _env_float("PV_IOU_THRESHOLD", 0.45))
    ort_threads: int = field(default_factory=lambda: _env_int("PV_ORT_THREADS", 4))

    # ---- 安全（D26密码哈希 / D27 JWT）----
    password_iterations: int = field(default_factory=lambda: _env_int("PV_PWD_ITERATIONS", 600_000))
    secret_key: str = os.getenv("PV_SECRET_KEY", "pv-dev-secret-key-please-override")
    token_expire_minutes: int = field(default_factory=lambda: _env_int("PV_TOKEN_EXPIRE_MINUTES", 1440))
    # 登录按 (IP, 用户名) 限流，注册按 IP 限流；窗口内超过阈值返回 42901
    login_rate_limit: int = field(default_factory=lambda: _env_int("PV_LOGIN_RATE_LIMIT", 8))
    register_rate_limit: int = field(default_factory=lambda: _env_int("PV_REGISTER_RATE_LIMIT", 30))
    rate_limit_window: int = field(default_factory=lambda: _env_int("PV_RATE_LIMIT_WINDOW", 60))
    # 公开部署防滥用：注册开关（false 时注册接口返回 40301）
    allow_register: bool = field(default_factory=lambda: os.getenv(
        "PV_ALLOW_REGISTER", "true").strip().lower() not in ("0", "false", "no", "off"))

    # ---- LLM Agent（阿里云百炼 OpenAI 兼容模式）----
    # 密钥优先级：PV_LLM_API_KEY > DASHSCOPE_API_KEY；均未设置时 Agent 接口返回 50302
    llm_api_key: str = os.getenv("PV_LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
    llm_base_url: str = os.getenv("PV_LLM_BASE_URL",
                                   "https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm_model: str = os.getenv("PV_LLM_MODEL", "kimi-k3.1-pro")
    # K3.1 Pro 始终思考；推理强度 low/high/max，max 慢且贵，Agent 场景默认 high
    llm_reasoning_effort: str = os.getenv("PV_LLM_REASONING_EFFORT", "high")
    agent_max_rounds: int = field(default_factory=lambda: _env_int("PV_AGENT_MAX_ROUNDS", 6))
    agent_chat_rate_limit: int = field(default_factory=lambda: _env_int("PV_AGENT_CHAT_RATE_LIMIT", 20))
    agent_history_limit: int = field(default_factory=lambda: _env_int("PV_AGENT_HISTORY_LIMIT", 20))
    kb_top_k: int = field(default_factory=lambda: _env_int("PV_KB_TOP_K", 4))

    # ---- 云服务（WorkBuddy Cloud Service）----
    # 前端用云端账号登录后，后端用 /user/me 校验 access token（不持有签密密钥）。
    # PV_CLOUD_ENDPOINT 取 cloud service 返回的 publicConfig.endpoint（与应用同域）。
    cloud_endpoint: str = os.getenv("PV_CLOUD_ENDPOINT", "").rstrip("/")
    # 应用公开凭据（publicConfig.publishableKey，publishable 可随代码/配置分发）：
    # 云端每个数据面请求都要求 x-wb-webapp-access-key 头识别应用，缺失时报 invalid_client。
    cloud_app_key: str = os.getenv("PV_CLOUD_APP_KEY", "").strip()
    cloud_auth_enabled: bool = field(default_factory=lambda: os.getenv(
        "PV_CLOUD_AUTH", "true").strip().lower() not in ("0", "false", "no", "off"))
    cloud_auth_ttl: int = field(default_factory=lambda: _env_int("PV_CLOUD_AUTH_TTL", 300))
    cloud_auth_timeout: float = field(default_factory=lambda: _env_float("PV_CLOUD_AUTH_TIMEOUT", 6.0))
    # 云端大模型目录（前端 models.list 失败时用于提示），仅作展示
    cloud_model_hint: str = os.getenv("PV_CLOUD_MODEL", "kimi-k3-1")
    # 鉴权链路诊断端点（/api/diag/auth）：默认关闭，排查线上问题时临时开启
    diag_enabled: bool = field(default_factory=lambda: os.getenv(
        "PV_DIAG", "0").strip().lower() in ("1", "true", "yes", "on"))

    # ---- CORS：默认只允许本地 Vite 开发源，生产用 PV_CORS_ORIGINS 逗号分隔覆盖 ----
    cors_origins: list = field(default_factory=lambda: _env_list(
        "PV_CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]))

    def __post_init__(self) -> None:
        if os.getenv("PV_SECRET_KEY") is None:
            if os.getenv("PV_ENV", "dev").lower() in ("prod", "production"):
                raise RuntimeError("生产环境必须显式设置 PV_SECRET_KEY")
            logger.warning("未设置环境变量 PV_SECRET_KEY，使用开发默认密钥（仅限本地开发）")


settings = Settings()
