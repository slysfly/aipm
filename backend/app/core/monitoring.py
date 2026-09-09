"""
PMI中国AI项目管理社区 - 监控与可观测性
使用内存中的环形缓冲区 + 定期聚合
"""

import time
import logging
import statistics
from typing import Dict, Any, List, Optional, Deque
from collections import deque
from datetime import datetime, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RequestMetric:
    """请求指标"""
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now())


@dataclass
class DBQueryMetric:
    """数据库查询指标"""
    table: str
    operation: str
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now())


@dataclass
class ErrorMetric:
    """错误指标"""
    error_type: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now())


class MetricsCollector:
    """指标收集器（基于内存环形缓冲区）"""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._requests: Deque[RequestMetric] = deque(maxlen=max_size)
        self._db_queries: Deque[DBQueryMetric] = deque(maxlen=max_size)
        self._errors: Deque[ErrorMetric] = deque(maxlen=max_size)
        self._start_time = datetime.now()

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """记录API请求指标"""
        metric = RequestMetric(
            method=method.upper(),
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        self._requests.append(metric)

    def record_db_query(self, table: str, operation: str, duration_ms: float) -> None:
        """记录数据库查询指标"""
        metric = DBQueryMetric(
            table=table,
            operation=operation.upper(),
            duration_ms=duration_ms,
        )
        self._db_queries.append(metric)

    def record_error(self, error_type: str, message: str) -> None:
        """记录错误"""
        metric = ErrorMetric(
            error_type=error_type,
            message=message[:500],  # 限制长度
        )
        self._errors.append(metric)

    def get_metrics(self, window_seconds: int = 300) -> Dict[str, Any]:
        """
        获取聚合指标

        Args:
            window_seconds: 时间窗口（秒），默认5分钟

        Returns:
            Dict: 聚合指标
        """
        cutoff = datetime.now() - timedelta(seconds=window_seconds)

        # 过滤时间窗口内的请求
        recent_requests = [r for r in self._requests if r.timestamp >= cutoff]
        recent_db_queries = [q for q in self._db_queries if q.timestamp >= cutoff]
        recent_errors = [e for e in self._errors if e.timestamp >= cutoff]

        # 计算请求指标
        request_metrics = self._calc_request_metrics(recent_requests)

        # 计算数据库指标
        db_metrics = self._calc_db_metrics(recent_db_queries)

        # 计算错误指标
        error_metrics = self._calc_error_metrics(recent_errors, len(recent_requests))

        return {
            "window_seconds": window_seconds,
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            "requests": request_metrics,
            "database": db_metrics,
            "errors": error_metrics,
        }

    def get_slow_queries(self, threshold_ms: float = 500.0, limit: int = 50) -> List[Dict[str, Any]]:
        """获取慢查询列表"""
        slow = [
            {
                "table": q.table,
                "operation": q.operation,
                "duration_ms": round(q.duration_ms, 2),
                "timestamp": q.timestamp.isoformat(),
            }
            for q in self._db_queries
            if q.duration_ms >= threshold_ms
        ]
        # 按时间倒序
        slow.sort(key=lambda x: x["timestamp"], reverse=True)
        return slow[:limit]

    def get_error_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取错误日志"""
        errors = [
            {
                "error_type": e.error_type,
                "message": e.message,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in self._errors
        ]
        errors.sort(key=lambda x: x["timestamp"], reverse=True)
        return errors[:limit]

    def get_qps_trend(self, buckets: int = 20) -> List[Dict[str, Any]]:
        """获取 QPS 趋势（按时间分桶）"""
        if not self._requests:
            return []

        now = datetime.now()
        window_start = now - timedelta(minutes=10)
        bucket_size = 600 / buckets  # 10分钟分成 buckets 个桶

        # 初始化桶
        bucket_counts = [0] * buckets
        bucket_latencies = [[] for _ in range(buckets)]

        for req in self._requests:
            if req.timestamp < window_start:
                continue

            seconds_ago = (now - req.timestamp).total_seconds()
            bucket_idx = min(int(seconds_ago / bucket_size), buckets - 1)
            bucket_idx = buckets - 1 - bucket_idx  # 反转，最新的在右边

            bucket_counts[bucket_idx] += 1
            bucket_latencies[bucket_idx].append(req.duration_ms)

        result = []
        for i in range(buckets):
            latencies = bucket_latencies[i]
            result.append({
                "bucket": i,
                "count": bucket_counts[i],
                "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0,
                "p95_latency_ms": round(self._percentile(latencies, 95), 2) if latencies else 0,
            })

        return result

    def _calc_request_metrics(self, requests: List[RequestMetric]) -> Dict[str, Any]:
        """计算请求指标"""
        if not requests:
            return {
                "total": 0,
                "qps": 0.0,
                "latency_p50_ms": 0.0,
                "latency_p95_ms": 0.0,
                "latency_p99_ms": 0.0,
                "status_distribution": {},
                "top_paths": [],
            }

        durations = [r.duration_ms for r in requests]
        total = len(requests)
        window_seconds = 300  # 5分钟
        qps = total / window_seconds

        # 状态码分布
        status_dist: Dict[str, int] = {}
        path_counts: Dict[str, int] = {}
        for r in requests:
            status_key = str(r.status_code)
            status_dist[status_key] = status_dist.get(status_key, 0) + 1
            path_counts[r.path] = path_counts.get(r.path, 0) + 1

        # Top 路径
        top_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total": total,
            "qps": round(qps, 2),
            "latency_p50_ms": round(self._percentile(durations, 50), 2),
            "latency_p95_ms": round(self._percentile(durations, 95), 2),
            "latency_p99_ms": round(self._percentile(durations, 99), 2),
            "status_distribution": status_dist,
            "top_paths": [{"path": p, "count": c} for p, c in top_paths],
        }

    def _calc_db_metrics(self, queries: List[DBQueryMetric]) -> Dict[str, Any]:
        """计算数据库指标"""
        if not queries:
            return {
                "total_queries": 0,
                "avg_duration_ms": 0.0,
                "slow_query_count": 0,
                "table_distribution": {},
            }

        durations = [q.duration_ms for q in queries]
        slow_count = sum(1 for q in queries if q.duration_ms >= 500)

        # 表分布
        table_dist: Dict[str, int] = {}
        for q in queries:
            table_dist[q.table] = table_dist.get(q.table, 0) + 1

        return {
            "total_queries": len(queries),
            "avg_duration_ms": round(statistics.mean(durations), 2),
            "slow_query_count": slow_count,
            "table_distribution": table_dist,
        }

    def _calc_error_metrics(self, errors: List[ErrorMetric], total_requests: int) -> Dict[str, Any]:
        """计算错误指标"""
        if not errors:
            return {
                "total": 0,
                "error_rate": 0.0,
                "type_distribution": {},
            }

        # 错误类型分布
        type_dist: Dict[str, int] = {}
        for e in errors:
            type_dist[e.error_type] = type_dist.get(e.error_type, 0) + 1

        error_rate = (len(errors) / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "total": len(errors),
            "error_rate": round(error_rate, 4),
            "type_distribution": type_dist,
        }

    @staticmethod
    def _percentile(data: List[float], percentile: int) -> float:
        """计算百分位数"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        if f == c:
            return sorted_data[f]
        return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


# 全局指标收集器实例
metrics_collector = MetricsCollector()
