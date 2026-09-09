"""
PMI中国AI项目管理社区 - 主应用入口
全球顶尖的AI驱动型项目管理平台
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import os
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
from app.core.response import ok_dict, error_dict
from app.core.lifespan_factory import create_lifespan
from app.middleware.monitoring import MonitoringMiddleware
from app.middleware.response_format import ResponseFormatMiddleware

# 配置日志
logger = setup_logging()


# 使用公共生命周期工厂（开发入口：create_all 策略，无需 Alembic 迁移即可启动）
lifespan = create_lifespan(
    db_strategy="create_all",
    enable_seed_data=False,
    enable_system_llm=False,
    enable_message_queue_stop=False,
)


# 创建FastAPI应用
app = FastAPI(
    title="PMI中国AI项目管理社区",
    description="""
    🌟 **全球顶尖的AI驱动型项目管理平台**
    
    ## 核心能力
    
    🤖 **AI执行主体**
    - 自然语言 → WBS智能分解
    - 多Agent协同执行
    - 实时自优化
    
    📊 **企业级项目管理**
    - Portfolio组合管理
    - 挣值管理(EVM)
    - 风险管理
    
    🔗 **深度集成**
    - 飞书生态深度整合
    - 企业微信/钉钉集成
    - 开放API生态
    
    ## 技术栈
    
    - **后端**: Python FastAPI + PostgreSQL
    - **AI**: LangGraph + LangChain + LLM Router
    - **前端**: React + TypeScript
    """,
    version=settings.VERSION,
    # 生产环境关闭 API 文档
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
    lifespan=lifespan,
)


# 添加中间件
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(MonitoringMiddleware, slow_query_threshold_ms=500.0)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一响应格式中间件：自动包裹 JSON 响应为标准信封 {code, data, message}
app.add_middleware(ResponseFormatMiddleware)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """添加请求处理时间"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志"""
    start_time = datetime.now()
    logger.info(f"➡️ {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    duration = (datetime.now() - start_time).total_seconds()
    logger.info(
        f"⬅️ {request.method} {request.url.path} "
        f"状态码: {response.status_code} 耗时: {duration:.3f}s"
    )
    
    return response


# 注册异常处理器（统一响应格式）
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


# 注册API路由
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "PMI中国AI项目管理社区",
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    # 开发入口：默认仅绑定回环地址、关闭自动重载，避免开发服务器暴露到全网或被误用作生产运行。
    # 生产部署请使用 serve.py（serve:app）。可通过环境变量覆盖：HOST / PORT / RELOAD。
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("RELOAD", "False").lower() in ("1", "true", "yes", "on"),
        log_level="info",
    )
