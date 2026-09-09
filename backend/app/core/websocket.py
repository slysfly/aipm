import asyncio
import json
from typing import Dict, Set, Optional
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        self.user_connections: Dict[str, WebSocket] = {}
        self.channel_subscribers: Dict[str, Set[str]] = {}
        self.user_channels: Dict[str, Set[str]] = {}
        self.online_users: Set[str] = set()
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self.last_heartbeat: Dict[str, datetime] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.user_connections[user_id] = websocket
        self.online_users.add(user_id)
        self.user_channels[user_id] = set()
        self.last_heartbeat[user_id] = datetime.now()
        self.heartbeat_tasks[user_id] = asyncio.create_task(
            self._heartbeat_check(user_id)
        )
        await self.broadcast_user_status(user_id, "online")

    async def disconnect(self, user_id: str):
        if user_id in self.heartbeat_tasks:
            self.heartbeat_tasks[user_id].cancel()
            del self.heartbeat_tasks[user_id]

        if user_id in self.user_channels:
            for channel_id in list(self.user_channels[user_id]):
                await self.leave_channel(user_id, channel_id)
            del self.user_channels[user_id]

        if user_id in self.user_connections:
            del self.user_connections[user_id]

        if user_id in self.online_users:
            self.online_users.remove(user_id)

        if user_id in self.last_heartbeat:
            del self.last_heartbeat[user_id]

        await self.broadcast_user_status(user_id, "offline")

    async def _heartbeat_check(self, user_id: str):
        try:
            while True:
                await asyncio.sleep(30)
                if user_id not in self.last_heartbeat:
                    break
                elapsed = (datetime.now() - self.last_heartbeat[user_id]).total_seconds()
                if elapsed > 120:
                    await self.disconnect(user_id)
                    break
        except asyncio.CancelledError:
            pass

    async def update_heartbeat(self, user_id: str):
        self.last_heartbeat[user_id] = datetime.now()

    async def join_channel(self, user_id: str, channel_id: str):
        if channel_id not in self.channel_subscribers:
            self.channel_subscribers[channel_id] = set()
        self.channel_subscribers[channel_id].add(user_id)
        self.user_channels[user_id].add(channel_id)

        await self.send_to_user(user_id, {
            "type": "channel_joined",
            "channel_id": channel_id,
        })

    async def leave_channel(self, user_id: str, channel_id: str):
        if channel_id in self.channel_subscribers:
            self.channel_subscribers[channel_id].discard(user_id)
            if not self.channel_subscribers[channel_id]:
                del self.channel_subscribers[channel_id]
        if user_id in self.user_channels:
            self.user_channels[user_id].discard(channel_id)

    async def broadcast_to_channel(self, channel_id: str, message: dict):
        if channel_id not in self.channel_subscribers:
            return
        disconnected = []
        for user_id in self.channel_subscribers[channel_id]:
            try:
                await self.send_to_user(user_id, message)
            except Exception:
                disconnected.append(user_id)
        for user_id in disconnected:
            await self.disconnect(user_id)

    async def send_to_user(self, user_id: str, message: dict):
        if user_id not in self.user_connections:
            return
        websocket = self.user_connections[user_id]
        await websocket.send_json(message)

    async def send_private_message(self, sender_id: str, receiver_id: str, message: dict):
        message["is_private"] = True
        message["sender_id"] = sender_id
        await self.send_to_user(receiver_id, message)

    async def broadcast_user_status(self, user_id: str, status: str):
        message = {
            "type": "user_status",
            "user_id": user_id,
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }
        for uid in self.online_users:
            if uid != user_id:
                await self.send_to_user(uid, message)

    async def broadcast_typing(self, channel_id: str, user_id: str, is_typing: bool):
        if channel_id not in self.channel_subscribers:
            return
        message = {
            "type": "typing",
            "channel_id": channel_id,
            "user_id": user_id,
            "is_typing": is_typing,
        }
        for uid in self.channel_subscribers[channel_id]:
            if uid != user_id:
                await self.send_to_user(uid, message)

    def is_online(self, user_id: str) -> bool:
        return user_id in self.online_users

    def get_online_users(self) -> Set[str]:
        return self.online_users.copy()

    def get_channel_users(self, channel_id: str) -> Set[str]:
        return self.channel_subscribers.get(channel_id, set()).copy()


manager = ConnectionManager()

# ── 事件总线（与 IM 的 manager 分离，避免同一用户的多条 WS 连接互相覆盖）──
# 用于「后台异步任务进度 / 数据变更 / 通知」等实时推送。
events_manager = ConnectionManager()


async def publish_event(user_id: str, event: dict):
    """向特定用户推送事件（任务进度 / 完成 / 通知等）"""
    await events_manager.send_to_user(user_id, event)


async def publish_to_all(event: dict):
    """向所有在线用户广播事件（多用户协作 / 数据变更同步）"""
    for uid in list(events_manager.online_users):
        try:
            await events_manager.send_to_user(uid, event)
        except Exception:
            pass
