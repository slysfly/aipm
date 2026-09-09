"""
实时事件 WebSocket 端点：/api/v1/ws/events/{token}
前端连此端点接收后台任务进度、数据变更、通知等实时事件。
与 IM 的 /ws/{token} 共用 ConnectionManager 类，但用独立的 events_manager 实例，
避免同一用户同时连 IM 与事件通道时连接被互相覆盖。
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.api.v1.ws import get_user_from_token
from app.core.websocket import events_manager

router = APIRouter()


@router.websocket("/ws/events/{token}")
async def events_endpoint(websocket: WebSocket, token: str, db: AsyncSession = Depends(get_db)):
    try:
        user = await get_user_from_token(token, db)
    except Exception:
        await websocket.close(code=4001)
        return

    await events_manager.connect(websocket, user.id)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "heartbeat":
                await events_manager.update_heartbeat(user.id)
                await events_manager.send_to_user(user.id, {"type": "heartbeat_ack"})
    except WebSocketDisconnect:
        await events_manager.disconnect(user.id)
    except Exception:
        await events_manager.disconnect(user.id)
