"""
PMI中国AI项目管理社区 - 知识库分享 / 用户组 / 多格式批量上传
[CPMAI Phase: Data Understanding | Domain: Data for AI — 知识共享与多格式数据接入]
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.knowledge_base import (
    KnowledgeBase, KnowledgeBaseShare, UserGroup, UserGroupMember,
    ShareType, SharePermission,
)
from app.services.kb_access import _can_access_kb
from app.services.rag_engine import RAGEngine
from app.services.doc_parser import extract_text, is_supported

router = APIRouter()


# ============== 用户列表（分享选择器） ==============

class UserLite(BaseModel):
    id: str
    username: str
    full_name: Optional[str]
    email: Optional[str]
    department: Optional[str]

    class Config:
        from_attributes = True


@router.get("/kb-users", response_model=List[UserLite])
async def list_users_for_share(
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出可用于分享的用户（同组织优先，超管看全部）。"""
    stmt = select(User).where(User.id != current_user.id, User.is_active.is_(True))
    if not getattr(current_user, "is_superuser", False) and getattr(current_user, "organization_id", None):
        stmt = stmt.where(User.organization_id == current_user.organization_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (User.username.ilike(like)) | (User.full_name.ilike(like)) | (User.email.ilike(like))
        )
    stmt = stmt.order_by(User.username).limit(100)
    res = await db.execute(stmt)
    return [UserLite.model_validate(u) for u in res.scalars().all()]


# ============== 用户组 ==============

class UserGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class UserGroupMemberAdd(BaseModel):
    user_id: str


class UserGroupOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_by: str
    created_at: Optional[str]
    member_count: int = 0
    is_owner: bool = False

    class Config:
        from_attributes = True


