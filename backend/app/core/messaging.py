"""
PMI中国AI项目管理社区 - 消息队列系统
基于 Redis Streams 实现轻量级消息队列；当 REDIS_URL 为 memory:// 时自动降级为进程内内存队列。
"""

import json
import asyncio
import time
import logging
from typing import Callable, Dict, Any, Optional, List, Awaitable
from datetime import datetime

import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)

# 支持的队列名称
QUEUE_STREAMS = {
    "email_queue": "queue:email",
    "notification_queue": "queue:notification",
    "report_queue": "queue:report",
    "webhook_queue": "queue:webhook",
}

# 退避与死信配置（F7/F8）
BACKOFF_MAX_RETRIES = 5        # 最大重试次数
BACKOFF_BASE_DELAY = 1.0       # 基础退避（秒）
BACKOFF_CAP = 30.0             # 退避上限（秒）
ACK_FAIL_THRESHOLD = 3         # ack 连续失败阈值：超过则直接死信，避免消息永久滞留 PEL


class MessageQueue:
    """消息队列：Redis Streams 或内存模式"""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._consumers: Dict[str, asyncio.Task] = {}
        self._running = False
        # 内存模式：REDIS_URL 以 memory:// 开头时使用进程内队列
        self._mode = "memory" if str(settings.REDIS_URL).startswith("memory://") else "redis"
        self._memory_queues: Dict[str, "asyncio.Queue"] = {}
        # 在途退避重投任务集合（停机时统一取消，避免悬挂）
        self._retry_tasks: set = set()
        # 内存模式死信存储
        self._dead_letters: Dict[str, List[Dict[str, Any]]] = {}
        # ack 连续失败计数（Redis 模式）：key=msg_id，跨 PEL 自然重投保持累计
        self._ack_fail_counts: Dict[str, int] = {}

    async def _get_redis(self) -> redis.Redis:
        """获取 Redis 连接（仅 redis 模式）"""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
            )
        return self._redis

    async def publish(self, stream: str, message: Dict[str, Any]) -> str:
        """发布消息到指定 Stream"""
        message["_published_at"] = datetime.now().isoformat()
        message["_stream"] = stream

        if self._mode == "memory":
            queue = self._memory_queues.setdefault(stream, asyncio.Queue())
            message_id = f"mem-{int(time.time() * 1000)}-{queue.qsize()}"
            wrapped = {"_id": message_id, **message}
            await queue.put(wrapped)
            logger.info(f"消息已发布(内存)到 {stream}: {message_id}")
            return message_id

        r = await self._get_redis()
        stream_key = QUEUE_STREAMS.get(stream, stream)
        payload = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in message.items()}
        message_id = await r.xadd(stream_key, payload)
        logger.info(f"消息已发布到 {stream}: {message_id}")
        return message_id

    async def create_consumer_group(self, stream: str, group: str) -> bool:
        """创建消费者组（内存模式无需分组，直接返回 True）"""
        if self._mode == "memory":
            return True

        r = await self._get_redis()
        stream_key = QUEUE_STREAMS.get(stream, stream)
        try:
            await r.xgroup_create(stream_key, group, id="0", mkstream=True)
            logger.info(f"消费者组创建成功: {group} @ {stream}")
            return True
        except redis.ResponseError as e:
            if "already exists" in str(e):
                logger.debug(f"消费者组已存在: {group} @ {stream}")
                return True
            logger.error(f"创建消费者组失败: {e}")
            return False

    async def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
        callback: Callable[[Dict[str, Any]], Awaitable[bool]],
        block_ms: int = 5000,
        count: int = 10,
    ) -> None:
        """消费者组订阅消息"""
        if self._mode == "memory":
            queue = self._memory_queues.setdefault(stream, asyncio.Queue())
            logger.info(f"内存模式消费者启动: {consumer} @ {stream}")
            self._running = True
            while self._running:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=block_ms / 1000.0)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    logger.info(f"消费者取消: {consumer}")
                    break
                try:
                    success = await callback(message)
                except Exception as e:
                    logger.error(f"消息处理异常 {message.get('_id')}: {e}", exc_info=True)
                    success = False
                if not success:
                    # 失败进入退避重试；超过上限进入死信（内存模式）
                    await self._handle_failure_memory(stream, message)
            return

        r = await self._get_redis()
        stream_key = QUEUE_STREAMS.get(stream, stream)
        await self.create_consumer_group(stream, group)
        logger.info(f"消费者启动: {consumer} in {group} @ {stream}")
        self._running = True

        while self._running:
            try:
                pending = await r.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream_key: "0"},
                    count=count,
                    block=block_ms,
                )
                new_messages = await r.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream_key: ">"},
                    count=count,
                    block=block_ms,
                )
                all_messages = pending + new_messages
                for stream_name, msgs in all_messages:
                    for msg_id, fields in msgs:
                        message = {"_id": msg_id}
                        try:
                            message = {
                                "_id": msg_id,
                                **{k: self._deserialize(v) for k, v in fields.items()},
                            }
                            success = await callback(message)
                        except Exception as e:
                            logger.error(f"消息处理异常 {msg_id}: {e}", exc_info=True)
                            # 回调异常也走退避重试 / 死信
                            await self._handle_failure(stream, group, msg_id, message)
                            continue
                        if success:
                            await self.ack(stream, group, msg_id)
                        else:
                            # 处理返回失败：退避重试；超过上限进死信
                            await self._handle_failure(stream, group, msg_id, message)
            except asyncio.CancelledError:
                logger.info(f"消费者取消: {consumer}")
                break
            except Exception as e:
                logger.error(f"消费者异常: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def ack(self, stream: str, group: str, message_id: str) -> bool:
        """确认消息已处理（内存模式无需确认）"""
        if self._mode == "memory":
            return True

        r = await self._get_redis()
        stream_key = QUEUE_STREAMS.get(stream, stream)
        try:
            await r.xack(stream_key, group, message_id)
            logger.debug(f"消息已确认: {message_id}")
            return True
        except Exception as e:
            logger.error(f"消息确认失败 {message_id}: {e}")
            return False

    async def get_pending_messages(
        self, stream: str, group: str, count: int = 100
    ) -> List[Dict[str, Any]]:
        """获取待处理消息列表（内存模式返回空）"""
        if self._mode == "memory":
            return []

        r = await self._get_redis()
        stream_key = QUEUE_STREAMS.get(stream, stream)
        try:
            pending = await r.xpending_range(stream_key, group, min="-", max="+", count=count)
            return [
                {
                    "id": p["message_id"],
                    "consumer": p["consumer"],
                    "idle_time": p["time_since_delivered"],
                    "delivery_count": p["times_delivered"],
                }
                for p in pending
            ]
        except Exception as e:
            logger.error(f"获取待处理消息失败: {e}")
            return []

    async def get_stream_info(self, stream: str) -> Dict[str, Any]:
        """获取 Stream 信息（内存模式返回概要）"""
        if self._mode == "memory":
            q = self._memory_queues.get(stream)
            return {
                "mode": "memory",
                "length": q.qsize() if q else 0,
                "groups": 0,
                "last_generated_id": "",
                "first_entry": None,
                "last_entry": None,
            }

        r = await self._get_redis()
        stream_key = QUEUE_STREAMS.get(stream, stream)
        try:
            info = await r.xinfo_stream(stream_key)
            return {
                "length": info.get("length", 0),
                "radix_tree_keys": info.get("radix-tree-keys", 0),
                "radix_tree_nodes": info.get("radix-tree-nodes", 0),
                "groups": info.get("groups", 0),
                "last_generated_id": info.get("last-generated-id", ""),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
            }
        except Exception as e:
            logger.error(f"获取 Stream 信息失败: {e}")
            return {}

    @staticmethod
    def _compute_backoff(retries: int) -> float:
        """指数退避：base * 2^(n-1)，封顶 cap。retries 从 1 开始。"""
        return min(BACKOFF_BASE_DELAY * (2 ** (retries - 1)), BACKOFF_CAP)

    async def _dead_letter(self, stream: str, message: Dict[str, Any], reason: str) -> None:
        """将消息移入死信（Redis 写入 queue:dead_letter:<stream> 流；内存模式存入列表）。"""
        message = dict(message)
        message["_dead_letter"] = True
        message["_dead_reason"] = reason
        message["_dead_at"] = datetime.now().isoformat()
        if self._mode == "memory":
            self._dead_letters.setdefault(stream, []).append(message)
            logger.error(f"消息进入死信(内存) stream={stream} reason={reason} id={message.get('_id')}")
            return
        try:
            r = await self._get_redis()
            stream_key = f"queue:dead_letter:{stream}"
            payload = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in message.items()}
            await r.xadd(stream_key, payload)
            logger.error(f"消息进入死信(Redis) stream={stream} reason={reason} id={message.get('_id')}")
        except Exception as e:
            logger.error(f"写入死信失败 stream={stream}: {e}")

    def _schedule_retry(self, stream: str, message: Dict[str, Any], delay: float) -> None:
        """安排一次延迟重投（退避期间不持有任何 DB/Redis 连接；任务由事件循环调度）。"""
        task = asyncio.create_task(self._republish_after(stream, message, delay))
        self._retry_tasks.add(task)
        task.add_done_callback(self._retry_tasks.discard)

    async def _republish_after(self, stream: str, message: Dict[str, Any], delay: float) -> None:
        """退避等待后重新发布消息，使其被正常消费；若停机则转入死信避免丢失。"""
        try:
            await asyncio.sleep(delay)
            if not self._running:
                await self._dead_letter(stream, message, "worker_stopped_during_backoff")
                return
            message.pop("_retry_after", None)
            await self.publish(stream, message)
        except asyncio.CancelledError:
            await self._dead_letter(stream, message, "retry_cancelled")
        except Exception as e:
            logger.error(f"退避重投失败 stream={stream}: {e}", exc_info=True)
            await self._dead_letter(stream, message, "retry_republish_failed")

    async def _handle_failure(self, stream: str, group: str, msg_id: str, message: Dict[str, Any]) -> None:
        """Redis 模式失败处理：指数退避重投；超上限则确认并转入死信。

        新增 ack 失败兜底：当 self.ack() 返回 False 时，累计计数到 _ack_fail_counts
        （按 msg_id 跟踪，跨 PEL 自然重投保持累计；并在 message["_ack_fail_count"] 上
        落戳以便观测）。连续失败超过 ACK_FAIL_THRESHOLD 时直接转入死信止血；
        否则保留在 PEL 依赖 Redis 自然重投（现状），仅补 logger.warning。
        正常退避重投主路径（ack 成功时）保持不变。
        """
        retries = int(message.get("_retry_count", 0)) + 1
        if retries > BACKOFF_MAX_RETRIES:
            await self.ack(stream, group, msg_id)
            await self._dead_letter(stream, message, "max_retries_exceeded")
            return
        delay = self._compute_backoff(retries)
        # 先确认原消息移出 PEL，避免被 pending 立即再次投递造成重复处理
        acked = await self.ack(stream, group, msg_id)
        if not acked:
            # ack 失败兜底：累计计数（跨 PEL 自然重投保持）
            self._ack_fail_counts[msg_id] = self._ack_fail_counts.get(msg_id, 0) + 1
            fail_count = self._ack_fail_counts[msg_id]
            message["_ack_fail_count"] = fail_count
            if fail_count > ACK_FAIL_THRESHOLD:
                # 连续 ack 失败超阈值：直接死信，避免消息永久滞留 PEL
                logger.error(
                    f"消息 ack 连续失败超阈值({ACK_FAIL_THRESHOLD})，转入死信 "
                    f"stream={stream} id={msg_id} reason=ack_failed"
                )
                await self._dead_letter(stream, message, "ack_failed")
                self._ack_fail_counts.pop(msg_id, None)
                return
            # 未超阈值：保留在 PEL 依赖 Redis 自然重投（现状），仅告警
            logger.warning(
                f"消息处理失败且 ack 失败（第 {fail_count}/{ACK_FAIL_THRESHOLD} 次），"
                f"保留在 PEL 依赖 Redis 自然重投 stream={stream} id={msg_id}"
            )
            return
        # ack 成功：清除连续 ack 失败计数，正常走退避重投主路径
        self._ack_fail_counts.pop(msg_id, None)
        message["_retry_count"] = retries
        message["_last_error_at"] = datetime.now().isoformat()
        self._schedule_retry(stream, message, delay)
        logger.warning(
            f"消息处理失败，已安排退避重投 stream={stream} id={msg_id} "
            f"retry={retries}/{BACKOFF_MAX_RETRIES} delay={delay:.1f}s"
        )

    async def _handle_failure_memory(self, stream: str, message: Dict[str, Any]) -> None:
        """内存模式失败处理：指数退避重投（重新入队）；超上限进死信。"""
        retries = int(message.get("_retry_count", 0)) + 1
        if retries > BACKOFF_MAX_RETRIES:
            await self._dead_letter(stream, message, "max_retries_exceeded")
            return
        delay = self._compute_backoff(retries)
        message["_retry_count"] = retries
        message["_last_error_at"] = datetime.now().isoformat()
        self._schedule_retry(stream, message, delay)
        logger.warning(
            f"消息处理失败，已安排退避重投(内存) stream={stream} id={message.get('_id')} "
            f"retry={retries}/{BACKOFF_MAX_RETRIES} delay={delay:.1f}s"
        )

    async def get_dead_letters(self, stream: str) -> List[Dict[str, Any]]:
        """获取死信消息。

        内存模式：返回 self._dead_letters 中的列表副本。
        Redis 模式：读取 queue:dead_letter:<stream> 流并反序列化（复用 _deserialize）。
        """
        if self._mode == "memory":
            return list(self._dead_letters.get(stream, []))
        # Redis 模式：从死信流读取全部条目并反序列化
        try:
            r = await self._get_redis()
            stream_key = f"queue:dead_letter:{stream}"
            entries = await r.xrange(stream_key, "-", "+")
            result: List[Dict[str, Any]] = []
            for entry_id, fields in entries:
                msg = {k: self._deserialize(v) for k, v in fields.items()}
                msg["_id"] = entry_id
                result.append(msg)
            return result
        except Exception as e:
            logger.error(f"读取死信失败 stream={stream}: {e}")
            return []

    async def stop(self):
        """停止所有消费者"""
        self._running = False
        for name, task in self._consumers.items():
            task.cancel()
            logger.info(f"消费者任务已取消: {name}")
        self._consumers.clear()

        # 取消在途的退避重投任务，避免进程退出时悬挂
        for t in list(self._retry_tasks):
            t.cancel()
        self._retry_tasks.clear()

        if self._redis:
            await self._redis.close()
            self._redis = None

    @staticmethod
    def _deserialize(value: Any) -> Any:
        """反序列化字段值"""
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value


# 全局消息队列实例
message_queue = MessageQueue()
