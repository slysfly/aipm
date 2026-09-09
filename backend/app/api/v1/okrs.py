"""
OKR (Objectives and Key Results) API

[PMBOK KA: 相关方管理 (Stakeholder) — 目标管理、干系人期望对齐]
对应PMI第6版标准：目标管理、干系人期望管理
"""

import json
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_active_user
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.okr_whiteboard_document import Objective
from app.models import Project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/okrs", tags=["OKR 目标管理"], dependencies=[Depends(get_current_active_user)])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class KeyResultSchema(BaseModel):
    id: Optional[str] = None
    title: str = ""
    description: str = ""
    target: float = 100
    current: float = 0
    unit: str = "%"
    progress: int = 0
    weight: float = 1.0


class OkrCreate(BaseModel):
    objective: str
    project_id: Optional[str] = None
    year: str = "2026"
    quarter: str = "Q3"
    owner: str = ""
    keyResults: List[KeyResultSchema] = []


class OkrUpdate(BaseModel):
    objective: Optional[str] = None
    project_id: Optional[str] = None
    year: Optional[str] = None
    quarter: Optional[str] = None
    owner: Optional[str] = None
    progress: Optional[int] = None
    keyResults: Optional[List[KeyResultSchema]] = None


class AiGenerateKRsRequest(BaseModel):
    """AI 生成 KR 的请求体（project_id 可选，优先使用 OKR 已关联的项目）"""
    count: int = 4  # 生成几个 KR
    extra_context: Optional[str] = None  # 额外约束/背景


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_okrs(
    year: Optional[str] = Query(None),
    quarter: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Objective))
    items = [o.to_dict() for o in result.scalars().all()]
    if year:
        items = [i for i in items if i.get("year") == year]
    if quarter:
        items = [i for i in items if i.get("quarter") == quarter]
    if project_id:
        items = [i for i in items if i.get("project_id") == project_id]
    return {"items": items, "total": len(items)}


@router.get("/{okr_id}")
async def get_okr(okr_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Objective, okr_id)
    if not obj:
        raise HTTPException(404, "OKR 不存在")
    return obj.to_dict()


@router.post("", status_code=201)
async def create_okr(payload: OkrCreate, db: AsyncSession = Depends(get_db)):
    # 验证 project_id 存在性（如果提供）
    if payload.project_id:
        proj = await db.get(Project, payload.project_id)
        if not proj:
            raise HTTPException(400, f"项目不存在 (id={payload.project_id})")

    kr_list = [kr.model_dump() for kr in payload.keyResults] if payload.keyResults else []
    progress = _calc_progress(kr_list)
    obj = Objective(
        objective=payload.objective,
        project_id=payload.project_id,
        year=payload.year,
        quarter=payload.quarter,
        owner=payload.owner,
        progress=progress,
        key_results=kr_list,
    )
    db.add(obj)
    await db.flush()
    return obj.to_dict()


@router.put("/{okr_id}")
async def update_okr(okr_id: str, payload: OkrUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Objective, okr_id)
    if not obj:
        raise HTTPException(404, "OKR 不存在")

    # 验证 project_id 存在性
    if payload.project_id:
        proj = await db.get(Project, payload.project_id)
        if not proj:
            raise HTTPException(400, f"项目不存在 (id={payload.project_id})")

    data = payload.model_dump(exclude_unset=True)
    if "keyResults" in data and data["keyResults"] is not None:
        krs = data["keyResults"]
        data["key_results"] = krs
        data["progress"] = _calc_progress(krs)
        del data["keyResults"]
    for k, v in data.items():
        setattr(obj, k, v)
    await db.flush()
    return obj.to_dict()


@router.delete("/{okr_id}")
async def delete_okr(okr_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Objective, okr_id)
    if not obj:
        raise HTTPException(404, "OKR 不存在")
    await db.delete(obj)
    return {"ok": True}


# ---------------------------------------------------------------------------
# AI 生成 KR —— 核心能力
# ---------------------------------------------------------------------------

KR_GENERATION_PROMPT = """你是一位资深的 OKR（目标与关键结果）管理顾问，精通 PMBOK 项目管理方法论。
请根据以下「项目信息」和「OKR 目标」，自动生成 {count} 个可考核、可落地的关键结果（Key Result）。

## 项目信息
{project_context}

## OKR 目标
{objective}

## 输出要求
每个 KR 必须满足 SMART 原则：
- **Specific**（具体）：明确做什么，不模糊
- **Measurable**（可衡量）：有量化指标和目标值
- **Achievable**（可实现）：基于项目现状可达
- **Relevant**（相关）：直接支撑目标达成
- **Time-bound**（有时限）：与季度/项目周期对齐

请严格按以下 JSON 数组格式输出（不要包含 markdown 代码块标记，只输出纯 JSON）：
[
  {{
    "title": "KR 标题（简短有力，15 字以内）",
    "description": "详细描述（说明如何衡量、验收标准）",
    "target": 目标数值（数字）,
    "unit": "单位（% / 个 / 天 / 分 / 元 / 次 等）",
    "weight": 权重（数字，所有 KR 权重之和建议为 10）
  }}
]

{extra_context}
"""


