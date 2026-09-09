"""
PMI中国AI项目管理社区 - 知识库访问控制
统一"当前用户可访问哪些知识库"的逻辑，供知识库各端点、以及
经验教训 AI 生成、仪表盘 AI 建议等系统级 RAG 复用。
可见规则：
  - 创建者本人
  - 系统级分享（share_type=system，提供给整个系统使用）
  - 分享给指定用户（share_type=user, target_id=用户id）
  - 分享给指定用户组（share_type=group, target_id=组id，且当前用户是成员）
超管可访问全部。

为避免与 app.models 的导入顺序耦合，模型在函数中惰性导入。
"""

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession


async def get_accessible_kb_ids(db: AsyncSession, user, scope: str = "mine") -> list:
    """返回当前用户可访问的知识库 id 列表。

    scope:
      - "mine" : 仅自己创建的
      - "all"  : 自己创建的 + 系统分享的 + 分享给我的（超管则返回全部）
    """
    from app.models import KnowledgeBase, KnowledgeBaseShare, UserGroupMember, ShareType

    is_super = getattr(user, "is_superuser", False)

    if scope == "all" and is_super:
        res = await db.execute(select(KnowledgeBase.id))
        return [r[0] for r in res.all()]

    if scope == "mine":
        res = await db.execute(
            select(KnowledgeBase.id).where(KnowledgeBase.created_by == user.id)
        )
        return [r[0] for r in res.all()]

    # scope == "all" 且非超管：可访问集合
    owned = select(KnowledgeBase.id).where(KnowledgeBase.created_by == user.id)
    shares = select(KnowledgeBaseShare.kb_id).where(
        or_(
            KnowledgeBaseShare.share_type == ShareType.SYSTEM.value,
            and_(
                KnowledgeBaseShare.share_type == ShareType.USER.value,
                KnowledgeBaseShare.target_id == user.id,
            ),
            and_(
                KnowledgeBaseShare.share_type == ShareType.GROUP.value,
                KnowledgeBaseShare.target_id.in_(
                    select(UserGroupMember.group_id).where(UserGroupMember.user_id == user.id)
                ),
            ),
        )
    )
    ids = set(r[0] for r in (await db.execute(owned)).all())
    for r in (await db.execute(shares)).all():
        ids.add(r[0])
    return list(ids)


async def _can_access_kb(db: AsyncSession, kb_id: str, user, require_write: bool = False):
    """权限判定。返回：
      - None : 知识库不存在
      - False: 存在但当前用户无权限
      - KnowledgeBase 实例 : 有权限
    """
    from app.models import (
        KnowledgeBase, KnowledgeBaseShare, UserGroupMember, ShareType, SharePermission,
    )

    kb = (
        await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    ).scalar_one_or_none()
    if not kb:
        return None

    if kb.created_by == user.id or getattr(user, "is_superuser", False):
        return kb

    shares = (
        await db.execute(
            select(KnowledgeBaseShare).where(KnowledgeBaseShare.kb_id == kb_id)
        )
    ).scalars().all()

    for s in shares:
        if s.share_type == ShareType.SYSTEM.value:
            if not require_write:
                return kb
        elif s.share_type == ShareType.USER.value and s.target_id == user.id:
            if not require_write or s.permission == SharePermission.WRITE.value:
                return kb
        elif s.share_type == ShareType.GROUP.value:
            member = (
                await db.execute(
                    select(UserGroupMember).where(
                        UserGroupMember.group_id == s.target_id,
                        UserGroupMember.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            if member and (not require_write or s.permission == SharePermission.WRITE.value):
                return kb
    return False


async def resolve_ai_kb(db: AsyncSession, raw_kb_id, user) -> "str | None":
    """解析并校验「AI 生成」使用的知识库（单 scope，requirement 4：公开/私密二选一）。

    - raw_kb_id 为空 / none / null：默认回退到用户可访问的第一个「公开」知识库
      （满足 requirement 3：所有 AI 生成内容首先参照知识库沉淀）。
    - 否则校验 raw_kb_id：公开库任意用户可用；私密库仅创建者可用；超管可用全部。
    返回可用的 kb_id，或 None（本次生成不使用知识库）。
    """
    from app.models.knowledge_base import KnowledgeBase, Visibility

    _none = (None, "", "none", "null", "None", "undefined")
    if raw_kb_id in _none:
        # 默认使用公开知识库（全系统可见，服务所有项目）
        res = await db.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.visibility == Visibility.PUBLIC.value)
            .order_by(KnowledgeBase.created_at)
        )
        kb = res.scalars().first()
        return kb.id if kb else None

    kb = (
        await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == raw_kb_id))
    ).scalar_one_or_none()
    if not kb:
        return None
    if (
        kb.visibility == Visibility.PUBLIC.value
        or kb.created_by == user.id
        or getattr(user, "is_superuser", False)
    ):
        return kb.id
    # 私密库仅创建者本人可用于 AI 生成
    return None
