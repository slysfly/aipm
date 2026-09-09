"""
PMI中国AI项目管理社区 - Wiki API路由

[PMBOK KA: 沟通管理 | PG: 执行 (Communications/Executing) — Wiki知识库、团队协作]
对应PMI第6版标准：知识管理、团队协作
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.session import get_db
from app.models import User
from app.models.wiki import WikiSpace, WikiPage, WikiPageVersion, WikiComment
from app.schemas.wiki import (
    WikiSpaceCreate, WikiSpaceUpdate, WikiSpaceResponse, WikiSpaceListResponse,
    WikiPageCreate, WikiPageUpdate, WikiPageResponse, WikiPageTreeResponse, WikiPageListResponse,
    WikiPageVersionResponse, WikiPageVersionListResponse,
    WikiCommentCreate, WikiCommentUpdate, WikiCommentResponse, WikiCommentListResponse,
    WikiSearchResponse, WikiSearchResult,
)
from app.core.security import get_current_user

router = APIRouter()


# ==================== WikiSpace ====================

@router.post("/spaces", response_model=WikiSpaceResponse, status_code=201)
async def create_space(
    space_in: WikiSpaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    space = WikiSpace(
        name=space_in.name,
        description=space_in.description,
        icon=space_in.icon,
        color=space_in.color,
        is_public=space_in.is_public,
        owner_id=current_user.id,
        member_ids=space_in.member_ids,
    )
    db.add(space)
    await db.commit()
    await db.refresh(space)
    return space


@router.get("/spaces", response_model=WikiSpaceListResponse)
async def list_spaces(
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(WikiSpace).where(
        or_(
            WikiSpace.is_public == True,
            WikiSpace.owner_id == current_user.id,
            WikiSpace.member_ids.contains([current_user.id])
        )
    )

    if search:
        query = query.where(WikiSpace.name.ilike(f"%{search}%"))

    query = query.order_by(WikiSpace.created_at.desc())

    result = await db.execute(query)
    spaces = result.scalars().all()

    return WikiSpaceListResponse(items=spaces, total=len(spaces))


@router.get("/spaces/{space_id}", response_model=WikiSpaceResponse)
async def get_space(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiSpace).where(WikiSpace.id == space_id))
    space = result.scalar_one_or_none()

    if not space:
        raise HTTPException(status_code=404, detail="知识空间不存在")

    return space


@router.put("/spaces/{space_id}", response_model=WikiSpaceResponse)
async def update_space(
    space_id: str,
    space_in: WikiSpaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiSpace).where(WikiSpace.id == space_id))
    space = result.scalar_one_or_none()

    if not space:
        raise HTTPException(status_code=404, detail="知识空间不存在")

    if space.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="无权修改此知识空间")

    update_data = space_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(space, field, value)

    space.updated_at = datetime.now()
    await db.commit()
    await db.refresh(space)
    return space


@router.delete("/spaces/{space_id}", status_code=204)
async def delete_space(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiSpace).where(WikiSpace.id == space_id))
    space = result.scalar_one_or_none()

    if not space:
        raise HTTPException(status_code=404, detail="知识空间不存在")

    if space.owner_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="无权删除此知识空间")

    await db.delete(space)
    await db.commit()
    return None


# ==================== WikiPage ====================

@router.post("/spaces/{space_id}/pages", response_model=WikiPageResponse, status_code=201)
async def create_page(
    space_id: str,
    page_in: WikiPageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiSpace).where(WikiSpace.id == space_id))
    space = result.scalar_one_or_none()

    if not space:
        raise HTTPException(status_code=404, detail="知识空间不存在")

    page = WikiPage(
        space_id=space_id,
        title=page_in.title,
        content=page_in.content,
        parent_id=page_in.parent_id,
        order_index=page_in.order_index,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)

    version = WikiPageVersion(
        page_id=page.id,
        title=page.title,
        content=page.content,
        editor_id=current_user.id,
        edit_summary="创建页面",
    )
    db.add(version)
    await db.commit()

    return page


@router.get("/spaces/{space_id}/pages", response_model=WikiPageListResponse)
async def list_pages(
    space_id: str,
    parent_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(WikiPage).where(WikiPage.space_id == space_id)

    if parent_id:
        query = query.where(WikiPage.parent_id == parent_id)
    else:
        query = query.where(WikiPage.parent_id.is_(None))

    query = query.order_by(WikiPage.order_index, WikiPage.created_at)

    result = await db.execute(query)
    pages = result.scalars().all()

    return WikiPageListResponse(items=pages, total=len(pages))


@router.get("/spaces/{space_id}/pages/tree", response_model=List[WikiPageTreeResponse])
async def get_page_tree(
    space_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(WikiPage).where(WikiPage.space_id == space_id).order_by(WikiPage.order_index, WikiPage.created_at)
    )
    pages = result.scalars().all()

    page_map = {page.id: page for page in pages}
    tree = []

    for page in pages:
        page.children = []
        if page.parent_id and page.parent_id in page_map:
            if not hasattr(page_map[page.parent_id], 'children'):
                page_map[page.parent_id].children = []
            page_map[page.parent_id].children.append(page)
        else:
            tree.append(page)

    return tree


@router.get("/pages/{page_id}", response_model=WikiPageResponse)
async def get_page(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    return page


@router.put("/pages/{page_id}", response_model=WikiPageResponse)
async def update_page(
    page_id: str,
    page_in: WikiPageUpdate,
    edit_summary: Optional[str] = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    if page.is_locked and page.lock_by != current_user.id:
        if page.lock_expires_at and page.lock_expires_at > datetime.now():
            raise HTTPException(status_code=423, detail="页面已被锁定")

    update_data = page_in.model_dump(exclude_unset=True)

    if update_data:
        version = WikiPageVersion(
            page_id=page.id,
            title=update_data.get("title", page.title),
            content=update_data.get("content", page.content),
            editor_id=current_user.id,
            edit_summary=edit_summary or "编辑页面",
        )
        db.add(version)

        for field, value in update_data.items():
            setattr(page, field, value)

        page.version += 1
        page.updated_by = current_user.id
        page.updated_at = datetime.now()

        await db.commit()
        await db.refresh(page)

    return page


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    space_result = await db.execute(select(WikiSpace).where(WikiSpace.id == page.space_id))
    space = space_result.scalar_one_or_none()

    if space and space.owner_id != current_user.id and page.created_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="无权删除此页面")

    await db.delete(page)
    await db.commit()
    return None


# ==================== WikiPageVersion ====================

@router.get("/pages/{page_id}/versions", response_model=WikiPageVersionListResponse)
async def list_page_versions(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(WikiPageVersion).where(WikiPageVersion.page_id == page_id).order_by(desc(WikiPageVersion.created_at))
    )
    versions = result.scalars().all()

    return WikiPageVersionListResponse(items=versions, total=len(versions))


@router.post("/pages/{page_id}/versions/{version_id}/restore", response_model=WikiPageResponse)
async def restore_version(
    page_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    page_result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = page_result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    version_result = await db.execute(select(WikiPageVersion).where(WikiPageVersion.id == version_id))
    version = version_result.scalar_one_or_none()

    if not version or version.page_id != page_id:
        raise HTTPException(status_code=404, detail="版本不存在")

    new_version = WikiPageVersion(
        page_id=page.id,
        title=page.title,
        content=page.content,
        editor_id=current_user.id,
        edit_summary=f"回退到版本 {version_id[:8]}",
    )
    db.add(new_version)

    page.title = version.title
    page.content = version.content
    page.version += 1
    page.updated_by = current_user.id
    page.updated_at = datetime.now()

    await db.commit()
    await db.refresh(page)
    return page


# ==================== WikiComment ====================

@router.get("/pages/{page_id}/comments", response_model=WikiCommentListResponse)
async def list_comments(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(WikiComment).where(
            WikiComment.page_id == page_id,
            WikiComment.parent_id.is_(None)
        ).order_by(WikiComment.created_at.desc())
    )
    comments = result.scalars().all()

    return WikiCommentListResponse(items=comments, total=len(comments))


@router.post("/pages/{page_id}/comments", response_model=WikiCommentResponse, status_code=201)
async def create_comment(
    page_id: str,
    comment_in: WikiCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    comment = WikiComment(
        page_id=page_id,
        content=comment_in.content,
        author_id=current_user.id,
        parent_id=comment_in.parent_id,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.put("/comments/{comment_id}", response_model=WikiCommentResponse)
async def update_comment(
    comment_id: str,
    comment_in: WikiCommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiComment).where(WikiComment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    if comment.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="无权修改此评论")

    if comment_in.content:
        comment.content = comment_in.content

    comment.updated_at = datetime.now()
    await db.commit()
    await db.refresh(comment)
    return comment


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiComment).where(WikiComment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    if comment.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="无权删除此评论")

    await db.delete(comment)
    await db.commit()
    return None


# ==================== Lock ====================

@router.post("/pages/{page_id}/lock", response_model=WikiPageResponse)
async def lock_page(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    if page.is_locked and page.lock_by != current_user.id:
        if page.lock_expires_at and page.lock_expires_at > datetime.now():
            raise HTTPException(status_code=423, detail="页面已被其他用户锁定")

    page.is_locked = True
    page.lock_by = current_user.id
    page.lock_expires_at = datetime.now() + timedelta(minutes=30)

    await db.commit()
    await db.refresh(page)
    return page


@router.delete("/pages/{page_id}/lock", response_model=WikiPageResponse)
async def unlock_page(
    page_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(WikiPage).where(WikiPage.id == page_id))
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    if page.lock_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="无权解锁此页面")

    page.is_locked = False
    page.lock_by = None
    page.lock_expires_at = None

    await db.commit()
    await db.refresh(page)
    return page


# ==================== Search ====================

@router.get("/search", response_model=WikiSearchResponse)
async def search_wiki(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(WikiPage, WikiSpace.name.label("space_name")).join(
        WikiSpace, WikiPage.space_id == WikiSpace.id
    ).where(
        or_(
            WikiPage.title.ilike(f"%{q}%"),
            WikiPage.content.ilike(f"%{q}%")
        )
    ).where(
        or_(
            WikiSpace.is_public == True,
            WikiSpace.owner_id == current_user.id,
            WikiSpace.member_ids.contains([current_user.id])
        )
    ).order_by(WikiPage.updated_at.desc())

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        page, space_name = row
        content_preview = page.content[:200] + "..." if len(page.content) > 200 else page.content
        items.append(WikiSearchResult(
            id=page.id,
            title=page.title,
            content_preview=content_preview,
            space_id=page.space_id,
            space_name=space_name,
            updated_at=page.updated_at,
        ))

    return WikiSearchResponse(items=items, total=len(items), query=q)
