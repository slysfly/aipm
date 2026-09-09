"""
PMI中国AI项目管理社区 - RAG引擎
支持语义搜索和关键词匹配降级
[CPMAI Phase: Data Understanding | Domain: Data for AI — RAG知识检索增强、AI数据理解]
"""

import os
import re
import math
import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from types import SimpleNamespace
from collections import Counter
import asyncio
import threading

from sqlalchemy import select, delete, and_, or_, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase, KnowledgeDocument, KnowledgeChunk, DocumentStatus
from app.config import settings
from app.db.vector import is_postgres


# ============================================================
# SAG（SQL-Retrieval Augmented Generation）检索增强
# 实体抽取 -> SQL ILIKE 候选过滤(含文档标题路由) -> 向量重排
# 通过 RAG_MODE 环境变量开关：sag(默认) / naive(强制朴素，便于回滚)
# ============================================================
_SAG_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "一个", "如何", "什么", "哪些", "怎么",
    "吗", "呢", "这", "那", "我", "你", "他", "我们", "你们", "他们", "该", "各", "有", "为",
    "对", "从", "到", "由", "等", "中", "上", "下", "内", "外", "前", "后", "之", "其", "但",
    "而", "并", "将", "把", "被", "让", "给", "向", "于", "以", "则", "若", "如", "是否",
    "多少", "几", "种", "类", "项", "个", "条", "次", "些", "般", "性", "度", "化", "请",
    "问", "关于", "根据", "基于", "可以", "需要", "进行", "实现", "通过", "以及", "还是",
    "这个", "那个", "哪些", "这些", "那些", "一种", "一项", "是否", "有没有", "能否", "为什么",
}

# 领域词表（PM / 通用）：命中即作为强实体参与 SQL 过滤与文档路由
_SAG_GLOSSARY = [
    "stakeholder", "register", "wbs", "scope", "risk", "issue log", "lessons learned",
    "sponsor", "change control", "change log", "principle", "standard", "retrospective",
    "charter", "baseline", "milestone", "deliverable", "backlog", "sprint", "kanban",
    "干系人", "登记册", "工作分解", "范围", "风险", "问题日志", "经验教训", "发起人",
    "变更控制", "变更日志", "原则", "标准", "回顾", "章程", "基线", "里程碑", "可交付",
    "敏捷", "瀑布", "项目管理", "项目经理", "治理", "质量", "成本", "进度", "沟通", "采购",
]


