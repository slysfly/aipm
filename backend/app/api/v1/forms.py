"""
PMI中国AI项目管理社区 - 表单API
提供表单模板管理和表单提交功能

[PMBOK KA: 整合管理 (Integration) — 表单管理、数据采集]
对应PMI第6版标准：表单数据采集
"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import csv
import io

from app.db.session import get_db
from app.models import User, Project
from app.models.form import FormTemplate, FormSubmission, SubmissionStatus
from app.schemas.form import (
    FormTemplateCreate, FormTemplateUpdate, FormTemplateResponse,
    FormTemplateStatsResponse, FormSubmissionCreate, FormSubmissionUpdate,
    FormSubmissionResponse, FormSubmissionDetailResponse,
    FormExportRequest
)
from app.schemas import SuccessResponse
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


# ==================== 表单模板CRUD ====================

@router.post("/templates", response_model=FormTemplateResponse, status_code=201)
async def create_form_template(
    template_in: FormTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if template_in.project_id:
        project_result = await db.execute(
            select(Project).where(Project.id == template_in.project_id, Project.is_deleted == False)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise NotFoundException(message="项目不存在")

    template = FormTemplate(
        name=template_in.name,
        description=template_in.description,
        fields=[f.model_dump() for f in template_in.fields],
        created_by=current_user.id,
        project_id=template_in.project_id,
        embed_in_task=template_in.embed_in_task,
        embed_in_project=template_in.embed_in_project,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/templates", response_model=List[FormTemplateResponse])
async def list_form_templates(
    project_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_published: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(FormTemplate)
    conditions = []

    if project_id:
        conditions.append(
            or_(
                FormTemplate.project_id == project_id,
                FormTemplate.project_id.is_(None)
            )
        )
    if is_active is not None:
        conditions.append(FormTemplate.is_active == is_active)
    if is_published is not None:
        conditions.append(FormTemplate.is_published == is_published)
    if search:
        conditions.append(FormTemplate.name.ilike(f"%{search}%"))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(desc(FormTemplate.created_at))
    result = await db.execute(query)
    templates = result.scalars().all()
    return templates


@router.get("/templates/{template_id}", response_model=FormTemplateResponse)
async def get_form_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")
    return template


@router.put("/templates/{template_id}", response_model=FormTemplateResponse)
async def update_form_template(
    template_id: str,
    template_in: FormTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    update_data = template_in.model_dump(exclude_unset=True)
    if "fields" in update_data and update_data["fields"] is not None:
        update_data["fields"] = [f.model_dump() if hasattr(f, "model_dump") else f for f in update_data["fields"]]

    for k, v in update_data.items():
        setattr(template, k, v)

    template.updated_at = datetime.now()
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", response_model=SuccessResponse)
async def delete_form_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    await db.delete(template)
    await db.commit()
    return SuccessResponse(message="表单模板删除成功")


@router.post("/templates/{template_id}/publish", response_model=FormTemplateResponse)
async def publish_form_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    template.is_published = True
    template.is_active = True
    template.updated_at = datetime.now()
    await db.commit()
    await db.refresh(template)
    return template


@router.post("/templates/{template_id}/unpublish", response_model=FormTemplateResponse)
async def unpublish_form_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    template.is_published = False
    template.updated_at = datetime.now()
    await db.commit()
    await db.refresh(template)
    return template


# ==================== 表单提交 ====================

@router.post("/templates/{template_id}/submit", response_model=FormSubmissionResponse, status_code=201)
async def submit_form(
    template_id: str,
    submission_in: FormSubmissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(
            FormTemplate.id == template_id,
            FormTemplate.is_active == True
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在或已停用")

    # 验证必填字段
    fields = template.fields or []
    for field in fields:
        if field.get("required") and not submission_in.data.get(field.get("name")):
            raise ValidationException(message=f"字段 '{field.get('label')}' 为必填项")

    submission = FormSubmission(
        form_id=template_id,
        data=submission_in.data,
        submitted_by=current_user.id,
        source_type=submission_in.source_type,
        source_id=submission_in.source_id,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return submission


@router.get("/templates/{template_id}/submissions", response_model=List[FormSubmissionResponse])
async def list_form_submissions(
    template_id: str,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    query = select(FormSubmission).where(FormSubmission.form_id == template_id)

    if status:
        query = query.where(FormSubmission.status == status)
    if source_type:
        query = query.where(FormSubmission.source_type == source_type)
    if source_id:
        query = query.where(FormSubmission.source_id == source_id)

    query = query.order_by(desc(FormSubmission.submitted_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    submissions = result.scalars().all()
    return submissions


@router.get("/submissions/{submission_id}", response_model=FormSubmissionDetailResponse)
async def get_submission(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    if not submission:
        raise NotFoundException(message="提交记录不存在")
    return submission


@router.put("/submissions/{submission_id}", response_model=FormSubmissionResponse)
async def update_submission(
    submission_id: str,
    submission_in: FormSubmissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormSubmission).where(FormSubmission.id == submission_id)
    )
    submission = result.scalar_one_or_none()
    if not submission:
        raise NotFoundException(message="提交记录不存在")

    update_data = submission_in.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(submission, k, v)

    if submission_in.status:
        submission.reviewed_by = current_user.id
        submission.reviewed_at = datetime.now()

    await db.commit()
    await db.refresh(submission)
    return submission


# ==================== 表单统计 ====================

@router.get("/templates/{template_id}/stats", response_model=FormTemplateStatsResponse)
async def get_form_stats(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    # 总提交数
    total_result = await db.execute(
        select(func.count(FormSubmission.id)).where(FormSubmission.form_id == template_id)
    )
    total_submissions = total_result.scalar() or 0

    # 各状态统计
    status_counts = {}
    for status in [SubmissionStatus.PENDING.value, SubmissionStatus.APPROVED.value,
                   SubmissionStatus.REJECTED.value, SubmissionStatus.PROCESSING.value]:
        count_result = await db.execute(
            select(func.count(FormSubmission.id)).where(
                FormSubmission.form_id == template_id,
                FormSubmission.status == status
            )
        )
        status_counts[status] = count_result.scalar() or 0

    # 今日提交
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(func.count(FormSubmission.id)).where(
            FormSubmission.form_id == template_id,
            FormSubmission.submitted_at >= today
        )
    )
    today_submissions = today_result.scalar() or 0

    # 本周提交
    week_start = today - timedelta(days=today.weekday())
    weekly_result = await db.execute(
        select(func.count(FormSubmission.id)).where(
            FormSubmission.form_id == template_id,
            FormSubmission.submitted_at >= week_start
        )
    )
    weekly_submissions = weekly_result.scalar() or 0

    # 字段统计
    field_stats = []
    fields = template.fields or []
    for field in fields:
        if field.get("type") in ["select", "radio", "checkbox", "multiselect"]:
            options = field.get("options", [])
            option_counts = {opt.get("value", opt.get("label")): 0 for opt in options}

            submissions_result = await db.execute(
                select(FormSubmission.data).where(FormSubmission.form_id == template_id)
            )
            all_data = submissions_result.scalars().all()
            for data in all_data:
                val = data.get(field.get("name")) if data else None
                if val:
                    if isinstance(val, list):
                        for v in val:
                            if v in option_counts:
                                option_counts[v] += 1
                    elif val in option_counts:
                        option_counts[val] += 1

            field_stats.append({
                "field_name": field.get("name"),
                "field_label": field.get("label"),
                "field_type": field.get("type"),
                "option_counts": option_counts,
            })

    return FormTemplateStatsResponse(
        total_submissions=total_submissions,
        pending_submissions=status_counts.get(SubmissionStatus.PENDING.value, 0),
        approved_submissions=status_counts.get(SubmissionStatus.APPROVED.value, 0),
        rejected_submissions=status_counts.get(SubmissionStatus.REJECTED.value, 0),
        today_submissions=today_submissions,
        weekly_submissions=weekly_submissions,
        field_stats=field_stats,
    )


# ==================== 数据导出 ====================

@router.post("/templates/{template_id}/export")
async def export_form_submissions(
    template_id: str,
    export_in: FormExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在")

    query = select(FormSubmission).where(FormSubmission.form_id == template_id)

    if export_in.status:
        query = query.where(FormSubmission.status == export_in.status)
    if export_in.start_date:
        query = query.where(FormSubmission.submitted_at >= export_in.start_date)
    if export_in.end_date:
        query = query.where(FormSubmission.submitted_at <= export_in.end_date)

    query = query.order_by(desc(FormSubmission.submitted_at))
    result = await db.execute(query)
    submissions = result.scalars().all()

    fields = template.fields or []
    headers = ["提交ID", "提交人", "提交时间", "状态"] + [f.get("label", f.get("name", "")) for f in fields]

    rows = []
    for sub in submissions:
        row = [
            sub.id,
            sub.submitted_by,
            sub.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if sub.submitted_at else "",
            sub.status,
        ]
        for field in fields:
            val = sub.data.get(field.get("name"), "") if sub.data else ""
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            row.append(str(val))
        rows.append(row)

    if export_in.format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        content = output.getvalue()
        output.close()

        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=form_{template_id}_submissions.csv"
            }
        )
    else:
        # xlsx format - simplified as CSV with xlsx extension for now
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        content = output.getvalue()
        output.close()

        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=form_{template_id}_submissions.xlsx"
            }
        )


# ==================== 嵌入表单 ====================

@router.get("/templates/{template_id}/embed")
async def get_embed_form(
    template_id: str,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(FormTemplate).where(
            FormTemplate.id == template_id,
            FormTemplate.is_active == True,
            FormTemplate.is_published == True
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="表单模板不存在或未发布")

    return {
        "form": template,
        "source_type": source_type,
        "source_id": source_id,
    }


@router.get("/embed/{source_type}/{source_id}", response_model=List[FormTemplateResponse])
async def list_embeddable_forms(
    source_type: str,
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    conditions = [
        FormTemplate.is_active == True,
        FormTemplate.is_published == True,
    ]

    if source_type == "task":
        conditions.append(FormTemplate.embed_in_task == True)
    elif source_type == "project":
        conditions.append(FormTemplate.embed_in_project == True)

    query = select(FormTemplate).where(and_(*conditions))
    result = await db.execute(query)
    templates = result.scalars().all()
    return templates
