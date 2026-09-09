"""
通维AI项目管理系统 - 多智能体可视化编排工作流

提供 Planner -> Executor -> Reviewer 的真实编排执行：
- Planner：LLM 将目标拆为执行计划

[PMBOK KA: 跨领域 | PG: 执行 (Cross-area/Executing) — Agent工作流执行]
对应PMI第6版标准：Agent工作流执行

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: CPMAI Methodology — Agent工作流自动化]"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Task, Project, User, AgentSession, TaskStatus, TaskPriority
from app.core.security import get_current_user
from app.core.ai_engine import ai_engine

router = APIRouter(prefix="/multi-agent", tags=["多智能体"])


class WorkflowRunRequest(BaseModel):
    objective: str
    project_id: Optional[str] = None
    create_tasks: bool = True


def _safe_json(text: str) -> Any:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    m = re.search(r"[\[{].*[\]}]", t, re.DOTALL)
    if m:
        t = m.group(0)
    try:
        return json.loads(t)
    except Exception:
        return None


async def _llm(prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> Optional[str]:
    try:
        return await ai_engine.generate(prompt, provider=None, temperature=temperature, max_tokens=max_tokens)
    except Exception:
        return None


async def _create_task(db: AsyncSession, project_id: str, name: str, description: str = "") -> Task:
    cnt = (await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id, Task.parent_task_id == None, Task.is_deleted == False)
    )).scalar() or 0
    task = Task(
        project_id=project_id, wbs_code=str(cnt + 1), name=name[:255],
        status=TaskStatus.TODO.value, priority=TaskPriority.MEDIUM.value,
        description=description, category="agent_workflow", labels=["multi-agent"],
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.post("/workflow/run")
async def run_workflow(
    req: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not req.objective or not req.objective.strip():
        raise HTTPException(status_code=400, detail="目标不能为空")

    # 1) Planner 规划
    planner_raw = await _llm(
        f"你是项目规划智能体(Planner)。针对目标：{req.objective}\n"
        "生成执行计划，严格按 JSON 数组返回，每项含：step(步骤名)、owner(负责角色)、"
        "desc(说明)。最多6步，不要解释。", temperature=0.4,
    )
    plan = _safe_json(planner_raw)
    if not isinstance(plan, list) or not plan:
        plan = [{"step": req.objective, "owner": "Executor", "desc": req.objective}]

    # 2) Executor 执行（落库任务）
    created: List[Dict[str, Any]] = []
    if req.project_id and req.create_tasks:
        proj = await db.get(Project, req.project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="项目不存在")
        for i, step in enumerate(plan[:6]):
            name = str(step.get("step") or step.get("desc") or f"步骤{i+1}").strip()
            t = await _create_task(db, req.project_id, name, description=step.get("desc", ""))
            created.append({"id": t.id, "name": t.name})

    # 3) Reviewer 审查
    reviewer_raw = await _llm(
        f"你是质量审查智能体(Reviewer)。请审查以下执行计划与已创建任务，"
        f"用中文给出最多3条改进建议（不要解释、不加标题）：\n计划：{json.dumps(plan, ensure_ascii=False)}\n"
        f"已建任务：{json.dumps(created, ensure_ascii=False)}", temperature=0.3,
    )
    review = reviewer_raw or "（未配置大模型）计划结构合理，建议补充验收标准与明确负责人。"

    # 轨迹落库
    session = AgentSession(
        user_id=current_user.id, project_id=req.project_id,
        title=f"[workflow] {req.objective[:40]}",
        messages=[{"role": "system", "content": "agent_workflow", "plan": plan, "review": review}],
    )
    db.add(session)
    await db.commit()

    return {
        "success": True,
        "objective": req.objective,
        "planner": plan,
        "created_tasks": created,
        "created_count": len(created),
        "reviewer": review,
    }