class TextChunker:
    """文本分块器 - 支持多种分块策略"""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        strategy: str = "hybrid"
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy

    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """
        将文本分块
        策略：hybrid（混合：先按段落，大段落再按固定长度）
        """
        if not text or not text.strip():
            return []

        if self.strategy == "paragraph":
            return self._chunk_by_paragraph(text)
        elif self.strategy == "fixed":
            return self._chunk_by_fixed_size(text)
        elif self.strategy == "semantic":
            return self._chunk_by_semantic(text)
        else:  # hybrid
            return self._chunk_by_hybrid(text)

    def _chunk_by_paragraph(self, text: str) -> List[Dict[str, Any]]:
        """按段落分块"""
        paragraphs = re.split(r'\n\s*\n', text.strip())
        chunks = []
        pos = 0

        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            chunks.append({
                "content": para,
                "index": i,
                "start_pos": pos,
                "end_pos": pos + len(para),
            })
            pos += len(para) + 2

        return chunks

    def _chunk_by_fixed_size(self, text: str) -> List[Dict[str, Any]]:
        """按固定长度分块"""
        chunks = []
        start = 0
        index = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_size, text_len)

            # 尝试在句子边界处分割
            if end < text_len:
                sentence_end = text.rfind('。', start, end)
                if sentence_end == -1:
                    sentence_end = text.rfind('. ', start, end)
                if sentence_end == -1:
                    sentence_end = text.rfind('\n', start, end)
                if sentence_end != -1 and sentence_end > start + self.chunk_size // 2:
                    end = sentence_end + 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "index": index,
                    "start_pos": start,
                    "end_pos": end,
                })
                index += 1

            start = end - self.chunk_overlap if end < text_len else end

        return chunks

    def _chunk_by_semantic(self, text: str) -> List[Dict[str, Any]]:
        """按语义边界分块（简单实现：按标题和段落）"""
        # 识别标题模式
        heading_pattern = r'(?:^|\n)(#{1,6}\s.+|【.+】|第[一二三四五六七八九十\d]+[章节].*)'
        parts = re.split(heading_pattern, text)

        chunks = []
        index = 0
        pos = 0

        current_section = ""
        for part in parts:
            if not part or not part.strip():
                continue

            if re.match(heading_pattern, part.strip()):
                # 保存之前的section
                if current_section.strip():
                    sub_chunks = self._chunk_large_text(current_section.strip(), index, pos)
                    chunks.extend(sub_chunks)
                    index += len(sub_chunks)
                    pos += len(current_section)
                current_section = part + "\n"
            else:
                current_section += part

        # 保存最后一个section
        if current_section.strip():
            sub_chunks = self._chunk_large_text(current_section.strip(), index, pos)
            chunks.extend(sub_chunks)

        return chunks

    def _chunk_by_hybrid(self, text: str) -> List[Dict[str, Any]]:
        """混合策略：先按段落，大段落再细分"""
        paragraphs = re.split(r'\n\s*\n', text.strip())
        chunks = []
        index = 0
        pos = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) <= self.chunk_size:
                # 小段落直接作为一个chunk
                chunks.append({
                    "content": para,
                    "index": index,
                    "start_pos": pos,
                    "end_pos": pos + len(para),
                })
                index += 1
                pos += len(para) + 2
            else:
                # 大段落进一步分割
                sub_chunks = self._chunk_large_text(para, index, pos)
                chunks.extend(sub_chunks)
                index += len(sub_chunks)
                pos += len(para) + 2

        return chunks

    def _chunk_large_text(self, text: str, start_index: int, start_pos: int) -> List[Dict[str, Any]]:
        """将大文本按固定长度分割"""
        chunks = []
        text_start = 0
        text_len = len(text)
        index = start_index
        pos = start_pos

        while text_start < text_len:
            end = min(text_start + self.chunk_size, text_len)

            # 尝试在句子边界处分割
            if end < text_len:
                for sep in ['。', '. ', '；', '; ', '\n']:
                    sep_pos = text.rfind(sep, text_start, end)
                    if sep_pos != -1 and sep_pos > text_start + self.chunk_size // 3:
                        end = sep_pos + len(sep)
                        break

            chunk_text = text[text_start:end].strip()
            if chunk_text:
                chunks.append({
                    "content": chunk_text,
                    "index": index,
                    "start_pos": pos + text_start,
                    "end_pos": pos + end,
                })
                index += 1

            text_start = end

        return chunks


class KeywordMatcher:
    """关键词匹配器（降级方案）"""

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """简单分词"""
        # 保留中文字符、英文单词和数字
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|\d+', text.lower())
        return tokens

    @staticmethod
    def compute_tf_idf_similarity(query: str, documents: List[str]) -> List[float]:
        """计算TF-IDF相似度（高效实现）。

        ⚠️ 2026-08-08 修复：原实现 IDF 为 O(V×D)（每个词遍历全部文档），
        3115 文档 × 数万词表 ≈ 数亿次操作 → 数十秒卡死 + RSS 3GB+ OOM
        （独立进程实测 anon-rss 3.12GB，生产 2200M 撞线被杀）。
        本实现：DF 用 Counter 一次遍历（O(D×L)）、IDF 为 O(V)、
        余弦只遍历较小向量的交集（O(min)），总量 O(D×L + V + D×avg) ≈ 秒级。
        """
        if not documents:
            return []

        query_tokens = KeywordMatcher.tokenize(query)
        doc_tokens_list = [KeywordMatcher.tokenize(doc) for doc in documents]

        # 每篇文档词频（Counter，一次遍历）
        doc_tfs = [Counter(tokens) for tokens in doc_tokens_list]

        # 文档频率 DF：某词出现在多少篇文档（keys 去重后计数）
        df = Counter()
        for tf in doc_tfs:
            df.update(tf.keys())
        n_docs = len(doc_tfs)

        # IDF（含平滑）
        idf = {token: math.log((n_docs + 1) / (df.get(token, 0) + 1)) + 1 for token in df}

        def compute_tfidf(tf: Counter) -> Dict[str, float]:
            total = sum(tf.values()) or 1
            return {token: (count / total) * idf.get(token, 0) for token, count in tf.items()}

        query_vec = compute_tfidf(Counter(query_tokens))
        doc_vecs = [compute_tfidf(tf) for tf in doc_tfs]

        def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
            if not vec1 or not vec2:
                return 0.0
            # 只遍历较小向量（query 词少），交集点积
            if len(vec1) > len(vec2):
                vec1, vec2 = vec2, vec1
            dot = sum(vec1.get(k, 0) * vec2.get(k, 0) for k in vec1)
            norm1 = math.sqrt(sum(v * v for v in vec1.values()))
            norm2 = math.sqrt(sum(v * v for v in vec2.values()))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)

        return [cosine_similarity(query_vec, doc_vec) for doc_vec in doc_vecs]


