"""
PMI中国AI项目管理社区 - 搜索引擎
基于 PostgreSQL 全文搜索 + Redis 缓存的混合搜索
"""

import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.config import settings
from app.db.session import AsyncSession as DBAsyncSession

logger = logging.getLogger(__name__)

# 支持的文档类型
DOC_TYPES = ["project", "task", "wiki_page", "comment", "user"]

# 文档类型对应的数据库表和搜索字段
DOC_TYPE_CONFIG = {
    "project": {
        "table": "projects",
        "fields": ["name", "description"],
        "id_field": "id",
        "extra_fields": ["status", "priority", "owner_id", "created_at"],
    },
    "task": {
        "table": "tasks",
        "fields": ["name", "description"],
        "id_field": "id",
        "extra_fields": ["status", "priority", "project_id", "assignee_id", "created_at"],
    },
    "wiki_page": {
        "table": "wiki_pages",
        "fields": ["title", "content"],
        "id_field": "id",
        "extra_fields": ["project_id", "created_by", "created_at"],
    },
    "comment": {
        "table": "comments",
        "fields": ["content"],
        "id_field": "id",
        "extra_fields": ["task_id", "project_id", "user_id", "created_at"],
    },
    "user": {
        "table": "users",
        "fields": ["username", "full_name", "email", "department", "position"],
        "id_field": "id",
        "extra_fields": ["is_active", "created_at"],
    },
}


