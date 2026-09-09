"""
PMI中国AI项目管理社区 - AI自然语言查询API
提供自然语言到SQL的查询执行能力

[PMBOK KA: 跨领域 (Cross-area) — 自然语言查询、智能问答]
对应PMI第6版标准：自然语言查询

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — 智能查询与AI交互]"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.models import User
from app.core.security import get_current_user
from app.services.ai.nlp_query_engine import nlp_query_engine

router = APIRouter()


class NLPQueryExecuteRequest(BaseModel):
    query: str
    project_id: Optional[str] = None


class NLPQueryValidateRequest(BaseModel):
    query: str


class NLPQueryExample(BaseModel):
    text: str
    description: str
    category: str


# 示例查询列表
EXAMPLE_QUERIES = [
    NLPQueryExample(
        text="显示所有高优先级的待办任务",
        description="按优先级和状态筛选任务",
        category="筛选"
    ),
    NLPQueryExample(
        text="统计每个项目的任务完成率",
        description="按项目分组聚合统计",
        category="聚合"
    ),
    NLPQueryExample(
        text="张三本周完成了多少任务",
        description="按负责人和时间范围统计",
        category="统计"
    ),
    NLPQueryExample(
        text="显示进度低于50%的任务，按截止日期排序",
        description="条件筛选加排序",
        category="筛选"
    ),
    NLPQueryExample(
        text="列出所有活跃状态的项目",
        description="按项目状态筛选",
        category="筛选"
    ),
    NLPQueryExample(
        text="统计各风险类别的数量",
        description="按风险类别分组统计",
        category="聚合"
    ),
    NLPQueryExample(
        text="显示最近创建的10个任务",
        description="限制数量并排序",
        category="筛选"
    ),
    NLPQueryExample(
        text="预算超过100万的项目有哪些",
        description="按预算条件筛选项目",
        category="筛选"
    ),
]


@router.post("/execute", response_model=Dict[str, Any])
async def execute_nlp_query(
    request: NLPQueryExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """执行自然语言查询

    请求示例：
    {
        "query": "显示所有阻塞的高优先级任务",
        "project_id": "optional-project-id"
    }

    响应示例：
    {
        "success": true,
        "query_plan": {...},
        "results": {...},
        "summary": "共找到3条阻塞的高优先级任务...",
        "execution_time_ms": 1250
    }
    """
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="查询文本不能为空")

    try:
        # 1. 解析自然语言查询
        query_plan = await nlp_query_engine.parse_query(query_text)

        # 2. 执行查询
        results = await nlp_query_engine.execute_query(
            query_plan=query_plan,
            db=db,
            project_id=request.project_id
        )

        # 3. 生成自然语言摘要
        summary = await nlp_query_engine.generate_summary(results, query_text)

        return {
            "success": True,
            "query_plan": query_plan,
            "results": results,
            "summary": summary,
            "execution_time_ms": results.get("execution_time_ms", 0),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询执行失败: {str(e)}")


@router.post("/validate", response_model=Dict[str, Any])
async def validate_nlp_query(
    request: NLPQueryValidateRequest,
    current_user: User = Depends(get_current_user)
):
    """验证自然语言查询意图（不执行实际查询）

    请求示例：
    {
        "query": "显示所有阻塞的高优先级任务"
    }

    响应示例：
    {
        "success": true,
        "valid": true,
        "query_plan": {...},
        "message": "查询意图解析成功"
    }
    """
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="查询文本不能为空")

    try:
        query_plan = await nlp_query_engine.parse_query(query_text)

        # 验证查询计划的有效性
        entity = query_plan.get("entity", "")
        valid_entities = ["task", "project", "user", "risk", "milestone", "comment"]

        if entity not in valid_entities:
            return {
                "success": True,
                "valid": False,
                "query_plan": query_plan,
                "message": f"不支持的查询实体: {entity}",
            }

        return {
            "success": True,
            "valid": True,
            "query_plan": query_plan,
            "message": "查询意图解析成功",
        }

    except ValueError as e:
        return {
            "success": True,
            "valid": False,
            "query_plan": None,
            "message": str(e),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI服务暂时不可用: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询验证失败: {str(e)}")


@router.get("/examples", response_model=Dict[str, Any])
async def get_query_examples(
    current_user: User = Depends(get_current_user)
):
    """获取示例查询列表

    响应示例：
    {
        "success": true,
        "data": [
            {"text": "...", "description": "...", "category": "..."}
        ]
    }
    """
    return {
        "success": True,
        "data": [example.model_dump() for example in EXAMPLE_QUERIES],
    }