class EmbeddingService:
    """Embedding 服务 - 支持本地免费中文模型(BGE 系列)与 OpenAI 两种提供方。

    默认使用本地 BGE 中文向量模型（MIT 协议、完全免费、中文 SOTA），无需 API Key。
    提供方由 settings.RAG_EMBEDDING_PROVIDER 控制：
      - "local"        : 本地 BGE 模型（默认，RAG_LOCAL_MODEL 指定具体型号）
      - "openai"       : 调用 OpenAI/兼容接口（需配置 API Key）
    本地模型懒加载并缓存为单例；首次调用会按需下载权重（bge-base-zh ~400MB /
    bge-small-zh ~100MB）。向量强制 L2 归一化，便于余弦相似度直接比较。
    任意异常均降级回关键词检索，保证系统不崩。
    """

    def __init__(self):
        self.provider = getattr(settings, "RAG_EMBEDDING_PROVIDER", "local")
        self.local_model_name = getattr(settings, "RAG_LOCAL_MODEL", "BAAI/bge-base-zh")
        # OpenAI 兼容路径
        self.api_key = settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY
        self.base_url = "https://api.openai.com/v1"
        self.model = "text-embedding-3-small"
        # 本地模型懒加载相关
        self._local_model = None
        # 锁必须在 __init__ 就创建：原先的懒初始化（if self._local_lock is None）
        # 存在竞态——两个线程可能各自造一把锁，导致互斥失效、模型被重复加载。
        self._local_lock = threading.Lock()
        self._load_error = None
        self._dim = None
        if self.provider.startswith("local"):
            # 乐观可用：首次加载失败再降级为不可用（search 会自动回退关键词）
            self._available = True
        else:
            self._available = bool(self.api_key)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def dimension(self) -> Optional[int]:
        """向量维度（首次加载模型后可知；用于校验/调试）。"""
        if self._dim is None and self._local_model is not None:
            try:
                self._dim = int(self._local_model.get_sentence_embedding_dimension())
            except Exception:
                self._dim = None
        return self._dim

    def _get_local_model(self):
        """懒加载本地 BGE 单例（线程安全）。

        注意：本方法只保证「同一个 EmbeddingService 实例内」不重复加载。
        跨请求的复用由模块级单例 get_embedding_service() 保证——
        务必通过它拿 EmbeddingService，不要直接 new。
        """
        if self._local_model is not None:
            return self._local_model
        with self._local_lock:
            if self._local_model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    import os as _os
                    # 利用多核对 CPU 推理加速（容器/受限环境默认常退化为单线程）
                    try:
                        import torch as _torch
                        # 3.7GB 小机器：限制推理线程到 2（原为 cpu_count=4），
                        # 实测 4 线程下 BGE 加载峰值 ~2.1GB 会撞 MemoryMax=2200M
                        # 被 cgroup OOM 误杀；2 线程峰值 ~1.6GB 且推理 100→200ms，
                        # KB 检索低频场景完全可接受。
                        _torch.set_num_threads(min(2, max(1, (_os.cpu_count() or 1))))
                    except Exception:
                        pass
                    # 关键：强制本地缓存、禁止联网校验，消除每次查询向 hf-mirror.com
                    # 发网络请求导致的 46~70s 毛刺。模型已落地默认 HF 缓存
                    # (~/.cache/huggingface/hub/models--BAAI--bge-base-zh)，
                    # 故不传 cache_folder，避免路径错位导致找不到本地权重。
                    self._local_model = SentenceTransformer(
                        self.local_model_name,
                        local_files_only=True,
                    )
                    try:
                        self._dim = int(self._local_model.get_sentence_embedding_dimension())
                    except Exception:
                        self._dim = None
                except Exception as e:  # noqa: BLE001
                    self._load_error = str(e)
                    self._available = False
                    raise
        return self._local_model

    def _embed_local(self, texts):
        model = self._get_local_model()
        vecs = model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [[float(x) for x in vec] for vec in vecs]

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """生成文本的向量嵌入（统一返回 list[list[float]]）。"""
        if self.provider.startswith("local"):
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, self._embed_local, texts)
            except Exception as e:  # noqa: BLE001
                self._available = False
                raise RuntimeError(f"本地 BGE 向量化失败: {e}")
        # OpenAI 兼容路径
        if not self.is_available:
            raise RuntimeError("Embedding service not available: no API key configured")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                data = response.json()
                return [item["embedding"] for item in data["data"]]
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Embedding generation failed: {str(e)}")

    async def embed_single(self, text: str) -> List[float]:
        """生成单条文本的向量嵌入"""
        embeddings = await self.embed([text])
        return embeddings[0] if embeddings else []