@router.post("/{okr_id}/ai-generate-krs")
async def ai_generate_krs(
    okr_id: str,
    req: AiGenerateKRsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI 根据关联项目的实际情况，自动生成可考核可落地的 KR 子项。
    流程：读取 OKR → 聚合项目上下文 → LLM 生成 KR → 回写数据库。
    """
    from app.services.ai_service import ai_service

    # 1) 读取 OKR
    obj = await db.get(Objective, okr_id)
    if not obj:
        raise HTTPException(404, "OKR 不存在")

    # 2) 聚合项目上下文
    pid = obj.project_id or req.extra_context  # 优先用已关联项目
    project_context = ""
    if pid and len(pid) > 5:
        try:
            project_context = await ai_service._gather_project_context(pid)
        except Exception as exc:
            logger.warning("聚合项目上下文失败 (pid=%s): %s", pid, exc)
            project_context = f"项目 ID: {pid}（未能加载明细）"

    if not project_context or not project_context.strip():
        project_context = "（未关联具体项目，请根据目标本身生成通用型 KR）"

    # 3) 构造 prompt 并调用 LLM（带重试，应对偶发超时 / 限流）
    prompt = KR_GENERATION_PROMPT.format(
        count=req.count,
        project_context=project_context,
        objective=obj.objective,
        extra_context=f"\n## 额外要求\n{req.extra_context}" if req.extra_context else "",
    )

    krs: list = []
    last_err = "AI 服务暂时不可用，请稍后重试"
    for attempt in range(3):  # 首次 + 2 次重试，应对偶发超时/限流
        try:
            result = await ai_service.chat(prompt)
        except Exception as exc:
            logger.error("AI 生成 KR 调用失败: %s", exc, exc_info=True)
            raise HTTPException(502, f"AI 服务暂时不可用: {exc}")

        # chat() 在内部捕获异常后会返回带 error_type/retryable 的错误字典（不抛异常），
        # 必须识别并正确上抛，避免把错误提示文本当成正常 message 去解析 → 静默 0 条
        if "error_type" in result or "retryable" in result:
            last_err = result.get("message") or last_err
            if result.get("retryable") and attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))  # 退避后重试：2s, 4s
                continue
            raise HTTPException(502, last_err)

        ai_text = result.get("message", "")
        if ai_text:
            krs = _parse_kr_json(ai_text)
        if krs:
            break
        # 解析无果：可能是 LLM 返回了非 JSON 内容，再尝试一次
        if attempt < 2:
            await asyncio.sleep(1.0)
            continue
        raise HTTPException(502, last_err if "AI服务" in last_err else "AI 生成的 KR 无法解析，请重试")

    # 4) 解析 LLM 返回的 JSON（krs 已在上方获得）
    # 5) 追加到现有 KR 列表并回写
    existing = obj.key_results or []
    # 给新生成的 KR 分配唯一 id
    import time
    for kr in krs:
        kr["id"] = f"kr-{int(time.time() * 1000)}-{hash(kr.get('title', '')) % 10000}"
        kr.setdefault("current", 0)
        kr.setdefault("progress", 0)

    updated_krs = existing + krs
    obj.key_results = updated_krs
    obj.progress = _calc_progress(updated_krs)
    await db.flush()

    return {
        "ok": len(krs) > 0,
        "generated_krs": krs,
        "total_krs": len(updated_krs),
        "message": f"成功生成 {len(krs)} 个 KR" if krs else "未能生成 KR，请重试",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calc_progress(krs: list) -> int:
    """根据 KR 列表计算总体进度（加权平均）"""
    if not krs:
        return 0
    total_weight = sum(kr.get("weight", 1.0) for kr in krs)
    if total_weight == 0:
        return 0
    weighted_sum = sum(
        kr.get("progress", 0) * kr.get("weight", 1.0) for kr in krs
    )
    return int(weighted_sum / total_weight)


def _parse_kr_json(raw: str) -> list:
    """
    从 LLM 返回文本中提取 KR JSON 数组。
    容错处理：去除 markdown 代码块、前后杂字；数组解析失败时回退提取单个 {…} 对象；
    兼容 {"krs":[...]} / {"key_results":[...]} 等包裹形态。
    """
    import re

    if not raw or not raw.strip():
        return []

    text = raw.strip()

    # 尝试提取 ```json ... ``` 或 ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    def _validate(items):
        out = []
        for item in items:
            if isinstance(item, dict) and item.get("title"):
                out.append({
                    "title": str(item.get("title", "")),
                    "description": str(item.get("description", "")),
                    "target": _to_float(item.get("target", 100)),
                    "unit": str(item.get("unit", "%")),
                    "weight": _to_float(item.get("weight", 1.0)),
                })
        return out

    # 1) 直接尝试整段 JSON（可能是 [..] 或 {..包裹数组..}）
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return _validate(data)
        if isinstance(data, dict):
            for key in ("krs", "key_results", "keyResults", "results", "data"):
                if isinstance(data.get(key), list):
                    return _validate(data[key])
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) 截取 [ ... ] 区间
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return _validate(data)
        except (json.JSONDecodeError, ValueError):
            pass

    # 3) 兜底：用正则提取所有独立 { ... } 对象并组装
    try:
        objs = re.findall(r"\{[^{}]*\}", text, re.DOTALL)
        items = []
        for o in objs:
            try:
                items.append(json.loads(o))
            except (json.JSONDecodeError, ValueError):
                continue
        if items:
            return _validate(items)
    except Exception:
        pass

    logger.warning("KR JSON 解析失败，原始文本前 500 字: %s", raw[:500])
    return []


def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