class SearchEngine:
    """混合搜索引擎（PostgreSQL 全文搜索 + Redis 缓存）"""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def _get_redis(self) -> redis.Redis:
        """获取 Redis 连接"""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
            )
        return self._redis

    def _cache_key(self, prefix: str, *parts: str) -> str:
        """生成缓存键"""
        raw = ":".join([prefix] + list(parts))
        return f"search:{prefix}:{hashlib.md5(raw.encode()).hexdigest()}"

    async def _get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            r = await self._get_redis()
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"缓存读取失败: {e}")
        return None

    async def _set_cache(self, key: str, value: Any, ttl: int = 300) -> None:
        """设置缓存"""
        try:
            r = await self._get_redis()
            await r.setex(key, ttl, json.dumps(value, default=str))
        except Exception as e:
            logger.debug(f"缓存写入失败: {e}")

    async def index_document(
        self,
        doc_type: str,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        索引文档

        Args:
            doc_type: 文档类型（project/task/wiki_page/comment/user）
            doc_id: 文档ID
            content: 搜索内容
            metadata: 附加元数据

        Returns:
            bool: 是否索引成功
        """
        if doc_type not in DOC_TYPES:
            logger.error(f"不支持的文档类型: {doc_type}")
            return False

        try:
            r = await self._get_redis()

            # 构建索引数据
            index_data = {
                "doc_type": doc_type,
                "doc_id": doc_id,
                "content": content,
                "metadata": json.dumps(metadata or {}),
                "indexed_at": datetime.now().isoformat(),
            }

            # 存储到 Redis 搜索索引
            key = f"search:index:{doc_type}:{doc_id}"
            await r.hset(key, mapping=index_data)
            await r.expire(key, 86400 * 7)  # 7天过期

            # 添加到类型集合
            await r.sadd(f"search:docs:{doc_type}", doc_id)

            # 更新搜索词索引（简单的分词）
            words = self._tokenize(content)
            for word in words:
                await r.zincrby(f"search:terms:{doc_type}", 1, word)
                await r.sadd(f"search:term:{doc_type}:{word}", doc_id)

            logger.info(f"📄 文档已索引: {doc_type}/{doc_id}")
            return True

        except Exception as e:
            logger.error(f"文档索引失败: {e}")
            return False

    async def search(
        self,
        query: str,
        doc_types: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        执行搜索

        Args:
            query: 搜索关键词
            doc_types: 文档类型过滤
            filters: 额外过滤条件
            limit: 返回数量
            offset: 偏移量

        Returns:
            Dict: 搜索结果
        """
        if not query or not query.strip():
            return {"items": [], "total": 0, "query": query}

        # 检查缓存
        cache_key = self._cache_key(
            "search",
            query,
            ",".join(sorted(doc_types or [])),
            json.dumps(filters or {}, sort_keys=True),
            str(limit),
            str(offset),
        )
        cached = await self._get_cache(cache_key)
        if cached:
            return cached

        # 默认搜索所有支持的类型
        types_to_search = doc_types or DOC_TYPES
        types_to_search = [t for t in types_to_search if t in DOC_TYPES]

        all_results = []

        for doc_type in types_to_search:
            try:
                results = await self._search_type(doc_type, query, filters, limit, offset)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"搜索 {doc_type} 失败: {e}")

        # 按相关性排序
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        total = len(all_results)
        items = all_results[offset : offset + limit]

        result = {
            "items": items,
            "total": total,
            "query": query,
            "doc_types": types_to_search,
            "limit": limit,
            "offset": offset,
        }

        # 写入缓存
        await self._set_cache(cache_key, result, ttl=60)

        return result

    async def _search_type(
        self,
        doc_type: str,
        query: str,
        filters: Optional[Dict[str, Any]],
        limit: int,
        offset: int,
    ) -> List[Dict[str, Any]]:
        """搜索特定类型的文档"""
        config = DOC_TYPE_CONFIG.get(doc_type)
        if not config:
            return []

        # 使用 PostgreSQL 全文搜索
        from app.db.session import engine

        search_query = query.strip()

        # 构建全文搜索 SQL
        tsvector_parts = []
        for field in config["fields"]:
            tsvector_parts.append(f"coalesce({field}, '')")
        tsvector_expr = " || ' ' || ".join(tsvector_parts)

        # 构建过滤条件
        where_clauses = ["is_deleted = false" if doc_type in ["project", "task", "comment"] else "1=1"]
        params = {"query": search_query, "limit": limit, "offset": offset}

        if filters:
            for key, value in filters.items():
                if key in config["extra_fields"] and value is not None:
                    where_clauses.append(f"{key} = :{key}")
                    params[key] = value

        where_sql = " AND ".join(where_clauses)

        sql = text(f"""
            SELECT
                {config['id_field']} as id,
                {', '.join(config['fields'])},
                {', '.join(config['extra_fields'])},
                ts_rank(
                    to_tsvector('chinese', {tsvector_expr}),
                    plainto_tsquery('chinese', :query)
                ) as rank
            FROM {config['table']}
            WHERE {where_sql}
              AND to_tsvector('chinese', {tsvector_expr}) @@ plainto_tsquery('chinese', :query)
            ORDER BY rank DESC
            LIMIT :limit OFFSET :offset
        """)

        results = []
        async with engine.connect() as conn:
            result = await conn.execute(sql, params)
            rows = result.mappings().all()

            for row in rows:
                item = dict(row)
                results.append({
                    "doc_type": doc_type,
                    "doc_id": str(item.get("id")),
                    "title": self._extract_title(item, config["fields"]),
                    "content_preview": self._extract_preview(item, config["fields"]),
                    "score": float(item.get("rank", 0)),
                    "metadata": {k: item.get(k) for k in config["extra_fields"] if k in item},
                })

        return results

    async def delete_document(self, doc_type: str, doc_id: str) -> bool:
        """
        删除索引

        Args:
            doc_type: 文档类型
            doc_id: 文档ID

        Returns:
            bool: 是否删除成功
        """
        try:
            r = await self._get_redis()

            # 删除索引
            key = f"search:index:{doc_type}:{doc_id}"
            await r.delete(key)

            # 从集合中移除
            await r.srem(f"search:docs:{doc_type}", doc_id)

            logger.info(f"🗑️ 文档索引已删除: {doc_type}/{doc_id}")
            return True

        except Exception as e:
            logger.error(f"删除文档索引失败: {e}")
            return False

    async def suggest(self, query: str, limit: int = 10) -> List[str]:
        """
        搜索建议

        Args:
            query: 输入关键词
            limit: 返回数量

        Returns:
            List[str]: 建议列表
        """
        if not query or len(query) < 2:
            return []

        cache_key = self._cache_key("suggest", query, str(limit))
        cached = await self._get_cache(cache_key)
        if cached:
            return cached

        try:
            r = await self._get_redis()
            suggestions = set()

            # 从 Redis 词索引中查找匹配的词
            for doc_type in DOC_TYPES:
                pattern = f"search:term:{doc_type}:{query.lower()}*"
                keys = await r.keys(pattern)
                for key in keys:
                    word = key.split(":")[-1]
                    suggestions.add(word)

            result = sorted(list(suggestions))[:limit]

            # 缓存建议
            await self._set_cache(cache_key, result, ttl=300)

            return result

        except Exception as e:
            logger.error(f"获取搜索建议失败: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """获取搜索统计信息"""
        try:
            r = await self._get_redis()
            stats = {}

            for doc_type in DOC_TYPES:
                count = await r.scard(f"search:docs:{doc_type}")
                stats[doc_type] = count

            return {
                "indexed_documents": stats,
                "total": sum(stats.values()),
            }

        except Exception as e:
            logger.error(f"获取搜索统计失败: {e}")
            return {}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """简单的中文分词"""
        import re
        # 提取中文字符和英文单词
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text.lower())
        # 过滤短词
        return [w for w in words if len(w) >= 2]

    @staticmethod
    def _extract_title(item: Dict[str, Any], fields: List[str]) -> str:
        """提取标题"""
        for field in fields:
            if field in item and item[field]:
                value = str(item[field])
                # 返回前 50 个字符作为标题
                return value[:50] + ("..." if len(value) > 50 else "")
        return "Untitled"

    @staticmethod
    def _extract_preview(item: Dict[str, Any], fields: List[str]) -> str:
        """提取内容预览"""
        for field in fields:
            if field in item and item[field]:
                value = str(item[field])
                return value[:200] + ("..." if len(value) > 200 else "")
        return ""


# 全局搜索引擎实例
search_engine = SearchEngine()
