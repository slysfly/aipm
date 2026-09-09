"""
PMI中国AI项目管理社区 - 监控API

[PMBOK KA: 质量管理 | PG: 监控 (Quality/Monitoring) — 质量指标、性能监控]
对应PMI第6版标准：质量指标、过程监控、性能测量

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: AI Management — 模型运营监控]
PMBOK 7th Principle: Measurement | Domain: Measurement — 持续测量、绩效评估
PMBOK 8th: Real-Time Monitoring Intelligence"""

import time
from fastapi import APIRouter, Query, Depends
from app.core.security import require_superuser
from sqlalchemy import text
import redis.asyncio as redis

from app.core.monitoring import metrics_collector
from app.db.session import engine
from app.config import settings
from app.schemas import SuccessResponse

router = APIRouter(dependencies=[Depends(require_superuser)])


async def check_database_health() -> dict:
    try:
        start = time.time()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = (time.time() - start) * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def check_redis_health() -> dict:
    try:
        start = time.time()
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        latency_ms = (time.time() - start) * 1000
        await r.close()
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


@router.get("/monitoring/metrics")
async def get_metrics(
    window: int = Query(300, ge=60, le=3600, description="时间窗口（秒）"),
):
    metrics = metrics_collector.get_metrics(window_seconds=window)
    qps_trend = metrics_collector.get_qps_trend(buckets=20)

    return SuccessResponse(
        data={
            **metrics,
            "qps_trend": qps_trend,
        },
        message="获取指标成功",
    )


@router.get("/monitoring/health")
async def health_check():
    db_health = await check_database_health()
    redis_health = await check_redis_health()

    overall_status = "healthy"
    if db_health["status"] != "healthy" or redis_health["status"] != "healthy":
        overall_status = "degraded"
    if db_health["status"] == "unhealthy" and redis_health["status"] == "unhealthy":
        overall_status = "unhealthy"

    return SuccessResponse(
        data={
            "status": overall_status,
            "timestamp": time.time(),
            "services": {
                "api": {"status": "healthy"},
                "database": db_health,
                "redis": redis_health,
            },
        },
        message="健康检查完成",
    )


@router.get("/monitoring/slow-queries")
async def get_slow_queries(
    threshold: float = Query(500.0, ge=100, description="慢查询阈值（毫秒）"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
):
    slow_queries = metrics_collector.get_slow_queries(
        threshold_ms=threshold,
        limit=limit,
    )

    return SuccessResponse(
        data={
            "threshold_ms": threshold,
            "count": len(slow_queries),
            "items": slow_queries,
        },
        message="获取慢查询列表成功",
    )


@router.get("/monitoring/errors")
async def get_errors(
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
):
    errors = metrics_collector.get_error_logs(limit=limit)

    return SuccessResponse(
        data={
            "count": len(errors),
            "items": errors,
        },
        message="获取错误日志成功",
    )
