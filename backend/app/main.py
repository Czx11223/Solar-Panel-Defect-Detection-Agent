"""应用入口：路由注册、CORS、全局异常处理、统一响应包装、生命周期事件。

生命周期（lifespan）：
1. init_db()：幂等建库建表（user、detect_record）；
2. load_engine()：加载推理引擎（ONNX优先/pt回退），存入 app.state.engine，
   模型不可用时检测接口返回50301，其余接口不受影响。

统一响应包装（中间件）：所有 /api/* 的成功JSON响应包装为
{code: 0, message: "success", data: <payload>}；
异常处理器已输出 {code, message, data}，中间件不再重复包装；
健康检查 /、CSV导出、图像文件流不经包装。

运行：uvicorn app.main:app --reload --port 8000
交互文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .api import agent, auth, detect, record, user
from .core.config import BASE_DIR, MODEL_DIR, settings
from .core.errors import (CODE_INTERNAL, CODE_NOT_FOUND, CODE_OK, CODE_PARAM,
                          BizError, biz_error)
from .db.init_db import init_db
from .services.inference import load_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("pv.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.engine = load_engine(MODEL_DIR)
    if app.state.engine is None:
        logger.warning("未找到可用模型权重（%s），检测接口将返回50301", MODEL_DIR)
    else:
        logger.info("推理引擎就绪：%s（%s）",
                    app.state.engine.model_version, type(app.state.engine).__name__)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="光伏面板六类缺陷（清洁/积灰/鸟粪/电损伤/物理损伤/积雪）检测系统后端。\n\n"
                    "免责声明：检测结果为AI辅助判断，置信度不等于缺陷确诊，运维建议供参考，"
                    "重大缺陷须人工复核。",
        lifespan=lifespan,
    )

    # CORS（开发默认放开，部署期通过环境变量收紧）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 路由注册（统一 /api 前缀）
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(user.router, prefix="/api/user")
    app.include_router(detect.router, prefix="/api")
    app.include_router(record.router, prefix="/api")
    app.include_router(agent.router, prefix="/api/agent")
    if settings.diag_enabled:
        from .api import diag
        app.include_router(diag.router, prefix="/api/diag")

    # ---- 统一响应包装：/api/* 成功JSON → {code, message, data} ----
    def _copy_headers(headers) -> dict:
        """复制响应头并剔除由body决定的首部（长度/编码），交给新响应重算。"""
        return {k: v for k, v in headers.items()
                if k.lower() not in ("content-length", "transfer-encoding")}

    @app.middleware("http")
    async def wrap_api_response(request: Request, call_next):
        # 仅拦截 /api/* 接口；健康检查、OpenAPI等路径原样透传
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        # 异常响应（已含code/message/data）与文件流（CSV/图像）不包装
        if response.status_code >= 400 or "application/json" not in ct:
            return response

        # Starlette 1.6 中call_next返回流式响应，需消费body_iterator后重建
        raw = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(raw)
        except ValueError:
            return Response(content=raw, status_code=response.status_code,
                            headers=_copy_headers(response.headers))
        if isinstance(payload, dict) and "code" not in payload:
            return JSONResponse(
                status_code=response.status_code,
                content={"code": CODE_OK, "message": "success", "data": payload},
                headers=_copy_headers(response.headers),
            )
        return Response(content=raw, status_code=response.status_code,
                        headers=_copy_headers(response.headers))

    # ---- 全局异常处理：统一 {code, message, data} 响应 ----
    @app.exception_handler(BizError)
    async def _biz_error_handler(_req: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # 参数校验失败：拼接首个错误信息，映射为40001
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x not in ("body", "query", "path"))
        msg = first.get("msg", "参数校验失败")
        return JSONResponse(
            status_code=400,
            content={"code": CODE_PARAM, "message": f"{loc}: {msg}" if loc else msg,
                     "data": None},
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_req: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code * 100, "message": str(exc.detail), "data": None},
        )

    @app.exception_handler(Exception)
    async def _unexpected_handler(_req: Request, exc: Exception) -> JSONResponse:
        logger.exception("未预期异常：%s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": CODE_INTERNAL, "message": "服务器内部错误，请稍后重试",
                     "data": None},
        )

    # ---- 前端静态托管（单端口部署形态；webapp_dist 由前端构建产物复制而来）----
    # 本地开发无此目录时自动跳过，前后端分离跑法不受影响。
    # 启用时健康检查让位于前端页面：/ 返回 index.html，健康检查在 /health。
    webapp_dist = BASE_DIR / "webapp_dist"
    spa_enabled = webapp_dist.is_dir() and (webapp_dist / "index.html").is_file()

    @app.get("/health" if spa_enabled else "/", summary="服务健康检查", tags=["system"])
    def health() -> dict:
        engine = getattr(app.state, "engine", None)
        return {
            "app": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "model_version": engine.model_version if engine else None,
        }

    if spa_enabled:
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        assets_dir = webapp_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> Response:
            """SPA 回退：命中真实文件则返回文件，否则回 index.html（前端路由）。"""
            if full_path.startswith("api/") or full_path == "docs":
                return JSONResponse(status_code=404,
                                    content={"code": CODE_NOT_FOUND,
                                             "message": "资源不存在", "data": None})
            candidate = webapp_dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(webapp_dist / "index.html")

        logger.info("前端静态托管已启用：%s（健康检查移至 /health）", webapp_dist)

    return app


app = create_app()