# ============================================================
# EmbeddingService 进程级单例 🚨 性能与内存关键
# ------------------------------------------------------------
# 背景（2026-08-08 定位）：RAGEngine 在 18+ 个调用点被按请求 new，
# 其 __init__ 里原本直接 `EmbeddingService()`，而 _local_model 是实例属性，
# 于是【每一次知识库检索都会重新加载一遍 BGE 模型】：
#   · 单次加载 ≈ 8.8s、常驻 ≈ 900MB
#   · 连续几个请求叠加 → RSS 冲到 3.0~3.2GB → 3.7GB 的机器直接 OOM
#     （dmesg 实证：02:08 global_oom 3.23GB / 02:19 memcg oom 3.04GB）
#   · 表象是"CPU 推理要 12 秒"，实际推理本身只要 73~115ms
# 因此模型持有者必须是进程级单例。RAGEngine 仍可自由 new（它只持有 db 会话）。
# ============================================================
_EMBEDDING_SINGLETON: Optional["EmbeddingService"] = None
_EMBEDDING_SINGLETON_LOCK = threading.Lock()


def get_embedding_service() -> "EmbeddingService":
    """获取进程级唯一的 EmbeddingService（双重检查锁）。

    ⚠️ 任何地方都不要直接 `EmbeddingService()`，否则会重复加载 ~900MB 模型。
    """
    global _EMBEDDING_SINGLETON
    if _EMBEDDING_SINGLETON is None:
        with _EMBEDDING_SINGLETON_LOCK:
            if _EMBEDDING_SINGLETON is None:
                _EMBEDDING_SINGLETON = EmbeddingService()
    return _EMBEDDING_SINGLETON


