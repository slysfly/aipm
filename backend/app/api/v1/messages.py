"""
[PMBOK KA: 沟通管理 (Communications) — 项目消息、团队沟通]
对应PMI第6版标准：项目沟通管理
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import User
from app.models.message import Message, Channel, ChannelMember, MessageReaction
from app.schemas.message import (
    MessageCreate, MessageUpdate, MessageResponse, MessageListResponse,
    ChannelCreate, ChannelUpdate, ChannelResponse, ChannelListResponse,
    ChannelMemberInfo, ReactionCreate, ReadMarkerUpdate, MessageSenderInfo,
    MessageReactionInfo, SuccessResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


async def get_channel_or_404(db: AsyncSession, channel_id: str) -> Channel:
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise NotFoundException(message="频道不存在")
    return channel


async def get_message_or_404(db: AsyncSession, message_id: str) -> Message:
    result = await db.execute(
        select(Message).where(Message.id == message_id, Message.is_deleted == False)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise NotFoundException(message="消息不存在")
    return message


def build_sender_info(user: User) -> MessageSenderInfo:
    return MessageSenderInfo(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
    )


async def build_message_response(db: AsyncSession, message: Message) -> MessageResponse:
    sender_info = None
    if message.sender:
        sender_info = build_sender_info(message.sender)

    reactions = []
    for reaction in message.reactions:
        user_info = None
        if reaction.user:
            user_info = build_sender_info(reaction.user)
        reactions.append(MessageReactionInfo(
            id=reaction.id,
            user_id=reaction.user_id,
            emoji=reaction.emoji,
            user=user_info,
            created_at=reaction.created_at,
        ))

    reply_count = 0
    if hasattr(message, 'replies'):
        reply_count = len(message.replies)

    return MessageResponse(
        id=message.id,
        content=message.content,
        type=message.type,
        sender_id=message.sender_id,
        receiver_id=message.receiver_id,
        channel_id=message.channel_id,
        thread_id=message.thread_id,
        reply_to=message.reply_to,
        mentions=message.mentions or [],
        edited_at=message.edited_at,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        sender=sender_info,
        reactions=reactions,
        reply_count=reply_count,
    )


@router.get("/channels", response_model=ChannelListResponse)
async def list_channels(
    type: Optional[str] = None,
    project_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Channel).join(
        ChannelMember,
        and_(
            ChannelMember.channel_id == Channel.id,
            ChannelMember.user_id == current_user.id
        )
    )

    if type:
        query = query.where(Channel.type == type)
    if project_id:
        query = query.where(Channel.project_id == project_id)

    count_query = select(func.count(Channel.id)).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(desc(Channel.created_at))
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    channels = result.scalars().all()

    channel_list = []
    for channel in channels:
        unread_count = 0
        last_message = None

        member_result = await db.execute(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel.id,
                ChannelMember.user_id == current_user.id
            )
        )
        member = member_result.scalar_one_or_none()

        if member and member.last_read_at:
            unread_result = await db.execute(
                select(func.count(Message.id)).where(
                    Message.channel_id == channel.id,
                    Message.created_at > member.last_read_at,
                    Message.is_deleted == False
                )
            )
            unread_count = unread_result.scalar()

        msg_result = await db.execute(
            select(Message).where(
                Message.channel_id == channel.id,
                Message.is_deleted == False
            ).order_by(desc(Message.created_at)).limit(1)
        )
        last_msg = msg_result.scalar_one_or_none()
        if last_msg:
            last_message = await build_message_response(db, last_msg)

        channel_list.append(ChannelResponse(
            id=channel.id,
            name=channel.name,
            type=channel.type,
            project_id=channel.project_id,
            member_ids=channel.member_ids or [],
            created_by=channel.created_by,
            created_at=channel.created_at,
            unread_count=unread_count,
            last_message=last_message,
        ))

    total_pages = (total + page_size - 1) // page_size
    return ChannelListResponse(
        items=channel_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/channels", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel_in: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    channel = Channel(
        name=channel_in.name,
        type=channel_in.type,
        project_id=channel_in.project_id,
        member_ids=list(set(channel_in.member_ids + [current_user.id])),
        created_by=current_user.id,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    for user_id in channel.member_ids:
        member = ChannelMember(
            channel_id=channel.id,
            user_id=user_id,
            role="owner" if user_id == current_user.id else "member",
        )
        db.add(member)
    await db.commit()

    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        type=channel.type,
        project_id=channel.project_id,
        member_ids=channel.member_ids or [],
        created_by=channel.created_by,
        created_at=channel.created_at,
        unread_count=0,
        last_message=None,
    )


@router.get("/channels/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    channel_id: str,
    before_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    channel = await get_channel_or_404(db, channel_id)

    member_result = await db.execute(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == current_user.id
        )
    )
    if not member_result.scalar_one_or_none():
        raise ValidationException(message="无权访问此频道")

    query = select(Message).where(
        Message.channel_id == channel_id,
        Message.is_deleted == False
    )

    if before_id:
        before_result = await db.execute(
            select(Message.created_at).where(Message.id == before_id)
        )
        before_time = before_result.scalar_one_or_none()
        if before_time:
            query = query.where(Message.created_at < before_time)

    count_query = select(func.count(Message.id)).where(
        Message.channel_id == channel_id,
        Message.is_deleted == False
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(desc(Message.created_at))
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    messages = result.scalars().all()

    message_list = []
    for msg in reversed(messages):
        message_list.append(await build_message_response(db, msg))

    total_pages = (total + page_size - 1) // page_size
    return MessageListResponse(
        items=message_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/channels/{channel_id}/messages", response_model=MessageResponse, status_code=201)
async def create_message(
    channel_id: str,
    message_in: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    channel = await get_channel_or_404(db, channel_id)

    member_result = await db.execute(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == current_user.id
        )
    )
    if not member_result.scalar_one_or_none():
        raise ValidationException(message="无权在此频道发送消息")

    message = Message(
        content=message_in.content,
        type=message_in.type,
        sender_id=current_user.id,
        channel_id=channel_id,
        thread_id=message_in.thread_id,
        reply_to=message_in.reply_to,
        mentions=message_in.mentions,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    return await build_message_response(db, message)


@router.put("/messages/{message_id}", response_model=MessageResponse)
async def update_message(
    message_id: str,
    message_in: MessageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    message = await get_message_or_404(db, message_id)

    if message.sender_id != current_user.id and not current_user.is_superuser:
        raise ValidationException(message="无权编辑此消息")

    update_data = message_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(message, field, value)

    message.edited_at = datetime.now()

    await db.commit()
    await db.refresh(message)

    return await build_message_response(db, message)


@router.delete("/messages/{message_id}", response_model=SuccessResponse)
async def delete_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    message = await get_message_or_404(db, message_id)

    if message.sender_id != current_user.id and not current_user.is_superuser:
        raise ValidationException(message="无权删除此消息")

    message.is_deleted = True
    message.edited_at = datetime.now()

    await db.commit()

    return SuccessResponse(message="消息删除成功")


@router.post("/messages/{message_id}/reactions", response_model=SuccessResponse, status_code=201)
async def add_reaction(
    message_id: str,
    reaction_in: ReactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    message = await get_message_or_404(db, message_id)

    existing = await db.execute(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == current_user.id,
            MessageReaction.emoji == reaction_in.emoji
        )
    )
    if existing.scalar_one_or_none():
        raise ValidationException(message="已添加过此反应")

    reaction = MessageReaction(
        message_id=message_id,
        user_id=current_user.id,
        emoji=reaction_in.emoji,
    )
    db.add(reaction)
    await db.commit()

    return SuccessResponse(message="反应添加成功")


@router.delete("/messages/{message_id}/reactions/{emoji}", response_model=SuccessResponse)
async def remove_reaction(
    message_id: str,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == current_user.id,
            MessageReaction.emoji == emoji
        )
    )
    reaction = result.scalar_one_or_none()
    if not reaction:
        raise NotFoundException(message="反应不存在")

    await db.delete(reaction)
    await db.commit()

    return SuccessResponse(message="反应删除成功")


@router.post("/channels/{channel_id}/members", response_model=SuccessResponse, status_code=201)
async def add_member(
    channel_id: str,
    user_id: str,
    role: str = "member",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    channel = await get_channel_or_404(db, channel_id)

    member_result = await db.execute(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == current_user.id
        )
    )
    current_member = member_result.scalar_one_or_none()
    if not current_member or current_member.role not in ["owner", "admin"]:
        raise ValidationException(message="无权添加成员")

    existing = await db.execute(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == user_id
        )
    )
    if existing.scalar_one_or_none():
        raise ValidationException(message="用户已在频道中")

    new_member = ChannelMember(
        channel_id=channel_id,
        user_id=user_id,
        role=role,
    )
    db.add(new_member)

    if channel.member_ids is None:
        channel.member_ids = []
    if user_id not in channel.member_ids:
        channel.member_ids.append(user_id)

    await db.commit()

    return SuccessResponse(message="成员添加成功")


@router.put("/channels/{channel_id}/read", response_model=SuccessResponse)
async def mark_read(
    channel_id: str,
    read_in: ReadMarkerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    channel = await get_channel_or_404(db, channel_id)

    result = await db.execute(
        select(ChannelMember).where(
            ChannelMember.channel_id == channel_id,
            ChannelMember.user_id == current_user.id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise ValidationException(message="无权访问此频道")

    member.last_read_at = datetime.now()
    await db.commit()

    return SuccessResponse(message="已标记为已读")


@router.get("/channels/{channel_id}/members", response_model=List[ChannelMemberInfo])
async def list_members(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    channel = await get_channel_or_404(db, channel_id)

    result = await db.execute(
        select(ChannelMember).where(ChannelMember.channel_id == channel_id)
    )
    members = result.scalars().all()

    member_list = []
    for member in members:
        user_info = None
        if member.user:
            user_info = build_sender_info(member.user)
        member_list.append(ChannelMemberInfo(
            channel_id=member.channel_id,
            user_id=member.user_id,
            role=member.role,
            joined_at=member.joined_at,
            last_read_at=member.last_read_at,
            user=user_info,
        ))

    return member_list
