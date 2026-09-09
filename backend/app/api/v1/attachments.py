"""
[PMBOK KA: 整合管理 (Integration) — 文件附件、交付物管理]
对应PMI第6版标准：交付物管理
"""

import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.db.session import get_db
from app.models import Attachment, Task, User, ProjectMember
from app.schemas import (
    AttachmentResponse, AttachmentListResponse, SuccessResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()

MAX_FILE_SIZE = 100 * 1024 * 1024
UPLOAD_DIR = Path("./uploads")


def get_upload_path() -> Path:
    now = datetime.now()
    upload_path = UPLOAD_DIR / str(now.year) / str(now.month)
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def generate_filename(original_filename: str) -> str:
    ext = Path(original_filename).suffix
    return f"{uuid.uuid4().hex}{ext}"


async def _user_can_access_attachment(
    attachment: "Attachment", current_user: User, db: AsyncSession
) -> bool:
    if current_user.is_superuser:
        return True
    if attachment.uploaded_by == current_user.id:
        return True
    if attachment.project_id:
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == attachment.project_id,
                ProjectMember.user_id == current_user.id,
                ProjectMember.is_active == True,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is not None:
            return True
    return False


@router.post("/upload", response_model=AttachmentResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    task_id: Optional[str] = None,
    project_id: Optional[str] = None,
    comment_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename:
        raise ValidationException(message="文件名不能为空")

    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise ValidationException(message=f"文件大小超过限制: {MAX_FILE_SIZE // 1024 // 1024}MB")

    upload_path = get_upload_path()
    stored_filename = generate_filename(file.filename)
    file_path = upload_path / stored_filename

    with open(file_path, "wb") as f:
        f.write(content)

    attachment = Attachment(
        filename=stored_filename,
        original_name=file.filename,
        file_path=str(file_path),
        file_size=file_size,
        mime_type=file.content_type or "application/octet-stream",
        task_id=task_id,
        project_id=project_id,
        comment_id=comment_id,
        uploaded_by=current_user.id,
    )

    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return attachment


@router.get("/{attachment_id}/download")
async def download_file(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise NotFoundException(message="附件不存在")

    if not await _user_can_access_attachment(attachment, current_user, db):
        raise NotFoundException(message="附件不存在或无权访问")

    file_path = Path(attachment.file_path)
    if not file_path.exists():
        raise NotFoundException(message="文件已丢失")

    return FileResponse(
        path=str(file_path),
        filename=attachment.original_name,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{attachment.original_name}"'},
    )


@router.get("/tasks/{task_id}/attachments", response_model=AttachmentListResponse)
async def list_task_attachments(
    task_id: str,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    count_query = select(func.count(Attachment.id)).where(Attachment.task_id == task_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        select(Attachment)
        .where(Attachment.task_id == task_id)
        .order_by(Attachment.created_at.desc())
    )
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    attachments = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return AttachmentListResponse(
        items=[AttachmentResponse.model_validate(a) for a in attachments],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.delete("/{attachment_id}", response_model=SuccessResponse)
async def delete_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise NotFoundException(message="附件不存在")

    if attachment.uploaded_by != current_user.id and not current_user.is_superuser:
        raise ValidationException(message="无权删除此附件")

    file_path = Path(attachment.file_path)
    if file_path.exists():
        file_path.unlink()

    await db.delete(attachment)
    await db.commit()

    return SuccessResponse(message="附件删除成功")