class RAGEngine:
    """RAG引擎 - 检索增强生成"""

    def __init__(
        self,
        db_session: AsyncSession,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self.db = db_session
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        # 走进程级单例，避免每个请求重复加载 ~900MB 的 BGE 模型（见上方说明）
        self.embedding_service = get_embedding_service()
        self.keyword_matcher = KeywordMatcher()

    async def add_document(
        self,
        kb_id: str,
        title: str,
        content: str,
        source_type: str = "text",
        source_url: Optional[str] = None,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size: Optional[int] = None,
        mime_type: Optional[str] = None,
        meta_data: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeDocument:
        """
        添加文档到知识库（自动分块）
        """
        # content 语义：file 来源=原始字节(bytes)；text 来源=文本(str)
        from app.services.doc_parser import extract_text
        if isinstance(content, (bytes, bytearray)):
            raw_bytes = bytes(content)
            text_for_chunk = extract_text(file_name or "unnamed", raw_bytes) or ""
        else:
            raw_bytes = content.encode("utf-8") if content is not None else b""
            text_for_chunk = content or ""
        # 创建文档记录
        document = KnowledgeDocument(
            kb_id=kb_id,
            title=title,
            content=raw_bytes,
            source_type=source_type,
            source_url=source_url,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size if file_size is not None else 0,
            mime_type=mime_type,
            status=DocumentStatus.PROCESSING.value,
            meta_data=meta_data or {},
        )
        self.db.add(document)
        await self.db.flush()

        try:
            # 文本分块（同步、快速，保证上传接口即时返回）
            chunks = self.chunker.chunk_text(text_for_chunk)

            if not chunks:
                document.status = DocumentStatus.COMPLETED.value
                document.chunk_count = 0
                await self.db.commit()
                return document

            # 先保存文本块：embedding 留空，由后台任务异步补全，避免阻塞上传响应
            chunk_objs = []
            for chunk_data in chunks:
                chunk = KnowledgeChunk(
                    document_id=document.id,
                    content=chunk_data["content"],
                    embedding=None,
                    chunk_index=chunk_data["index"],
                    start_pos=chunk_data["start_pos"],
                    end_pos=chunk_data["end_pos"],
                    meta_data={"strategy": self.chunker.strategy},
                )
                self.db.add(chunk)
                chunk_objs.append(chunk)

            await self.db.flush()  # 分配 chunk id，供后台向量化定位
            document.status = DocumentStatus.COMPLETED.value
            document.chunk_count = len(chunks)
            await self.db.commit()
            await self.db.refresh(document)

            # 向量化改为后台任务：上传接口立即返回，向量在后台补全（best-effort，失败不影响文本块）
            if self.embedding_service.is_available and chunk_objs:
                chunk_ids = [c.id for c in chunk_objs]
                chunk_texts = [c.content for c in chunk_objs]
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._embed_chunks(chunk_ids, chunk_texts))
                except Exception:
                    pass

            return document

        except Exception as e:
            document.status = DocumentStatus.FAILED.value
            document.error_message = str(e)
            await self.db.commit()
            raise RuntimeError(f"Document processing failed: {str(e)}")

    async def update_document(
        self,
        doc_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        meta_data: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeDocument:
        """
        更新已存在文档的标题/正文，并重新分块（拆解）+ 异步向量化。
        用于"文档与知识库合并"后富文本文档的在线编辑：编辑即重新入库。
        """
        result = await self.db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise RuntimeError("文档不存在")

        if title is not None:
            document.title = title
        if content is not None:
            document.content = content.encode("utf-8")
        if meta_data is not None:
            document.meta_data = {**(document.meta_data or {}), **meta_data}

        # 丢弃旧分块，按最新正文重新拆解
        await self.db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        )
        document.status = DocumentStatus.PROCESSING.value
        document.chunk_count = 0
        await self.db.flush()

        try:
            if not content or not content.strip():
                document.status = DocumentStatus.COMPLETED.value
                document.chunk_count = 0
                await self.db.commit()
                await self.db.refresh(document)
                return document

            chunks = self.chunker.chunk_text(content)
            if not chunks:
                document.status = DocumentStatus.COMPLETED.value
                document.chunk_count = 0
                await self.db.commit()
                await self.db.refresh(document)
                return document

            chunk_objs = []
            for chunk_data in chunks:
                chunk = KnowledgeChunk(
                    document_id=document.id,
                    content=chunk_data["content"],
                    embedding=None,
                    chunk_index=chunk_data["index"],
                    start_pos=chunk_data["start_pos"],
                    end_pos=chunk_data["end_pos"],
                    meta_data={"strategy": self.chunker.strategy},
                )
                self.db.add(chunk)
                chunk_objs.append(chunk)

            await self.db.flush()
            document.status = DocumentStatus.COMPLETED.value
            document.chunk_count = len(chunks)
            await self.db.commit()
            await self.db.refresh(document)

            if self.embedding_service.is_available and chunk_objs:
                chunk_ids = [c.id for c in chunk_objs]
                chunk_texts = [c.content for c in chunk_objs]
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._embed_chunks(chunk_ids, chunk_texts))
                except Exception:
                    pass

            return document

        except Exception as e:
            document.status = DocumentStatus.FAILED.value
            document.error_message = str(e)
            await self.db.commit()
            raise RuntimeError(f"Document reindex failed: {str(e)}")

    async def _embed_chunks(self, chunk_ids: List[str], texts: List[str]) -> None:
        """
        后台补全向量：使用独立数据库会话，避免阻塞上传响应，也不受主请求会话生命周期影响。
        向量生成失败仅记录日志，已保存的文本块仍可通过关键词检索（系统级 RAG 降级可用）。
        """
        try:
            import logging
            logger = logging.getLogger("app.services.rag_engine")
            from app.db.session import async_session_maker

            embeddings = await self.embedding_service.embed(texts)
            async with async_session_maker() as s:
                res = await s.execute(
                    select(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids))
                )
                objs = {o.id: o for o in res.scalars().all()}
                for cid, emb in zip(chunk_ids, embeddings):
                    if cid in objs:
                        objs[cid].embedding = emb
                await s.commit()
        except Exception as e:
            try:
                import logging
                logging.getLogger("app.services.rag_engine").warning(
                    "后台向量化失败，已回退关键词搜索: %s", e
                )
            except Exception:
                pass

    async def search(
        self,
        kb_id: str,
        query: str,
        top_k: int = 5,
        use_embedding: bool = True,
        mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        在知识库中搜索相关片段。

        SAG 模式（默认，RAG_MODE=sag）：实体抽取 -> SQL ILIKE 候选过滤(含文档标题路由)
        -> 向量重排，缩小向量计算候选集并校正跨文档路由；任何异常自动降级朴素向量。
        naive 模式（RAG_MODE=naive 或显式 mode="naive"）：走原 O(N) 余弦 / SQL 最近邻。

        PostgreSQL 下走 SQL 层最近邻（pgvector），SQLite 下保持原 JSON 列 + Python 余弦。
        """
        # 模式解析：默认读环境变量 RAG_MODE（sag），可显式覆盖；naive 强制朴素
        if mode is None:
            mode = os.getenv("RAG_MODE", "sag").lower()
        sag_on = (
            mode == "sag"
            and use_embedding
            and self.embedding_service.is_available
        )

        if is_postgres():
            if sag_on:
                try:
                    ef = self._sag_entity_filter(self._extract_entities(query))
                    if ef is not None:
                        res = await self._embedding_search_pg(
                            query, kb_id, top_k, extra_filter=ef
                        )
                        for r in res:
                            r["search_method"] = "sag"
                        return res
                except Exception:
                    logging.getLogger("app.services.rag_engine").warning(
                        "SAG(pg) 失败，降级朴素向量", exc_info=True
                    )
            if use_embedding and self.embedding_service.is_available:
                try:
                    return await self._embedding_search_pg(query, kb_id, top_k)
                except Exception:
                    pass
            return await self._keyword_search_pg(query, kb_id, top_k)

        # ---- SQLite 路径 ----
        if sag_on:
            try:
                ef = self._sag_entity_filter(self._extract_entities(query))
                if ef is not None:
                    result = await self.db.execute(
                        select(
                            KnowledgeChunk,
                            KnowledgeDocument.id.label("doc_id"),
                            KnowledgeDocument.title.label("doc_title"),
                        )
                        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                        .where(
                            and_(
                                KnowledgeDocument.kb_id == kb_id,
                                KnowledgeDocument.status == DocumentStatus.COMPLETED.value,
                                ef,
                            )
                        )
                    )
                    rows = result.all()
                    if rows:
                        chunks = []
                        documents = {}
                        # ⚠️ 只取 doc id/title，绝不加载 doc.content（文档全文可能数 MB，
                        # JOIN 按行重复携带 → 3115 行 × 6.7MB ≈ 20GB 传输，卡死 + OOM。
                        # 2026-08-08 定位修复）
                        for chunk, doc_id, doc_title in rows:
                            chunks.append(chunk)
                            documents[chunk.document_id] = SimpleNamespace(title=doc_title)
                        res = await self._embedding_search(query, chunks, documents, top_k)
                        for r in res:
                            r["search_method"] = "sag"
                        return res
            except Exception:
                logging.getLogger("app.services.rag_engine").warning(
                    "SAG(sqlite) 失败，降级朴素向量", exc_info=True
                )

        # ---- 朴素路径（原实现，向后兼容）----
        # 获取知识库的所有chunks（⚠️ 只取 doc id/title，不加载 doc.content 全文，
        # JOIN 按行重复携带会致 3115 行 × 数 MB ≈ 20GB 传输卡死 + OOM，2026-08-08 修复）
        result = await self.db.execute(
            select(
                KnowledgeChunk,
                KnowledgeDocument.id.label("doc_id"),
                KnowledgeDocument.title.label("doc_title"),
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                and_(
                    KnowledgeDocument.kb_id == kb_id,
                    KnowledgeDocument.status == DocumentStatus.COMPLETED.value,
                )
            )
        )
        rows = result.all()

        if not rows:
            return []

        chunks = []
        documents = {}
        for chunk, doc_id, doc_title in rows:
            chunks.append(chunk)
            documents[chunk.document_id] = SimpleNamespace(title=doc_title)

        # 优先使用embedding搜索
        if use_embedding and self.embedding_service.is_available:
            try:
                return await self._embedding_search(query, chunks, documents, top_k)
            except Exception:
                # Embedding搜索失败，降级到关键词匹配
                pass

        # 关键词匹配降级
        return await self._keyword_search(query, chunks, documents, top_k)

    # ---------- SAG 辅助方法 ----------
    def _extract_entities(self, query: str) -> List[str]:
        """实体抽取：泛化词法（CJK 2~3 字 n-gram + 拉丁词）+ 领域词表增强；不依赖 LLM。
        返回用于 SQL ILIKE 过滤的实体 term 列表（词表优先，截断 16 个以保留聚焦过滤）。"""
        q = (query or "").strip()
        if not q:
            return []
        terms: set = set()
        # 拉丁词（含 + # . 等，保留术语 token）
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_+#./-]*", q):
            w = w.strip().lower()
            if len(w) >= 2:
                terms.add(w)
        # CJK 2~3 字 n-gram（丢弃整段超长串与 4-gram，避免过滤过宽）
        for run in re.findall(r"[\u4e00-\u9fff]+", q):
            for n in (3, 2):
                for i in range(len(run) - n + 1):
                    terms.add(run[i:i + n].lower())
        # 领域词表增强（优先：命中即强实体）
        ql = q.lower()
        for g in _SAG_GLOSSARY:
            if g.lower() in ql:
                terms.add(g.lower())
        # 去停用词与超短项
        terms = {t for t in terms if t not in _SAG_STOPWORDS and len(t) >= 2}
        # 优先长词（更具体的实体），截断到 16 个
        ranked = sorted(terms, key=lambda t: (-len(t), t))
        return ranked[:16]

    def _sag_entity_filter(self, entities: List[str]):
        """由实体构造 SQL ILIKE 过滤条件（chunk.content 或 doc.title/file_name 命中即候选）。
        无实体时返回 None（调用方跳过 SAG，走朴素）。"""
        if not entities:
            return None
        conds = []
        for e in entities:
            pat = f"%{e}%"
            conds.append(KnowledgeChunk.content.ilike(pat))
            conds.append(KnowledgeDocument.title.ilike(pat))
            conds.append(KnowledgeDocument.file_name.ilike(pat))
        return or_(*conds)

    async def _embedding_search_pg(
        self,
        query: str,
        kb_id: str,
        top_k: int,
        extra_filter=None,
    ) -> List[Dict[str, Any]]:
        """PostgreSQL/pgvector 语义检索：SQL 层最近邻，仅取 top_k 行。
        extra_filter: SAG 实体 SQL 过滤条件（可选），注入候选集缩小范围。
        """
        q_emb = await self.embedding_service.embed_single(query)
        # 用 pgvector 的余弦距离运算符 <=> （pgvector 0.2.x 未导出 cosine_distance 函数）
        dist = KnowledgeChunk.embedding.op("<=>")(q_emb)
        where_clauses = [
            KnowledgeDocument.kb_id == kb_id,
            KnowledgeDocument.status == DocumentStatus.COMPLETED.value,
        ]
        if extra_filter is not None:
            where_clauses.append(extra_filter)
        result = await self.db.execute(
            select(
                KnowledgeChunk.id,
                KnowledgeChunk.document_id,
                KnowledgeChunk.content,
                KnowledgeChunk.chunk_index,
                KnowledgeDocument.title,
                cast(dist, Float).label("distance"),
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(and_(*where_clauses))
            .order_by(dist)
            .limit(top_k)
        )
        rows = result.all()
        out = []
        for r in rows:
            d = r.distance if r.distance is not None else 1.0
            out.append({
                "chunk_id": r.id,
                "document_id": r.document_id,
                "document_title": r.title or "",
                "content": r.content,
                "score": float(max(0.0, 1.0 - d)),
                "chunk_index": r.chunk_index,
                "search_method": "embedding",
            })
        return out

    async def _keyword_search_pg(
        self,
        query: str,
        kb_id: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """PostgreSQL 关键词降级：SQL ILIKE（避免整库拉取）。"""
        terms = [
            w for w in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}|\d{2,}", query.lower())
        ][:5]
        if not terms:
            return []
        cond = or_(*[KnowledgeChunk.content.ilike(f"%{t}%") for t in terms])
        result = await self.db.execute(
            select(
                KnowledgeChunk.id,
                KnowledgeChunk.document_id,
                KnowledgeChunk.content,
                KnowledgeChunk.chunk_index,
                KnowledgeDocument.title,
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                and_(
                    KnowledgeDocument.kb_id == kb_id,
                    KnowledgeDocument.status == DocumentStatus.COMPLETED.value,
                    cond,
                )
            )
            .limit(top_k)
        )
        return [
            {
                "chunk_id": r.id,
                "document_id": r.document_id,
                "document_title": r.title or "",
                "content": r.content,
                "score": 0.5,
                "chunk_index": r.chunk_index,
                "search_method": "keyword",
            }
            for r in result.all()
        ]

    async def _embedding_search(
        self,
        query: str,
        chunks: List[KnowledgeChunk],
        documents: Dict[str, KnowledgeDocument],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """基于向量的语义搜索"""
        query_embedding = await self.embedding_service.embed_single(query)

        # 计算余弦相似度
        scored_chunks = []
        for chunk in chunks:
            if chunk.embedding:
                similarity = self._cosine_similarity(query_embedding, chunk.embedding)
                scored_chunks.append((chunk, similarity))

        # 排序并返回top_k
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        results = []
        for chunk, score in scored_chunks[:top_k]:
            doc = documents.get(chunk.document_id)
            results.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": doc.title if doc else "",
                "content": chunk.content,
                "score": float(score),
                "chunk_index": chunk.chunk_index,
                "search_method": "embedding",
            })

        return results

    async def _keyword_search(
        self,
        query: str,
        chunks: List[KnowledgeChunk],
        documents: Dict[str, KnowledgeDocument],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """基于关键词的搜索（降级方案）"""
        chunk_texts = [chunk.content for chunk in chunks]
        similarities = self.keyword_matcher.compute_tf_idf_similarity(query, chunk_texts)

        scored_chunks = list(zip(chunks, similarities))
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        results = []
        for chunk, score in scored_chunks[:top_k]:
            doc = documents.get(chunk.document_id)
            results.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": doc.title if doc else "",
                "content": chunk.content,
                "score": float(score),
                "chunk_index": chunk.chunk_index,
                "search_method": "keyword",
            })

        return results

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    async def delete_document(self, doc_id: str) -> bool:
        """
        删除文档及其所有片段
        """
        result = await self.db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            return False

        # 显式删除片段，避免生产库（PostgreSQL）外键约束导致 IntegrityError
        await self.db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        )
        await self.db.delete(document)
        await self.db.commit()
        return True

    async def get_context(
        self,
        query: str,
        kb_ids: List[str],
        top_k: int = 5,
        max_tokens: int = 2000,
    ) -> str:
        """
        获取RAG上下文 - 用于增强LLM生成
        """
        all_results = []

        for kb_id in kb_ids:
            try:
                results = await self.search(kb_id, query, top_k=top_k)
                all_results.extend(results)
            except Exception:
                continue

        # 按分数排序
        all_results.sort(key=lambda x: x["score"], reverse=True)

        # 构建上下文文本
        context_parts = []
        total_length = 0

        for result in all_results[:top_k]:
            part = f"【{result['document_title']}】\n{result['content']}\n\n"
            if total_length + len(part) > max_tokens * 4:  # 粗略估算：1 token ≈ 4 字符
                break
            context_parts.append(part)
            total_length += len(part)

        return "\n".join(context_parts) if context_parts else ""

    async def multi_kb_search(
        self,
        kb_ids: List[str],
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        在多个知识库中搜索
        """
        all_results = []

        for kb_id in kb_ids:
            try:
                results = await self.search(kb_id, query, top_k=top_k)
                for r in results:
                    r["kb_id"] = kb_id
                all_results.extend(results)
            except Exception:
                continue

        # 全局排序
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return all_results[:top_k]

    async def get_document_chunks(self, doc_id: str) -> List[Dict[str, Any]]:
        """获取文档的所有片段"""
        result = await self.db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        chunks = result.scalars().all()
        return [chunk.to_dict() for chunk in chunks]

    async def reindex_document(self, doc_id: str) -> KnowledgeDocument:
        """重新索引文档"""
        result = await self.db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()

        if not document or not document.content:
            raise ValueError("Document not found or has no content")

        # 删除旧chunks
        await self.db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        )

        # 重新分块（content 为原始字节时先抽文本）
        document.status = DocumentStatus.PROCESSING.value
        await self.db.commit()

        try:
            raw = document.content
            if isinstance(raw, (bytes, bytearray)):
                from app.services.doc_parser import extract_text
                text_for_chunk = extract_text(document.file_name or "unnamed", raw) or ""
            else:
                text_for_chunk = raw or ""
            chunks = self.chunker.chunk_text(text_for_chunk)

            embeddings = None
            if self.embedding_service.is_available:
                try:
                    chunk_texts = [c["content"] for c in chunks]
                    embeddings = await self.embedding_service.embed(chunk_texts)
                except Exception:
                    embeddings = None

            for i, chunk_data in enumerate(chunks):
                chunk = KnowledgeChunk(
                    document_id=document.id,
                    content=chunk_data["content"],
                    embedding=embeddings[i] if embeddings else None,
                    chunk_index=chunk_data["index"],
                    start_pos=chunk_data["start_pos"],
                    end_pos=chunk_data["end_pos"],
                )
                self.db.add(chunk)

            document.status = DocumentStatus.COMPLETED.value
            document.chunk_count = len(chunks)
            await self.db.commit()
            await self.db.refresh(document)

            return document

        except Exception as e:
            document.status = DocumentStatus.FAILED.value
            document.error_message = str(e)
            await self.db.commit()
            raise


async def get_rag_engine(db: AsyncSession) -> RAGEngine:
    """获取RAG引擎实例"""
    return RAGEngine(db_session=db)
