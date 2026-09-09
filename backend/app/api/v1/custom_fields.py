"""
[PMBOK KA: 整合管理 (Integration) — 自定义字段、元数据扩展]
对应PMI第6版标准：元数据扩展
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import User, Project
from app.models.custom_field import CustomField, CustomFieldValue
from app.schemas.custom_field import (
    CustomFieldCreate, CustomFieldUpdate, CustomFieldResponse,
    CustomFieldValueCreate, CustomFieldValueUpdate, CustomFieldValueResponse,
    CustomFieldValueWithField
)
from app.schemas import SuccessResponse
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


@router.post("/", response_model=CustomFieldResponse, status_code=201)
async def create_custom_field(
    field_in: CustomFieldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if field_in.project_id:
        project_result = await db.execute(
            select(Project).where(Project.id == field_in.project_id, Project.is_deleted == False)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise NotFoundException(message="项目不存在")

    existing_result = await db.execute(
        select(CustomField).where(
            CustomField.field_key == field_in.field_key,
            CustomField.project_id == field_in.project_id
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValidationException(message="字段key已存在")

    field = CustomField(
        name=field_in.name,
        field_key=field_in.field_key,
        field_type=field_in.field_type,
        entity_type=field_in.entity_type,
        options=field_in.options,
        is_required=field_in.is_required,
        default_value=field_in.default_value,
        sort_order=field_in.sort_order,
        project_id=field_in.project_id,
        is_global=field_in.is_global,
        created_by=current_user.id,
    )

    db.add(field)
    await db.commit()
    await db.refresh(field)

    return field


@router.get("/", response_model=List[CustomFieldResponse])
async def list_custom_fields(
    entity_type: Optional[str] = None,
    project_id: Optional[str] = None,
    is_global: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(CustomField)

    conditions = []
    if entity_type:
        conditions.append(CustomField.entity_type == entity_type)
    if project_id:
        conditions.append(
            or_(
                CustomField.project_id == project_id,
                CustomField.is_global == True
            )
        )
    if is_global is not None:
        conditions.append(CustomField.is_global == is_global)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(CustomField.sort_order, CustomField.created_at)

    result = await db.execute(query)
    fields = result.scalars().all()

    return [CustomFieldResponse.model_validate(f) for f in fields]


@router.get("/{field_id}", response_model=CustomFieldResponse)
async def get_custom_field(
    field_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(CustomField).where(CustomField.id == field_id)
    )
    field = result.scalar_one_or_none()

    if not field:
        raise NotFoundException(message="自定义字段不存在")

    return field


@router.put("/{field_id}", response_model=CustomFieldResponse)
async def update_custom_field(
    field_id: str,
    field_in: CustomFieldUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(CustomField).where(CustomField.id == field_id)
    )
    field = result.scalar_one_or_none()

    if not field:
        raise NotFoundException(message="自定义字段不存在")

    update_data = field_in.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(field, k, v)

    field.updated_at = datetime.now()

    await db.commit()
    await db.refresh(field)

    return field


@router.delete("/{field_id}", response_model=SuccessResponse)
async def delete_custom_field(
    field_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(CustomField).where(CustomField.id == field_id)
    )
    field = result.scalar_one_or_none()

    if not field:
        raise NotFoundException(message="自定义字段不存在")

    await db.delete(field)
    await db.commit()

    return SuccessResponse(message="自定义字段删除成功")


@router.post("/{field_id}/values", response_model=CustomFieldValueResponse)
async def set_field_value(
    field_id: str,
    value_in: CustomFieldValueCreate,
    entity_id: str,
    entity_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    field_result = await db.execute(
        select(CustomField).where(CustomField.id == field_id)
    )
    field = field_result.scalar_one_or_none()

    if not field:
        raise NotFoundException(message="自定义字段不存在")

    existing_result = await db.execute(
        select(CustomFieldValue).where(
            CustomFieldValue.custom_field_id == field_id,
            CustomFieldValue.entity_id == entity_id,
            CustomFieldValue.entity_type == entity_type
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.value = value_in.value
        existing.updated_at = datetime.now()
        await db.commit()
        await db.refresh(existing)
        return existing

    value = CustomFieldValue(
        custom_field_id=field_id,
        entity_id=entity_id,
        entity_type=entity_type,
        value=value_in.value,
    )

    db.add(value)
    await db.commit()
    await db.refresh(value)

    return value


@router.get("/by-entity/{entity_type}/{entity_id}", response_model=List[CustomFieldValueWithField])
async def get_entity_custom_field_values(
    entity_type: str,
    entity_id: str,
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    field_query = select(CustomField).where(
        CustomField.entity_type == entity_type,
        or_(
            CustomField.is_global == True,
            CustomField.project_id == project_id if project_id else False
        )
    ).order_by(CustomField.sort_order)

    field_result = await db.execute(field_query)
    fields = field_result.scalars().all()

    value_result = await db.execute(
        select(CustomFieldValue).where(
            CustomFieldValue.entity_id == entity_id,
            CustomFieldValue.entity_type == entity_type
        )
    )
    values = value_result.scalars().all()
    value_map = {v.custom_field_id: v.value for v in values}

    result = []
    for field in fields:
        result.append(CustomFieldValueWithField(
            field_id=field.id,
            field_name=field.name,
            field_key=field.field_key,
            field_type=field.field_type,
            value=value_map.get(field.id, field.default_value),
            is_required=field.is_required,
            options=field.options or []
        ))

    return result
