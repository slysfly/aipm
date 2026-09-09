"""
PMI中国AI项目管理社区 - AI Agent 执行路由
包含Agent指令执行、对话管理、Agent能力目录
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User, AgentSession, Project, Risk, Resource, Task, TaskStatus
from app.models.budget import ProjectBudget
from app.models.system_llm_config import SystemLLMConfig
from app.schemas import SuccessResponse
from app.core.security import get_current_user
from app.services.ai.agent_engine import agent_engine
from app.services.ai.agent_registry import (
    list_agents as registry_list_agents,
    list_agents_grouped as registry_list_grouped,
    list_domain_ids,
    run_agent as registry_run_agent,
    get_structured_itto,
    normalize_agent_id,
    candidate_override_keys,
)
from app.services.ai.pmbok_agents import (
    get_pmbok_catalog, get_pmbok_catalog_grouped, PMBOK_REGISTRY, itto_to_structured,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =========================== ai_agent.py 路由 =========================== #


@router.post("/ai/agent/execute")
async def agent_execute(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    执行自然语言指令
    请求: {text, project_id, context}
    响应: {success, action_type, executed_steps, result, message}
    """
    text = request.get("text", "").strip()
    project_id = request.get("project_id")
    context = request.get("context", {})
    session_id = request.get("session_id")

    if not text:
        raise HTTPException(status_code=400, detail="指令内容不能为空")

    try:
        result = await agent_engine.execute_natural_language(
            db=db,
            user_id=current_user.id,
            project_id=project_id,
            text=text,
            context=context,
        )

        # 如果有session_id，保存对话记录
        if session_id:
            session_result = await db.execute(
                select(AgentSession).where(
                    AgentSession.id == session_id,
                    AgentSession.user_id == current_user.id
                )
            )
            session = session_result.scalar_one_or_none()
            if session:
                messages = session.messages or []
                messages.append({
                    "role": "user",
                    "content": text,
                    "timestamp": datetime.now().isoformat(),
                })
                messages.append({
                    "role": "assistant",
                    "content": result.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                    "action_type": result.get("action_type"),
                    "executed_steps": result.get("executed_steps"),
                    "result": result.get("result"),
                })
                session.messages = messages
                session.updated_at = datetime.now()
                await db.commit()

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent执行失败: {str(e)}")


