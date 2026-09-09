"""
通维AI项目管理系统 - AI自然语言任务创建API
提供自然语言解析、需求拆分和工时估算能力

[PMBOK KA: 范围管理 | PG: 规划 (Scope/Planning) — AI需求解析、WBS分解、范围定义]
对应PMI第6版标准：AI辅助WBS分解、需求分析、范围定义

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — 自然语言需求解析]"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Dict, Any, Optional, List

from app.db.session import get_db
from app.models import User, Project, Task
from app.schemas import TaskCreate, TaskResponse, SuccessResponse
from app.core.security import get_current_user
from app.services.ai.nlp_task_parser import nlp_task_parser
from app.services.ai.requirement_decomposer import requirement_decomposer
from app.services.ai.effort_estimator import effort_estimator
from app.api.v1.tasks import generate_wbs_code

router = APIRouter()


class NLPTaskParseRequest:
    text: str
    project_id: Optional[str] = None


class NLPTaskCreateRequest:
    text: str
    project_id: str


@router.post("/parse-task", response_model=Dict[str, Any])
async def parse_task_description(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """解析自然语言任务描述，返回结构化任务信息
    
    示例请求：
    {
        "text": "下周三之前让张三完成登录页面的前端开发，优先级高，预计8小时",
        "project_id": "optional-project-id"
    }
    """
    text = request.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="任务描述不能为空")

    try:
        result = await nlp_task_parser.parse_task_description(
            text=text,
            db=db,
            project_id=request.get("project_id"),
        )
        return {
            "success": True,
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.post("/create-task", response_model=TaskResponse)
async def create_task_from_nlp(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """直接解析自然语言描述并创建任务
    
    示例请求：
    {
        "text": "下周三之前让张三完成登录页面的前端开发，优先级高，预计8小时",
        "project_id": "required-project-id"
    }
    """
    text = request.get("text", "").strip()
    project_id = request.get("project_id", "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="任务描述不能为空")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id不能为空")

    # 验证项目存在
    from sqlalchemy import select
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 解析自然语言
    try:
        parsed = await nlp_task_parser.parse_task_description(
            text=text,
            db=db,
            project_id=project_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

    # 构建任务创建数据
    from sqlalchemy import func
    from app.api.v1.tasks import generate_wbs_code

    # 统计根级任务数量
    sibling_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.parent_task_id == None,
            Task.is_deleted == False
        )
    )
    sibling_count = sibling_result.scalar() + 1
    wbs_code = generate_wbs_code(None, sibling_count)

    task = Task(
        project_id=project_id,
        wbs_code=wbs_code,
        name=parsed.get("name", text[:50]),
        description=parsed.get("description", text),
        level=1,
        estimated_hours=parsed.get("estimated_hours", 0),
        planned_end=parsed.get("due_date") if parsed.get("due_date") else None,
        priority=parsed.get("priority", 3),
        status="todo",
        assignee_id=parsed.get("assignee_id"),
        is_milestone=False,
        labels=parsed.get("labels", []),
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    return task


@router.post("/decompose-requirement", response_model=Dict[str, Any])
async def decompose_requirement(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI需求自动拆分 - 将需求描述拆分为结构化子任务

    示例请求：
    {
        "text": "开发一个用户登录系统，支持手机号+验证码登录、微信扫码登录、密码找回功能",
        "project_id": "optional-project-id"
    }
    """
    text = request.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="需求描述不能为空")

    try:
        tasks = await requirement_decomposer.decompose(
            requirement_text=text,
            project_id=request.get("project_id"),
            db=db,
        )
        return {
            "success": True,
            "data": {
                "tasks": tasks,
                "total_tasks": len(tasks),
                "total_hours": sum(t.get("estimated_hours", 0) for t in tasks),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拆分失败: {str(e)}")


@router.post("/decompose-requirement/confirm", response_model=Dict[str, Any])
async def confirm_decomposed_tasks(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """确认拆分结果，批量创建真实任务

    示例请求：
    {
        "project_id": "required-project-id",
        "tasks": [
            {"name": "...", "description": "...", "estimated_hours": 8, "priority": 2, ...}
        ]
    }
    """
    project_id = request.get("project_id", "").strip()
    tasks_data = request.get("tasks", [])

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id不能为空")
    if not tasks_data or not isinstance(tasks_data, list):
        raise HTTPException(status_code=400, detail="tasks不能为空且必须是数组")

    # 验证项目存在
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    created_tasks = []
    task_name_to_id = {}

    # 按层级排序，确保先创建父级任务
    sorted_tasks = sorted(tasks_data, key=lambda t: t.get("level", 0))

    for task_data in sorted_tasks:
        # 统计根级任务数量
        sibling_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.parent_task_id == None,
                Task.is_deleted == False
            )
        )
        sibling_count = sibling_result.scalar() + 1
        wbs_code = generate_wbs_code(None, sibling_count)

        task = Task(
            project_id=project_id,
            wbs_code=wbs_code,
            name=task_data.get("name", "未命名任务")[:255],
            description=task_data.get("description", ""),
            level=1,
            estimated_hours=task_data.get("estimated_hours", 0),
            priority=task_data.get("priority", 3),
            status="todo",
            assignee_id=task_data.get("assignee_id") or task_data.get("assignee_suggestion_id"),
            is_milestone=False,
            labels=task_data.get("labels", []),
            category=task_data.get("category", ""),
        )

        db.add(task)
        await db.flush()
        await db.refresh(task)

        task_name_to_id[task_data.get("name", "")] = task.id
        created_tasks.append(task)

    # 创建任务依赖关系
    dependency_count = 0
    for task_data in tasks_data:
        deps = task_data.get("dependencies", [])
        task_name = task_data.get("name", "")
        successor_id = task_name_to_id.get(task_name)

        if successor_id and deps:
            for dep_name in deps:
                predecessor_id = task_name_to_id.get(dep_name)
                if predecessor_id and predecessor_id != successor_id:
                    from app.models import TaskDependency
                    dep = TaskDependency(
                        predecessor_id=predecessor_id,
                        successor_id=successor_id,
                        dependency_type="FS",
                        lag_time=0,
                    )
                    db.add(dep)
                    dependency_count += 1

    await db.commit()

    return {
        "success": True,
        "data": {
            "created_count": len(created_tasks),
            "dependency_count": dependency_count,
            "tasks": [{"id": t.id, "name": t.name, "wbs_code": t.wbs_code} for t in created_tasks],
        },
        "message": f"成功创建 {len(created_tasks)} 个任务，{dependency_count} 条依赖关系",
    }


@router.post("/estimate-task", response_model=Dict[str, Any])
async def estimate_task_effort(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI估算单个任务工时

    示例请求：
    {
        "task_name": "实现用户登录API",
        "description": "开发手机号验证码登录后端接口",
        "project_id": "optional-project-id"
    }
    """
    task_name = request.get("task_name", "").strip()
    if not task_name:
        raise HTTPException(status_code=400, detail="task_name不能为空")

    try:
        result = await effort_estimator.estimate_task(
            task_name=task_name,
            description=request.get("description", ""),
            project_id=request.get("project_id"),
            db=db,
        )
        return {
            "success": True,
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"估算失败: {str(e)}")


@router.get("/estimate-project/{project_id}", response_model=Dict[str, Any])
async def estimate_project_effort(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI估算整个项目工时

    返回项目总工时、缓冲时间、预估周期和置信度
    """
    # 验证项目存在
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    try:
        result = await effort_estimator.estimate_project(
            project_id=project_id,
            db=db,
        )
        return {
            "success": True,
            "data": result,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"估算失败: {str(e)}")
