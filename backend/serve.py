"""
PMI中国AI项目管理社区 - 生产模式入口
同时服务后端API和前端静态文件
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
import time
from datetime import datetime

from app.config import settings
from app.api.routers import api_router
from app.core.logging import setup_logging
from app.core.exceptions import (
    ProjectManagementException,
    NotFoundException,
    ValidationException,
    AuthenticationException,
    AuthorizationException,
)
from app.core.response import success, error_dict
from app.core.lifespan_factory import create_lifespan
from app.middleware.monitoring import MonitoringMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

logger = setup_logging()

# 内置预构建（随仓库提供 / Docker COPY 目标），保证开箱即用
_PREBUILT = Path(__file__).parent / "frontend"
# 本地自行构建的产物（执行 npm install && npm run build 后生成）
_LOCAL_DIST = Path(__file__).parent.parent / "frontend" / "dist"

# 优先使用本地自行构建的前端；否则回退到内置预构建（无需任何前端构建步骤即可运行）
if _LOCAL_DIST.exists():
    FRONTEND_DIST = _LOCAL_DIST
elif _PREBUILT.exists():
    FRONTEND_DIST = _PREBUILT
else:
    FRONTEND_DIST = _PREBUILT


# 使用公共生命周期工厂（生产入口：Alembic 迁移 + 消息队列清理）
# 注意：enable_seed_data 保持 False —— 生产环境绝不自动写入演示/示例数据，
# 保证数据库中的所有项目/任务均为用户真实数据（数据真实性策略）。
lifespan = create_lifespan(
    db_strategy="migrate",
    enable_seed_data=False,
    enable_system_llm=True,
    enable_message_queue_stop=True,
)


app = FastAPI(
    title="PMI中国AI项目管理社区",
    description="全球标准AI驱动型项目管理平台 · PMI中国",
    version=settings.VERSION,
    # 生产环境关闭 API 文档（避免内部接口结构暴露到公网）
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(MonitoringMiddleware, slow_query_threshold_ms=500.0)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))
    return response




# 前端对集合端点普遍不带尾斜杠（如 POST /api/v1/projects），而后端路由注册为带尾斜杠。
# Starlette 默认的 RedirectSlashes 对 POST 会以 307 重定向并丢失 body，导致创建失败。
# 这里在内部（不重定向）为已知集合端点补尾斜杠，保留请求方法与 body。
# 仅作用于 /api/v1/<collection>（4 段）且末段为已知集合名词的请求，避免误改 /auth/login 等。
_COLLECTION_NAMES = {
    "app-market",
    "approvals",
    "attachments",
    "automations",
    "budgets",
    "change-requests",
    "comments",
    "compliance",
    "custom-fields",
    "epics",
    "forms",
    "integrations",
    "knowledge-base",
    "knowledge-bases",
    "llm-configs",
    "members",
    "messages",
    "monitoring",
    "multi-agent",
    "nlp-query",
    "notifications",
    "projects",
    "recurring-tasks",
    "releases",
    "reports",
    "roles",
    "scheduled-jobs",
    "search",
    "sprints",
    "task-templates",
    "tasks",
    "webhooks",
    "wiki",
    "zapier",
}


@app.middleware("http")
async def api_trailing_slash_rewrite(request: Request, call_next):
    path = request.url.path
    parts = [x for x in path.split("/") if x]
    # /api/v1/<collection> 共 3 段
    if len(parts) == 3 and parts[0] == "api" and parts[1] == "v1" and parts[2] in _COLLECTION_NAMES:
        scope = request.scope
        scope["path"] = "/" + "/".join(parts) + "/"
        request = Request(scope, request.receive)
    return await call_next(request)


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    return JSONResponse(status_code=404, content=error_dict(code=404, message=exc.message, details=exc.details))


@app.exception_handler(ValidationException)
async def validation_handler(request: Request, exc: ValidationException):
    return JSONResponse(status_code=422, content=error_dict(code=422, message=exc.message, details=exc.details))


@app.exception_handler(ProjectManagementException)
async def pm_exception_handler(request: Request, exc: ProjectManagementException):
    return JSONResponse(status_code=400, content=error_dict(code=400, message=exc.message, details=exc.details))


@app.exception_handler(AuthenticationException)
async def auth_exception_handler(request: Request, exc: AuthenticationException):
    return JSONResponse(status_code=401, content=error_dict(code=401, message=exc.message, details=exc.details))


@app.exception_handler(AuthorizationException)
async def authorization_exception_handler(request: Request, exc: AuthorizationException):
    return JSONResponse(status_code=403, content=error_dict(code=403, message=exc.message, details=exc.details))


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理的异常: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content=error_dict(code=500, message="服务器内部错误，请稍后重试"))


app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat(), "version": settings.VERSION}


if FRONTEND_DIST.exists():
    # ── 自定义 StaticFiles：给带 hash 的资源文件设长缓存，其余不缓存 ──
    class CacheControlledStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            if response.status_code == 200:
                # Vite 构建产物文件名含 hash（如 index-abc123.js），
                # 可安全长期缓存；无 hash 的文件每次都重新验证
                if any(c.isalpha() for c in path.rsplit(".", 1)[0][-8:]):
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                else:
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return response

    app.mount("/assets", CacheControlledStaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

    # 根级静态文件：显式路由提供
    @app.get("/icon.svg")
    async def serve_icon():
        return FileResponse(FRONTEND_DIST / "icon.svg", media_type="image/svg+xml",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/manifest.json")
    async def serve_manifest():
        return FileResponse(FRONTEND_DIST / "manifest.json", media_type="application/manifest+json",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    @app.get("/manifest.webmanifest")
    async def serve_manifest_web():
        return FileResponse(FRONTEND_DIST / "manifest.webmanifest", media_type="application/manifest+json",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    @app.get("/sw.js")
    async def serve_sw():
        return FileResponse(FRONTEND_DIST / "sw.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    _ROOT_STATIC_FILES = {"/icon.svg", "/manifest.json", "/manifest.webmanifest", "/sw.js"}

    @app.middleware("http")
    async def spa_fallback(request: Request, call_next):
        # 先尝试走正常路由（API、静态资源、根静态文件等）
        response = await call_next(request)
        # 仅当不是已知静态文件路径时才尝试 SPA fallback
        path = request.url.path
        if (
            response.status_code == 404
            and request.method == "GET"
            and path not in _ROOT_STATIC_FILES
            and not path.startswith("/api")
            and not path.startswith("/docs")
            and not path.startswith("/redoc")
            and not path.startswith("/openapi.json")
            and not path.startswith("/assets")
        ):
            resp = FileResponse(str(FRONTEND_DIST / "index.html"))
            # index.html 永远不能被缓存，否则用户拿不到新版本
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            return resp
        return response


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("RELOAD", "False").lower() in ("true", "1", "yes")
    uvicorn.run(
        "serve:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=port,
        reload=reload,
        workers=4,
        log_level="info",
    )