@router.post("/ai/agent/chat")
async def agent_chat_stream(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Agent对话模式（支持多轮，SSE流式返回）
    请求: {message, session_id, project_id}
    """
    message = request.get("message", "").strip()
    session_id = request.get("session_id")
    project_id = request.get("project_id")

    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    # 获取或创建会话历史
    history_messages = []
    if session_id:
        session_result = await db.execute(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.user_id == current_user.id
            )
        )
        session = session_result.scalar_one_or_none()
        if session and session.messages:
            for msg in session.messages[-10:]:  # 最近10条
                if msg.get("role") in ["user", "assistant"]:
                    history_messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", ""),
                    })

    # 添加当前消息
    all_messages = history_messages + [{"role": "user", "content": message}]

    async def event_generator():
        full_content = ""
        try:
            async for chunk in agent_engine.chat_stream(
                messages=all_messages,
                project_id=project_id,
            ):
                full_content += chunk
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: Agent服务暂时不可用：{str(e)}\n\n"
            yield "data: [DONE]\n\n"

        # 保存对话记录
        if session_id:
            try:
                session_result = await db.execute(
                    select(AgentSession).where(
                        AgentSession.id == session_id,
                        AgentSession.user_id == current_user.id
                    )
                )
                session = session_result.scalar_one_or_none()
                if session:
                    messages = session.messages or []
                    messages.append({
                        "role": "user",
                        "content": message,
                        "timestamp": datetime.now().isoformat(),
                    })
                    messages.append({
                        "role": "assistant",
                        "content": full_content,
                        "timestamp": datetime.now().isoformat(),
                    })
                    session.messages = messages
                    session.updated_at = datetime.now()
                    await db.commit()
            except Exception as e:
                logger.warning("保存 Agent 会话消息失败（已忽略）: %s", e, exc_info=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/ai/agent/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取对话历史"""
    result = await db.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "session_id": session.id,
        "title": session.title,
        "project_id": session.project_id,
        "messages": session.messages or [],
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.post("/ai/agent/sessions", status_code=201)
async def create_session(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建新会话"""
    title = request.get("title", "新对话")
    project_id = request.get("project_id")

    session = AgentSession(
        user_id=current_user.id,
        project_id=project_id,
        title=title,
        messages=[],
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "title": session.title,
        "project_id": session.project_id,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/ai/agent/sessions")
async def list_sessions(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户的Agent会话列表"""
    query = select(AgentSession).where(AgentSession.user_id == current_user.id)
    if project_id:
        query = query.where(AgentSession.project_id == project_id)

    query = query.order_by(AgentSession.updated_at.desc())
    result = await db.execute(query)
    sessions = result.scalars().all()

    return {
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "project_id": s.project_id,
                "message_count": len(s.messages) if s.messages else 0,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@router.delete("/ai/agent/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除会话"""
    result = await db.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    await db.delete(session)
    await db.commit()

    return SuccessResponse(message="会话删除成功")


# =========================== agents.py 路由 =========================== #
# 注：Agent 目录与执行能力统一由 app.services.ai.agent_registry 派生（单一真相源），
# 不再在此维护重复硬编码 catalog。


async def _compute_telemetry(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    domain_ids = list_domain_ids()  # [report, evm, risk, ...]（来自注册中心）
    sessions = (await db.execute(select(AgentSession))).scalars().all()
    counts: Dict[str, int] = {a: 0 for a in domain_ids}
    last_active: Dict[str, Any] = {a: None for a in domain_ids}
    for s in sessions:
        title = s.title or ""
        if title.startswith("["):
            end = title.find("]")
            tag = title[1:end] if end > 0 else ""
            if tag in counts:
                counts[tag] += 1
                if s.updated_at and (last_active[tag] is None or s.updated_at > last_active[tag]):
                    last_active[tag] = s.updated_at

    coverage = {
        "report": (await db.execute(select(func.count(Project.id)).where(Project.is_deleted.is_(False)))).scalar() or 0,
        "evm": (await db.execute(select(func.count(ProjectBudget.id)))).scalar() or 0,
        "risk": (await db.execute(select(func.count(Risk.id)))).scalar() or 0,
        "resource": (await db.execute(select(func.count(Resource.id)).where(Resource.is_active.is_(True)))).scalar() or 0,
        "wbs": (await db.execute(select(func.count(Task.id)).where(Task.parent_task_id.is_(None), Task.is_deleted.is_(False)))).scalar() or 0,
        "quality": (await db.execute(select(func.count(Task.id)).where(Task.status == TaskStatus.TESTING.value, Task.is_deleted.is_(False)))).scalar() or 0,
        "compliance": 0,
        "meeting_minutes": (await db.execute(select(func.count(Task.id)).where(Task.category == "meeting_action", Task.is_deleted.is_(False)))).scalar() or 0,
        "health_check": 0,
        "decision": 0,
    }
    return {"counts": counts, "last_active": last_active, "coverage": coverage}


def _compute_status(llm_active: bool, team_running: bool) -> str:
    if team_running:
        return "busy"
    if llm_active:
        return "online"
    return "offline"


@router.get("/agents")
async def list_agents(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """获取 AI Agent 能力目录及实时状态（统一注册中心派生，含真实遥测）"""
    cfg = (await db.execute(select(SystemLLMConfig).order_by(SystemLLMConfig.updated_at.desc()))).scalars().first()
    llm_active = bool(cfg and cfg.is_active and getattr(cfg, "_api_key", None))
    team_running = False  # 多智能体编排已下线，不再有团队运行中

    tele = await _compute_telemetry(db)

    agents = []
    for a in registry_list_agents(source="domain"):
        status = _compute_status(llm_active, team_running)
        la = tele["last_active"].get(a["id"])
        agents.append({
            **a,  # id/name/name_en/type/icon/color/description/accuracy/inputHint/tags/category/source/kind
            "status": status,
            "tasksCompleted": tele["counts"].get(a["id"], 0),
            "coverage": tele["coverage"].get(a["id"], 0),
            "lastActive": la.isoformat() if la else "待命",
        })
    return {"items": agents, "total": len(agents)}


@router.get("/agents/pmbok-catalog", summary="PMBOK / CPMAI 过程 Agent 目录")
async def pmbok_catalog(_: User = Depends(get_current_user)):
    """返回全部 PMBOK 第6版/第8版 与 CPMAI 知识单元（按体系分组：原则/绩效域/裁剪/CPMAI阶段/可信AI）。"""
    return {
        "items": get_pmbok_catalog(),
        "grouped": get_pmbok_catalog_grouped(),
        "total": len(PMBOK_REGISTRY),
    }


@router.get("/agents/registry", summary="统一 Agent 注册中心（全量）")
async def agent_registry_full(_: User = Depends(get_current_user)):
    """返回全部可调用 Agent（领域 + PMBOK/CPMAI），供工作流编排面板拉取工具箱。

    每个条目含 id / name / name_en / kind / category / source / type / icon / color /
    description / accuracy / tags / inputHint / extra(ITTO)。
    """
    items = registry_list_agents()
    return {
        "items": items,
        "grouped": registry_list_grouped(),
        "total": len(items),
    }


class AgentRunRequest(BaseModel):
    agent_type: str
    project_id: Optional[str] = None
    input: str = ""
    options: Dict[str, Any] = {}


@router.post("/agents/run")
async def run_agent_endpoint(
    req: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """直接驱动一个 Agent 执行任务（结果写回 AgentSession 供遥测）。
    支持领域 Agent（report/evm/...）与 PMBOK 过程 Agent（pmbok:4.1），统一取自注册中心。"""
    try:
        result = await registry_run_agent(
            agent_type=req.agent_type,
            db=db, user_id=current_user.id,
            project_id=req.project_id, input_text=req.input, options=req.options,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI 服务不可用: {str(e)}")
    return {"success": True, "agent_type": req.agent_type, "result": result}


@router.get("/agents/runs")
async def list_agent_runs(
    agent_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查看 Agent 真实运行历史（来自 AgentSession）"""
    query = select(AgentSession)
    if agent_type:
        query = query.where(AgentSession.title.like(f"[{agent_type}]%"))
    query = query.order_by(desc(AgentSession.updated_at)).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    items = []
    for s in rows:
        tag = ""
        if s.title and s.title.startswith("["):
            end = s.title.find("]")
            tag = s.title[1:end] if end > 0 else ""
        items.append({
            "id": s.id, "agent_type": tag, "summary": s.title,
            "project_id": s.project_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return {"items": items, "total": len(items)}


# --------------------------------------------------------------------------- #
# Agent 个性化覆盖（深度编辑持久化）
#
# 设计原则：
# - 内置 Agent 永远是"开箱即用完整可用"的（注册表 *_build_* 函数已写死 ITTO + 过程说明）。
# - 用户/管理员可在前端"深度编辑"面板调整 name / description / input_hint /
#   inputs / tools / outputs / process / system_prompt，这些调整以"覆盖"形式
#   落到 backend/data/agent_overrides.json，下次 run 时优先读。
# - 当前文件级 JSON 持久化足够 1-100 人协作；后续可平滑迁移到数据库表。
# --------------------------------------------------------------------------- #
_OVERRIDE_DIR = Path(__file__).resolve().parents[4] / "data"
_OVERRIDE_FILE = _OVERRIDE_DIR / "agent_overrides.json"


def _load_overrides() -> Dict[str, Dict[str, Any]]:
    try:
        if _OVERRIDE_FILE.exists():
            with _OVERRIDE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("read agent_overrides.json failed: %s", e)
    return {}


def _save_overrides(data: Dict[str, Dict[str, Any]]) -> None:
    _OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _OVERRIDE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(_OVERRIDE_FILE)


class AgentOverridePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    input_hint: Optional[str] = None
    inputs: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    outputs: Optional[List[str]] = None
    # 完整结构化 ITTO（含 optional / enabled 等可配置项），优先于上面的纯文本列表
    inputs_struct: Optional[List[Dict[str, Any]]] = None
    tools_struct: Optional[List[Dict[str, Any]]] = None
    outputs_struct: Optional[List[Dict[str, Any]]] = None
    process: Optional[str] = None
    system_prompt: Optional[str] = None
    updated_by: Optional[str] = None
    note: Optional[str] = None


@router.get("/agents/{agent_id}/override")
async def get_agent_override(
    agent_id: str,
    _: User = Depends(get_current_user),
):
    """读取某个 Agent 的个性化覆盖（深度编辑配置）。同时返回注册表里的"完整可用默认"。

    ID 归一化：``pmbok:<id>`` 与原始 ``<id>``（如 ``4.1``）都能命中同一份覆盖。
    """
    all_ovr = _load_overrides()
    ovr = next(
        (all_ovr[k] for k in candidate_override_keys(agent_id) if k in all_ovr),
        {},
    )
    base = None
    for a in registry_list_agents():
        if a["id"] == agent_id:
            base = a
            break
    if not base:
        for p in get_pmbok_catalog():
            if p["id"] == agent_id:
                base = {
                    "id": p["id"],
                    "name": p.get("name_cn"),
                    "description": p.get("summary"),
                    "extra": p,
                    "inputs": p.get("inputs", []),
                    "tools": p.get("tools", []),
                    "outputs": p.get("outputs", []),
                    "process": p.get("v8", ""),
                }
                break
    # 统一附上结构化 ITTO（inputs/tools/outputs 均为可配置项）
    if base is not None:
        sitto = get_structured_itto(agent_id)
        base = {**base, "inputs_struct": sitto["inputs"],
                "tools_struct": sitto["tools"], "outputs_struct": sitto["outputs"]}
    return {
        "agent_id": agent_id,
        "override": ovr,
        "base": base,
        "has_override": bool(ovr),
    }
@router.put("/agents/{agent_id}/override")
async def put_agent_override(
    agent_id: str,
    payload: AgentOverridePayload,
    current_user: User = Depends(get_current_user),
):
    """保存某个 Agent 的个性化覆盖。覆盖字段允许为空（清空）。

    ID 归一化：无论前端传入 ``4.1`` 还是 ``pmbok:4.1``，均 consolid 到同一份覆盖
    （删除其它写法的残留 key，避免分裂存储）。
    """
    # 归一为规范 key（pmbok:<id> 或领域 Agent 原 id），并清掉其它写法的残留
    canon = normalize_agent_id(agent_id)
    data = _load_overrides()
    for k in candidate_override_keys(agent_id):
        data.pop(k, None)
    now = datetime.now().isoformat()
    data[canon] = {
        "name": payload.name,
        "description": payload.description,
        "input_hint": payload.input_hint,
        "inputs": payload.inputs or [],
        "tools": payload.tools or [],
        "outputs": payload.outputs or [],
        "inputs_struct": payload.inputs_struct,
        "tools_struct": payload.tools_struct,
        "outputs_struct": payload.outputs_struct,
        "process": payload.process,
        "system_prompt": payload.system_prompt,
        "note": payload.note,
        "updated_at": now,
        "updated_by": payload.updated_by or (
            current_user.username if hasattr(current_user, "username") else str(current_user.id)
        ),
    }
    _save_overrides(data)
    return {"ok": True, "agent_id": canon, "saved_at": now}


@router.delete("/agents/{agent_id}/override")
async def delete_agent_override(
    agent_id: str,
    _: User = Depends(get_current_user),
):
    """删除覆盖（恢复为内置默认值）。兼容 ``pmbok:<id>`` 与原始 ``<id>`` 两种写法。"""
    data = _load_overrides()
    changed = False
    for k in candidate_override_keys(agent_id):
        if k in data:
            data.pop(k)
            changed = True
    if changed:
        _save_overrides(data)
    return {"ok": True, "agent_id": normalize_agent_id(agent_id)}


# --------------------------------------------------------------------------- #
# Agent 物料工作区（结构化 ITTO 运行时管线）
#
# 流程：prepare（运行前检查系统已有物料） → generate-template（缺失时手工上传基础信息
#       并由 AI 生成统一格式模板） → run-material（聚合输入 + 工具技术 → 输出指定文件）。
# --------------------------------------------------------------------------- #
from app.services.ai.agent_materials import (
    prepare as material_prepare,
    generate_template as material_generate_template,
    run_material as material_run,
    list_materials as material_list,
    get_material_content,
)


class AgentPrepareRequest(BaseModel):
    project_id: Optional[str] = None


class AgentGenerateTemplateRequest(BaseModel):
    project_id: Optional[str] = None
    input_key: str
    input_label: str
    basic_info: str = ""
    file_content: str = ""
    file_name: str = ""


class AgentRunMaterialRequest(BaseModel):
    project_id: Optional[str] = None
    input_refs: Dict[str, str] = {}   # {input_key: material_ref}
    selected_tools: List[str] = []    # 勾选的工具技术 key 列表（空=全部）
    user_input: str = ""


@router.post("/agents/{agent_id}/prepare")
async def agent_prepare(
    agent_id: str,
    req: AgentPrepareRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """运行前检查：返回每个输入物料的存在状态与缺失清单（含项目知识库文档匹配）。"""
    return await material_prepare(req.project_id, agent_id, db)


@router.post("/agents/{agent_id}/generate-template")
async def agent_generate_template(
    agent_id: str,
    req: AgentGenerateTemplateRequest,
    _: User = Depends(get_current_user),
):
    """手工上传基础信息 → AI 生成统一格式模板文件材料（落库到工作区）。"""
    rec = await material_generate_template(
        req.project_id, agent_id, req.input_key, req.input_label,
        basic_info=req.basic_info, file_content=req.file_content, file_name=req.file_name,
    )
    return rec


@router.post("/agents/{agent_id}/run-material")
async def agent_run_material(
    agent_id: str,
    req: AgentRunMaterialRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """执行物料管线：聚合输入物料 + 勾选工具技术 → AI 处理 → 输出指定文件。"""
    if not req.project_id:
        raise HTTPException(status_code=400, detail="运行物料管线需要指定 project_id")
    return await material_run(
        req.project_id, agent_id, db,
        input_refs=req.input_refs, selected_tools=req.selected_tools,
        user_input=req.user_input,
    )


@router.get("/agents/materials")
async def agent_list_materials(
    project_id: Optional[str] = None,
    _: User = Depends(get_current_user),
):
    """列出某项目的全部 Agent 物料（输入模板 + 输出文件）。"""
    return material_list(project_id)


@router.get("/agents/materials/{ref}/download")
async def agent_download_material(
    ref: str,
    project_id: Optional[str] = None,
    _: User = Depends(get_current_user),
):
    """下载某份物料（模板/输出）文件，Markdown 以 text/markdown 返回。"""
    m = get_material_content(project_id or "_global", ref)
    if not m:
        raise HTTPException(status_code=404, detail="物料不存在")
    from fastapi.responses import Response
    return Response(
        content=m["content"].encode("utf-8", "ignore"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ref}.md"'},
    )
