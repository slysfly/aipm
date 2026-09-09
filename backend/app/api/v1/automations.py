"""
[PMBOK KA: 跨领域 | PG: 执行 (Cross-area/Executing) — 自动化规则引擎]
对应PMI第6版标准：自动化工作流执行

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: CPMAI Methodology — AI自动化工作流]
PMBOK 7th Principle: Adaptability | Domain: Project Work — 适应性自动化
PMBOK 8th: AI-Powered Workflow Automation"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import User, Project, Task
from app.models.automation import AutomationRule
from app.schemas.automation import (
    AutomationRuleCreate, AutomationRuleUpdate, AutomationRuleResponse,
    AutomationRuleToggle, AutomationTestRequest, AutomationTestResponse
)
from app.schemas import SuccessResponse
from app.services.automation_engine import AutomationEngine
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


@router.post("/", response_model=AutomationRuleResponse, status_code=201)
async def create_automation_rule(
    rule_in: AutomationRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if rule_in.project_id:
        project_result = await db.execute(
            select(Project).where(Project.id == rule_in.project_id, Project.is_deleted == False)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise NotFoundException(message="项目不存在")

    rule = AutomationRule(
        name=rule_in.name,
        description=rule_in.description,
        is_active=rule_in.is_active,
        trigger_type=rule_in.trigger_type,
        trigger_conditions=rule_in.trigger_conditions,
        actions=rule_in.actions,
        project_id=rule_in.project_id,
        is_global=rule_in.is_global,
        created_by=current_user.id,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    return rule


@router.get("/", response_model=List[AutomationRuleResponse])
async def list_automation_rules(
    trigger_type: Optional[str] = None,
    project_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_global: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(AutomationRule)
    conditions = []

    if trigger_type:
        conditions.append(AutomationRule.trigger_type == trigger_type)
    if project_id:
        conditions.append(
            or_(
                AutomationRule.project_id == project_id,
                AutomationRule.is_global == True
            )
        )
    if is_active is not None:
        conditions.append(AutomationRule.is_active == is_active)
    if is_global is not None:
        conditions.append(AutomationRule.is_global == is_global)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(AutomationRule.created_at.desc())

    result = await db.execute(query)
    rules = result.scalars().all()

    return [AutomationRuleResponse.model_validate(r) for r in rules]


@router.get("/{rule_id}", response_model=AutomationRuleResponse)
async def get_automation_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise NotFoundException(message="自动化规则不存在")

    return rule


@router.put("/{rule_id}", response_model=AutomationRuleResponse)
async def update_automation_rule(
    rule_id: str,
    rule_in: AutomationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise NotFoundException(message="自动化规则不存在")

    update_data = rule_in.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(rule, k, v)

    rule.updated_at = datetime.now()

    await db.commit()
    await db.refresh(rule)

    return rule


@router.delete("/{rule_id}", response_model=SuccessResponse)
async def delete_automation_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise NotFoundException(message="自动化规则不存在")

    await db.delete(rule)
    await db.commit()

    return SuccessResponse(message="自动化规则删除成功")


@router.put("/{rule_id}/toggle", response_model=AutomationRuleResponse)
async def toggle_automation_rule(
    rule_id: str,
    toggle_in: AutomationRuleToggle,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise NotFoundException(message="自动化规则不存在")

    rule.is_active = toggle_in.is_active
    rule.updated_at = datetime.now()

    await db.commit()
    await db.refresh(rule)

    return rule


@router.post("/{rule_id}/test", response_model=AutomationTestResponse)
async def test_automation_rule(
    rule_id: str,
    test_in: AutomationTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AutomationRule).where(AutomationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise NotFoundException(message="自动化规则不存在")

    entity = None
    if test_in.entity_type == "task":
        entity_result = await db.execute(
            select(Task).where(Task.id == test_in.entity_id, Task.is_deleted == False)
        )
        entity = entity_result.scalar_one_or_none()

    engine = AutomationEngine(db)
    conditions_result = await engine.evaluate_trigger(rule, entity, test_in.trigger_data)

    actions_executed = []
    if conditions_result:
        actions_executed = await engine.execute_actions(rule, entity, test_in.trigger_data)

    return AutomationTestResponse(
        rule_id=rule.id,
        rule_name=rule.name,
        triggered=conditions_result,
        conditions_result=conditions_result,
        actions_executed=[
            {
                "type": a["action"].get("type"),
                "success": a.get("success"),
                "result": a.get("result"),
                "error": a.get("error"),
            }
            for a in actions_executed
        ],
        errors=engine.errors,
    )