@router.get("/user-groups", response_model=List[UserGroupOut])
async def list_user_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出我创建或我加入的用户组。"""
    owned = select(UserGroup).where(UserGroup.created_by == current_user.id)
    member_gids = select(UserGroupMember.group_id).where(UserGroupMember.user_id == current_user.id)
    stmt = select(UserGroup).where(
        (UserGroup.created_by == current_user.id) | (UserGroup.id.in_(member_gids))
    ).order_by(UserGroup.name)
    res = await db.execute(stmt)
    groups = res.scalars().all()
    out = []
    for g in groups:
        mc = (await db.execute(
            select(UserGroupMember).where(UserGroupMember.group_id == g.id)
        )).scalars().all()
        out.append(UserGroupOut(
            id=g.id, name=g.name, description=g.description,
            created_by=g.created_by,
            created_at=g.created_at.isoformat() if g.created_at else None,
            member_count=len(mc),
            is_owner=(g.created_by == current_user.id),
        ))
    return out


@router.post("/user-groups", response_model=UserGroupOut, status_code=status.HTTP_201_CREATED)
async def create_user_group(
    data: UserGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = UserGroup(name=data.name, description=data.description, created_by=current_user.id)
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return UserGroupOut(
        id=g.id, name=g.name, description=g.description, created_by=g.created_by,
        created_at=g.created_at.isoformat() if g.created_at else None,
        member_count=0, is_owner=True,
    )


@router.get("/user-groups/{group_id}", response_model=dict)
async def get_user_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = (await db.execute(select(UserGroup).where(UserGroup.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="用户组不存在")
    members = (await db.execute(
        select(UserGroupMember, User)
        .join(User, UserGroupMember.user_id == User.id)
        .where(UserGroupMember.group_id == group_id)
    )).all()
    return {
        "id": g.id, "name": g.name, "description": g.description,
        "created_by": g.created_by,
        "members": [
            {"user_id": m.User.id, "username": m.User.username,
             "full_name": m.User.full_name, "email": m.User.email}
            for m in members
        ],
    }


@router.post("/user-groups/{group_id}/members", status_code=status.HTTP_201_CREATED)
async def add_group_member(
    group_id: str,
    data: UserGroupMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = (await db.execute(select(UserGroup).where(UserGroup.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="用户组不存在")
    if g.created_by != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="仅组创建者可添加成员")
    u = (await db.execute(select(User).where(User.id == data.user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    exists = (await db.execute(
        select(UserGroupMember).where(
            UserGroupMember.group_id == group_id, UserGroupMember.user_id == data.user_id
        )
    )).scalar_one_or_none()
    if exists:
        return {"ok": True, "message": "已是成员"}
    m = UserGroupMember(group_id=group_id, user_id=data.user_id)
    db.add(m)
    await db.commit()
    return {"ok": True}


@router.delete("/user-groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(
    group_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = (await db.execute(select(UserGroup).where(UserGroup.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="用户组不存在")
    if g.created_by != current_user.id and user_id != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="无权移除成员")
    m = (await db.execute(
        select(UserGroupMember).where(
            UserGroupMember.group_id == group_id, UserGroupMember.user_id == user_id
        )
    )).scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()


@router.delete("/user-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = (await db.execute(select(UserGroup).where(UserGroup.id == group_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(status_code=404, detail="用户组不存在")
    if g.created_by != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="仅组创建者可删除")
    await db.delete(g)
    await db.commit()


# ============== 知识库分享 ==============

class ShareCreate(BaseModel):
    share_type: str          # user | group | system
    target_id: Optional[str] = None   # user/group id；system 时留空
    permission: str = "read"          # read | write


class ShareOut(BaseModel):
    id: str
    kb_id: str
    share_type: str
    target_id: Optional[str]
    target_name: Optional[str]
    permission: str
    created_by: str

    class Config:
        from_attributes = True


@router.post("/knowledge-bases/{kb_id}/shares", response_model=ShareOut, status_code=status.HTTP_201_CREATED)
async def add_share(
    kb_id: str,
    data: ShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 仅拥有者或超管可分享
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if kb.created_by != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="仅知识库拥有者可设置分享")

    if data.share_type not in (ShareType.USER.value, ShareType.GROUP.value, ShareType.SYSTEM.value):
        raise HTTPException(status_code=400, detail="share_type 必须是 user/group/system")
    if data.permission not in (SharePermission.READ.value, SharePermission.WRITE.value):
        raise HTTPException(status_code=400, detail="permission 必须是 read/write")

    target_name = None
    if data.share_type == ShareType.SYSTEM.value:
        data.target_id = None
    elif data.share_type == ShareType.USER.value:
        if not data.target_id:
            raise HTTPException(status_code=400, detail="分享给用户时需提供 target_id")
        u = (await db.execute(select(User).where(User.id == data.target_id))).scalar_one_or_none()
        if not u:
            raise HTTPException(status_code=404, detail="目标用户不存在")
        target_name = u.full_name or u.username
    elif data.share_type == ShareType.GROUP.value:
        if not data.target_id:
            raise HTTPException(status_code=400, detail="分享给用户组时需提供 target_id")
        g = (await db.execute(select(UserGroup).where(UserGroup.id == data.target_id))).scalar_one_or_none()
        if not g:
            raise HTTPException(status_code=404, detail="目标用户组不存在")
        target_name = g.name

    # 去重
    existing = (await db.execute(
        select(KnowledgeBaseShare).where(
            KnowledgeBaseShare.kb_id == kb_id,
            KnowledgeBaseShare.share_type == data.share_type,
            KnowledgeBaseShare.target_id == data.target_id,
        )
    )).scalar_one_or_none()
    if existing:
        existing.permission = data.permission
        await db.commit()
        return ShareOut(
            id=existing.id, kb_id=existing.kb_id, share_type=existing.share_type,
            target_id=existing.target_id, target_name=target_name,
            permission=existing.permission, created_by=existing.created_by,
        )

    share = KnowledgeBaseShare(
        kb_id=kb_id, share_type=data.share_type, target_id=data.target_id,
        permission=data.permission, created_by=current_user.id,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return ShareOut(
        id=share.id, kb_id=share.kb_id, share_type=share.share_type,
        target_id=share.target_id, target_name=target_name,
        permission=share.permission, created_by=share.created_by,
    )


@router.get("/knowledge-bases/{kb_id}/shares", response_model=List[ShareOut])
async def list_shares(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if kb.created_by != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="仅知识库拥有者可查看分享")

    rows = (await db.execute(
        select(KnowledgeBaseShare).where(KnowledgeBaseShare.kb_id == kb_id)
    )).scalars().all()
    out = []
    for s in rows:
        target_name = None
        if s.share_type == ShareType.USER.value and s.target_id:
            u = (await db.execute(select(User).where(User.id == s.target_id))).scalar_one_or_none()
            target_name = u.full_name or u.username if u else None
        elif s.share_type == ShareType.GROUP.value and s.target_id:
            g = (await db.execute(select(UserGroup).where(UserGroup.id == s.target_id))).scalar_one_or_none()
            target_name = g.name if g else None
        out.append(ShareOut(
            id=s.id, kb_id=s.kb_id, share_type=s.share_type, target_id=s.target_id,
            target_name=target_name, permission=s.permission, created_by=s.created_by,
        ))
    return out


@router.delete("/knowledge-bases/{kb_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_share(
    kb_id: str,
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))).scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if kb.created_by != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="仅知识库拥有者可移除分享")
    s = (await db.execute(
        select(KnowledgeBaseShare).where(
            KnowledgeBaseShare.id == share_id, KnowledgeBaseShare.kb_id == kb_id
        )
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="分享记录不存在")
    await db.delete(s)
    await db.commit()


# ============== 多文件 / 文件夹 批量上传（自动 RAG） ==============

class BatchUploadResult(BaseModel):
    file_name: str
    title: str
    status: str
    document_id: Optional[str] = None
    chunk_count: int = 0
    error: Optional[str] = None
    supported: bool = True


@router.post("/knowledge-bases/{kb_id}/documents/upload-batch", response_model=List[BatchUploadResult])
async def upload_documents_batch(
    kb_id: str,
    files: List[UploadFile] = File(...),
    folder: Optional[str] = Form(None),   # 前端传文件夹相对路径前缀（可选）
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 验证知识库写权限
    await _can_access_kb(db, kb_id, current_user, require_write=True)

    rag_engine = RAGEngine(db_session=db)
    results: List[BatchUploadResult] = []

    for f in files:
        raw_name = f.filename or "unnamed"
        # 拼接文件夹前缀，保留目录结构
        full_name = f"{folder}/{raw_name}" if folder else raw_name
        try:
            content_bytes = await f.read()
        except Exception as e:
            results.append(BatchUploadResult(
                file_name=raw_name, title=raw_name, status="failed",
                error=f"读取失败: {str(e)}", supported=False,
            ))
            continue

        supported = is_supported(raw_name)
        try:
            content = extract_text(raw_name, content_bytes)
        except Exception as e:
            content = content_bytes.decode("utf-8", errors="ignore")

        doc_title = raw_name
        try:
            doc = await rag_engine.add_document(
                kb_id=kb_id,
                title=doc_title,
                content=content_bytes,
                source_type="file",
                file_name=full_name,
                file_size=len(content_bytes),
                mime_type=f.content_type,
                meta_data={
                    "ext": raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else "",
                    "folder": folder or "",
                    "supported": supported,
                },
            )
            results.append(BatchUploadResult(
                file_name=raw_name, title=doc_title, status=doc.status,
                document_id=doc.id, chunk_count=doc.chunk_count, supported=supported,
            ))
        except Exception as e:
            results.append(BatchUploadResult(
                file_name=raw_name, title=doc_title, status="failed",
                error=f"解析入库失败: {str(e)}", supported=supported,
            ))

    return results
