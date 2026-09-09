"""
[PMBOK KA: 沟通管理 (Communications) — WebSocket实时通信]
对应PMI第6版标准：实时通信
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.db.session import get_db
from app.models import User
from app.models.message import Message, Channel, ChannelMember
from app.core.websocket import manager
from app.core.security import decode_token

router = APIRouter()


async def get_user_from_token(token: str, db: AsyncSession) -> User:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("无效token")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("用户不存在")
    return user


@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str, db: AsyncSession = Depends(get_db)):
    try:
        user = await get_user_from_token(token, db)
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, user.id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                await manager.update_heartbeat(user.id)
                await manager.send_to_user(user.id, {"type": "heartbeat_ack"})

            elif msg_type == "join_channel":
                channel_id = data.get("channel_id")
                if channel_id:
                    result = await db.execute(
                        select(ChannelMember).where(
                            ChannelMember.channel_id == channel_id,
                            ChannelMember.user_id == user.id
                        )
                    )
                    if result.scalar_one_or_none():
                        await manager.join_channel(user.id, channel_id)

            elif msg_type == "leave_channel":
                channel_id = data.get("channel_id")
                if channel_id:
                    await manager.leave_channel(user.id, channel_id)

            elif msg_type == "message":
                channel_id = data.get("channel_id")
                content = data.get("content", "").strip()
                msg_type_str = data.get("msg_type", "text")
                reply_to = data.get("reply_to")
                mentions = data.get("mentions", [])

                if not channel_id or not content:
                    continue

                result = await db.execute(
                    select(ChannelMember).where(
                        ChannelMember.channel_id == channel_id,
                        ChannelMember.user_id == user.id
                    )
                )
                if not result.scalar_one_or_none():
                    continue

                message = Message(
                    content=content,
                    type=msg_type_str,
                    sender_id=user.id,
                    channel_id=channel_id,
                    reply_to=reply_to,
                    mentions=mentions,
                )
                db.add(message)
                await db.commit()
                await db.refresh(message)

                await manager.broadcast_to_channel(channel_id, {
                    "type": "new_message",
                    "message": {
                        "id": message.id,
                        "content": message.content,
                        "type": message.type,
                        "sender_id": message.sender_id,
                        "channel_id": message.channel_id,
                        "reply_to": message.reply_to,
                        "mentions": message.mentions,
                        "created_at": message.created_at.isoformat(),
                        "sender": {
                            "id": user.id,
                            "username": user.username,
                            "full_name": user.full_name,
                            "avatar_url": user.avatar_url,
                        }
                    }
                })

            elif msg_type == "typing":
                channel_id = data.get("channel_id")
                is_typing = data.get("is_typing", True)
                if channel_id:
                    await manager.broadcast_typing(channel_id, user.id, is_typing)

            elif msg_type == "read":
                channel_id = data.get("channel_id")
                message_id = data.get("message_id")
                if channel_id:
                    result = await db.execute(
                        select(ChannelMember).where(
                            ChannelMember.channel_id == channel_id,
                            ChannelMember.user_id == user.id
                        )
                    )
                    member = result.scalar_one_or_none()
                    if member:
                        member.last_read_at = datetime.now()
                        await db.commit()

                    await manager.broadcast_to_channel(channel_id, {
                        "type": "read_receipt",
                        "channel_id": channel_id,
                        "user_id": user.id,
                        "message_id": message_id,
                    })

            elif msg_type == "private_message":
                receiver_id = data.get("receiver_id")
                content = data.get("content", "").strip()
                if receiver_id and content:
                    message = Message(
                        content=content,
                        type="text",
                        sender_id=user.id,
                        receiver_id=receiver_id,
                    )
                    db.add(message)
                    await db.commit()

                    await manager.send_private_message(user.id, receiver_id, {
                        "type": "new_private_message",
                        "message": {
                            "id": message.id,
                            "content": message.content,
                            "type": message.type,
                            "sender_id": message.sender_id,
                            "receiver_id": message.receiver_id,
                            "created_at": message.created_at.isoformat(),
                            "sender": {
                                "id": user.id,
                                "username": user.username,
                                "full_name": user.full_name,
                                "avatar_url": user.avatar_url,
                            }
                        }
                    })

    except WebSocketDisconnect:
        await manager.disconnect(user.id)
    except Exception:
        await manager.disconnect(user.id)
