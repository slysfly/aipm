"""
PMI中国AI项目管理社区 - 工作流可视编排 API（多租户版）

支持：
- 每个项目经理独立编排自己的工作流（owner_id = 创建者）
- 多种工作流并存（模板列表）
- 每个项目可以绑定一套独特的工作流（project_id）
- 工作流 DAG 真实调度：步骤的 agent_type 可为已有领域/ITTO Agent（evm/risk/.../pmbok:4.1/知识单元）

核心能力（本次增强）：
- **内容真正流动**：上游 Agent 的输出文本会真实喂入下游 Agent 的输入。
  - 扇入(fan-in)：一个步骤的 depends_on 可含多个上游 → 多份上游输出合并后作为本步骤输入。
  - 扇出(fan-out)：一个步骤可被多个下游步骤依赖 → 其输出被多份下游复用。
- **统一执行器**：所有 Agent 统一走 run_material（同时覆盖 85 ITTO 物料 Agent 与 10 领域 Agent）。
- **异步 + 实时进度**：execute 立即返回 run_id，后台任务逐节点更新状态（pending/running/completed/failed），
  轮询 /workflows/runs/{run_id} 即可看到实时进度；运行历史文件化持久化（data/workflow_runs/）。
- **可选精确槽位映射**：input_mapping 可将指定上游输出绑定到 ITTO Agent 的某个输入槽；
  未指定时默认把全部上游输出合并进 user_input，保证内容一定流动。

存储复用 AgentSession 表（user_id=owner, project_id=绑定项目, title="[workflow] {name}"），无需数据库迁移。

[PMBOK KA: 跨领域 | PG: 执行 — Agent工作流可视编排]
[PMBOK 8th: AI-Driven Workflow Orchestration]
"""

from __future__ import annotations

import json
import uuid
import logging
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User, AgentSession
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["工作流编排"])

# --------------------------------------------------------------------------- #
# 内存运行时（单进程：异步执行结果的实时缓存；完成后落盘到 data/workflow_runs/）
# --------------------------------------------------------------------------- #

_runs: Dict[str, Dict[str, Any]] = {}

WF_PREFIX = "[workflow] "
RUN_PREFIX = "[workflow_run] "
_RUN_DIR = Path(__file__).resolve().parents[3] / "data" / "workflow_runs"


# --------------------------------------------------------------------------- #
# Pydantic 模型
# --------------------------------------------------------------------------- #

class WorkflowStep(BaseModel):
    """工作流中的一个步骤（DAG 节点）。

    - agent_type：Agent 类型，如 evm / risk / wbs / pmbok:4.1 / 知识单元 id。
    - label：步骤显示标签，同时作为 DAG 节点 ID（用于 depends_on 引用）。
    - depends_on：依赖的步骤 label 列表。
        * 多个 → 扇入（本步骤等所有上游完成，上游输出合并为输入）。
        * 被多个步骤引用 → 扇出（本步骤输出被多份下游复用）。
    - user_input：本步骤的内联补充输入文本（与上游输出拼接后喂入 Agent）。
    - selected_tools：勾选的工具技术 key（ITTO Agent 用；空=全部）。
    - input_mapping：可选精确槽位映射 {输入槽key: 上游label}，把指定上游输出绑到该槽。
    """
    agent_type: str = Field(..., description="Agent 类型，如 evm / risk / wbs / pmbok:4.1")
    label: str = Field(default="", description="步骤显示标签（也作为 DAG 节点 ID）")
    depends_on: List[str] = Field(default_factory=list, description="依赖的步骤标签列表（空=根节点）")
    user_input: str = Field(default="", description="本步骤内联补充输入文本")
    selected_tools: List[str] = Field(default_factory=list, description="勾选的工具技术 key（空=全部）")
    input_mapping: Dict[str, str] = Field(default_factory=dict, description="可选：{输入槽key: 上游label} 精确槽位绑定")
    config: Dict[str, Any] = Field(default_factory=dict, description="保留字段（兼容旧前端）")


class ExecuteRequest(BaseModel):
    """执行工作流请求"""
    steps: Optional[List[WorkflowStep]] = Field(default=None, description="步骤列表（DAG）；与 workflow_id 二选一")
    workflow_id: Optional[str] = Field(default=None, description="已保存工作流 ID；提供则忽略 steps")
    project_id: Optional[str] = Field(default=None, description="目标项目 ID")


class TemplateSaveRequest(BaseModel):
    """保存模板请求（兼容旧前端）"""
    name: str = Field(..., min_length=1, max_length=128, description="模板名称")
    description: str = Field(default="", max_length=512, description="模板描述")
    steps: List[Dict[str, Any]] = Field(..., description="工作流步骤定义")


class WorkflowCreateRequest(BaseModel):
    """创建工作流"""
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    is_global: bool = Field(default=False, description="是否全局模板（所有 PM 可用）")
    project_id: Optional[str] = Field(default=None, description="创建时即绑定到某项目")
    steps: List[WorkflowStep] = Field(default_factory=list)


class WorkflowUpdateRequest(BaseModel):
    """更新工作流（部分字段）"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    is_global: Optional[bool] = None
    steps: Optional[List[WorkflowStep]] = None


class WorkflowBindRequest(BaseModel):
    """绑定/解绑工作流到项目"""
    project_id: Optional[str] = Field(default=None, description="目标项目 ID；传 null 表示解绑")


class ValidateRequest(BaseModel):
    """校验工作流（不执行）"""
    steps: Optional[List[WorkflowStep]] = None
    workflow_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# 序列化与权限
# --------------------------------------------------------------------------- #

def _wf_payload(msg: Any) -> Dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    try:
        return json.loads(msg) if isinstance(msg, str) else {}
    except Exception:
        return {}


def _serialize(session: AgentSession) -> Dict[str, Any]:
    msg = session.messages[0] if isinstance(session.messages, list) and session.messages else {}
    p = _wf_payload(msg)
    return {
        "id": session.id,
        "name": p.get("name") or session.title.replace(WF_PREFIX, ""),
        "description": p.get("description", ""),
        "owner_id": session.user_id,
        "is_global": bool(p.get("is_global", False)),
        "project_id": session.project_id,
        "steps": p.get("steps", []),
        "process_ids": p.get("process_ids", []),
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


async def _load_workflow(wf_id: str, db: AsyncSession) -> AgentSession:
    s = (await db.execute(
        select(AgentSession).where(AgentSession.id == wf_id, AgentSession.title.like(f"{WF_PREFIX}%"))
    )).scalars().first()
    if not s:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return s


def _can_edit(session: AgentSession, user: User) -> bool:
    return user.is_superuser or session.user_id == user.id


# --------------------------------------------------------------------------- #
# DAG 拓扑排序（Kahn 算法，含环路检测）
# --------------------------------------------------------------------------- #

def _topological_sort(steps: List[WorkflowStep]) -> Optional[List[WorkflowStep]]:
    """返回拓扑序；存在环路则返回 None。"""
    step_map = {s.label or s.agent_type: s for s in steps}
    indeg = {k: 0 for k in step_map}
    adj: Dict[str, List[str]] = {k: [] for k in step_map}
    for s in steps:
        k = s.label or s.agent_type
        for dep in s.depends_on:
            if dep in step_map:
                adj[dep].append(k)
                indeg[k] += 1
    q = deque(k for k in step_map if indeg[k] == 0)
    order: List[WorkflowStep] = []
    while q:
        n = q.popleft()
        order.append(step_map[n])
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if len(order) != len(step_map):
        return None
    return order


# --------------------------------------------------------------------------- #
# 单节点执行（统一走 run_material，覆盖 ITTO + 领域 Agent）
# --------------------------------------------------------------------------- #

async def _run_node(
    agent_type: str, project_id: Optional[str], user_input: str,
    input_refs: Dict[str, str], selected_tools: List[str], db: AsyncSession,
) -> str:
    """执行单个 Agent 节点，返回其输出文本（合并所有 output.content）。"""
    from app.services.ai.agent_materials import run_material
    res = await run_material(
        project_id, agent_type, db,
        input_refs=input_refs or {},
        selected_tools=selected_tools or [],
        user_input=user_input or "",
    )
    outputs = res.get("outputs") or []
    text = "\n\n---\n\n".join(o.get("content", "") for o in outputs if o.get("content"))
    return text


# --------------------------------------------------------------------------- #
# DAG 执行核心（在后台任务中运行；逐节点更新 _runs 实现实时进度）
# --------------------------------------------------------------------------- #

async def _run_dag(
    steps: List[WorkflowStep], project_id: Optional[str],
    db: AsyncSession, run_id: str,
) -> Dict[str, Any]:
    """真实调度 DAG，返回各步骤结果；同时增量更新 _runs[run_id]['results']。"""
    ordered = _topological_sort(steps)
    if ordered is None:
        raise ValueError("工作流存在环路（cycle），无法执行")

    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    run = _runs.get(run_id)
    if run is None:
        run = _runs[run_id] = {"run_id": run_id, "status": "running", "results": {}}

    for step in ordered:
        label = step.label or step.agent_type
        run["results"].setdefault(label, {})["status"] = "running"

        # —— 收集上游输出（扇入：多份上游合并）——
        upstream_texts: List[str] = []
        for dep in step.depends_on:
            d = results.get(dep)
            if d and d.get("status") == "completed":
                upstream_texts.append(d.get("output_text", ""))
        merged = "\n\n---\n\n".join(t for t in upstream_texts if t)

        # —— 可选精确槽位映射（input_mapping：上游输出 → 本 Agent 输入槽）——
        input_refs: Dict[str, str] = {}
        if step.input_mapping:
            from app.services.ai.agent_materials import store_material
            for in_key, up_label in step.input_mapping.items():
                up = results.get(up_label)
                if up and up.get("status") == "completed":
                    rec = store_material(
                        project_id or "_global",
                        title=f"{up_label}→{in_key}",
                        content=up.get("output_text", ""),
                        kind="file", source="workflow",
                        agent_id=step.agent_type, input_key=in_key,
                    )
                    input_refs[in_key] = rec["ref"]

        # —— 内联输入 + 上游输出 合并为本步骤输入 ——
        user_input = (merged + ("\n\n" + step.user_input if step.user_input else "")).strip()
        input_preview = user_input[:400]

        try:
            text = await _run_node(
                step.agent_type, project_id, user_input, input_refs, step.selected_tools, db,
            )
            results[label] = {
                "agent_type": step.agent_type, "status": "completed",
                "output_text": text, "input_preview": input_preview,
            }
            run["results"][label] = {
                "status": "completed",
                "agent_type": step.agent_type,
                "input_preview": input_preview,
                "output_preview": text[:500],
            }
            logger.info("Step [%s] completed", label)
        except Exception as e:  # 单节点失败不阻断整条 DAG
            errors[label] = str(e)
            results[label] = {
                "agent_type": step.agent_type, "status": "failed",
                "error": str(e), "input_preview": input_preview,
            }
            run["results"][label] = {
                "status": "failed", "agent_type": step.agent_type,
                "input_preview": input_preview, "error": str(e),
            }
            logger.error("Step [%s] failed: %s", label, e)

    return {"results": results, "errors": errors}


async def _execute_async(run_id: str, steps: List[WorkflowStep],
                         project_id: Optional[str], user_id: str) -> None:
    """后台任务：自管 DB 会话执行 DAG，增量更新 _runs，完成后落盘运行历史。"""
    from app.db.session import async_session_maker
    run = _runs.get(run_id) or _runs.setdefault(run_id, {"run_id": run_id, "status": "running", "results": {}})
    async with async_session_maker() as db:
        try:
            dag_result = await _run_dag(steps, project_id, db, run_id)
            run["status"] = "completed" if not dag_result["errors"] else "partial_failure"
            run["errors"] = dag_result["errors"]
            run["completed_at"] = datetime.now().isoformat()
        except Exception as e:
            run["status"] = "failed"
            run["errors"] = {"_global": str(e)}
            run["completed_at"] = datetime.now().isoformat()
            logger.exception("workflow run %s failed", run_id)
        finally:
            _persist_run(run)


def _persist_run(run: Dict[str, Any]) -> None:
    """将完成的运行落盘（data/workflow_runs/{run_id}.json），重启后仍可查。"""
    try:
        _RUN_DIR.mkdir(parents=True, exist_ok=True)
        ( _RUN_DIR / f"{run['run_id']}.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("persist workflow run failed: %s", e)


def _load_run_file(run_id: str) -> Optional[Dict[str, Any]]:
    p = _RUN_DIR / f"{run_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------- #
# API 端点
# --------------------------------------------------------------------------- #

@router.post("", summary="创建工作流")
async def create_workflow(
    req: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一条工作流（属于当前 PM）。is_global=true 则成为全局模板。"""
    if not req.steps:
        raise HTTPException(status_code=400, detail="工作流至少需要一个步骤")
    session = AgentSession(
        user_id=current_user.id,
        project_id=req.project_id,
        title=f"{WF_PREFIX}{req.name}",
        messages=[{
            "type": "workflow",
            "name": req.name,
            "description": req.description,
            "is_global": req.is_global,
            "project_id": req.project_id,
            "steps": [s.model_dump() for s in req.steps],
            "process_ids": [s.agent_type for s in req.steps if s.agent_type.startswith("pmbok:")],
        }],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"success": True, "workflow": _serialize(session)}


@router.get("", summary="列出可用工作流")
async def list_workflows(
    only_mine: bool = False,
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户可用的工作流：自己创建的 ∪ 全局模板 ∪（可选）指定项目绑定的。"""
    rows = (await db.execute(
        select(AgentSession)
        .where(AgentSession.title.like(f"{WF_PREFIX}%"))
        .order_by(desc(AgentSession.updated_at))
        .limit(200)
    )).scalars().all()

    items: List[Dict[str, Any]] = []
    for s in rows:
        wf = _serialize(s)
        if only_mine:
            if wf["owner_id"] == current_user.id:
                items.append(wf)
            continue
        if wf["owner_id"] == current_user.id:
            items.append(wf)
        elif wf.get("is_global"):
            items.append(wf)
        elif project_id and wf.get("project_id") == project_id:
            items.append(wf)
    return {"items": items, "total": len(items)}


@router.get("/{wf_id}", summary="获取单条工作流")
async def get_workflow(
    wf_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = await _load_workflow(wf_id, db)
    if not _can_edit(s, current_user) and not _serialize(s).get("is_global"):
        raise HTTPException(status_code=403, detail="无权访问该工作流")
    return {"workflow": _serialize(s)}


@router.put("/{wf_id}", summary="更新工作流")
async def update_workflow(
    wf_id: str,
    req: WorkflowUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = await _load_workflow(wf_id, db)
    if not _can_edit(s, current_user):
        raise HTTPException(status_code=403, detail="仅创建者或管理员可编辑")
    msg = s.messages[0] if isinstance(s.messages, list) and s.messages else {}
    if req.name is not None:
        msg["name"] = req.name
        s.title = f"{WF_PREFIX}{req.name}"
    if req.description is not None:
        msg["description"] = req.description
    if req.is_global is not None:
        msg["is_global"] = req.is_global
    if req.steps is not None:
        msg["steps"] = [st.model_dump() for st in req.steps]
        msg["process_ids"] = [st.agent_type for st in req.steps if st.agent_type.startswith("pmbok:")]
    s.messages = [msg]
    await db.commit()
    await db.refresh(s)
    return {"success": True, "workflow": _serialize(s)}


@router.delete("/{wf_id}", summary="删除工作流")
async def delete_workflow(
    wf_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = await _load_workflow(wf_id, db)
    if not _can_edit(s, current_user):
        raise HTTPException(status_code=403, detail="仅创建者或管理员可删除")
    await db.delete(s)
    await db.commit()
    return {"success": True}


@router.post("/{wf_id}/bind", summary="绑定工作流到项目")
async def bind_workflow(
    wf_id: str,
    req: WorkflowBindRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将工作流绑定到某项目（每项目一套独特工作流）。project_id=null 表示解绑。"""
    s = await _load_workflow(wf_id, db)
    if not _can_edit(s, current_user):
        raise HTTPException(status_code=403, detail="仅创建者或管理员可绑定")
    s.project_id = req.project_id
    if isinstance(s.messages, list) and s.messages:
        s.messages[0]["project_id"] = req.project_id
    await db.commit()
    await db.refresh(s)
    return {"success": True, "workflow": _serialize(s)}


@router.get("/project/{project_id}", summary="获取项目绑定的工作流")
async def get_project_workflow(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = (await db.execute(
        select(AgentSession)
        .where(AgentSession.title.like(f"{WF_PREFIX}%"), AgentSession.project_id == project_id)
        .order_by(desc(AgentSession.updated_at))
        .limit(1)
    )).scalars().first()
    if not s:
        return {"workflow": None}
    return {"workflow": _serialize(s)}


@router.post("/execute", summary="执行工作流 DAG（异步，立即返回 run_id）")
async def execute_workflow(
    req: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行工作流 DAG。可传 steps 或 workflow_id（加载已保存工作流）。

    立即返回 run_id；后台逐节点执行并增量更新状态，轮询 GET /workflows/runs/{run_id} 看实时进度。
    """
    steps = req.steps
    wf_name = ""
    if req.workflow_id:
        s = await _load_workflow(req.workflow_id, db)
        if not _can_edit(s, current_user) and not _serialize(s).get("is_global"):
            raise HTTPException(status_code=403, detail="无权执行该工作流")
        msg = s.messages[0] if isinstance(s.messages, list) and s.messages else {}
        steps = [WorkflowStep(**st) for st in msg.get("steps", [])]
        wf_name = msg.get("name", "")
    if not steps:
        raise HTTPException(status_code=400, detail="步骤列表不能为空")

    # 环路预检
    if _topological_sort(steps) is None:
        raise HTTPException(status_code=400, detail="工作流存在环路（cycle），无法执行")

    run_id = str(uuid.uuid4())
    _runs[run_id] = {
        "run_id": run_id,
        "workflow_id": req.workflow_id,
        "workflow_name": wf_name,
        "user_id": current_user.id,
        "project_id": req.project_id,
        "status": "running",
        "steps": [s.model_dump() for s in steps],
        "results": {s.label or s.agent_type: {"status": "pending"} for s in steps},
        "errors": {},
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }
    # 后台执行（自管 DB 会话）
    import asyncio
    asyncio.create_task(_execute_async(run_id, steps, req.project_id, current_user.id))

    return {
        "run_id": run_id,
        "status": "running",
        "steps": _runs[run_id]["steps"],
        "created_at": _runs[run_id]["created_at"],
    }


@router.get("/runs/{run_id}", summary="查询工作流执行状态（实时进度）")
async def get_run_status(run_id: str):
    run = _runs.get(run_id)
    if not run:
        run = _load_run_file(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return run


@router.get("/{wf_id}/runs", summary="列出某工作流的运行历史")
async def list_workflow_runs(
    wf_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """运行历史来自文件化持久化（data/workflow_runs/）；内存中尚未落盘的也一并返回。"""
    items: List[Dict[str, Any]] = []
    for run in _runs.values():
        if run.get("workflow_id") == wf_id:
            items.append(run)
    if _RUN_DIR.exists():
        for f in _RUN_DIR.glob("*.json"):
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if r.get("workflow_id") == wf_id and not any(i.get("run_id") == r.get("run_id") for i in items):
                items.append(r)
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/validate", summary="校验工作流（不执行）")
async def validate_workflow(
    req: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """校验工作流：环路检测 + 缺失必填输入告警（不阻塞，仅提示）。"""
    steps = req.steps
    if req.workflow_id:
        s = await _load_workflow(req.workflow_id, db)
        msg = s.messages[0] if isinstance(s.messages, list) and s.messages else {}
        steps = [WorkflowStep(**st) for st in msg.get("steps", [])]
    if not steps:
        raise HTTPException(status_code=400, detail="步骤列表不能为空")

    order = _topological_sort(steps)
    if order is None:
        return {"valid": False, "error": "存在环路（cycle），无法执行", "warnings": []}

    warnings: List[Dict[str, Any]] = []
    from app.services.ai.agent_registry import get_structured_itto
    for step in steps:
        label = step.label or step.agent_type
        # 已被上游覆盖的输入槽
        covered_by_upstream = set(step.input_mapping.keys())
        if step.depends_on:
            covered_by_upstream.add("__upstream__")
        sitto = get_structured_itto(step.agent_type)
        for it in sitto.get("inputs", []):
            if it.get("enabled") is False:
                continue
            key = it.get("key")
            optional = it.get("optional", False)
            if optional:
                continue
            if key in covered_by_upstream:
                continue
            if key in step.input_mapping:
                continue
            if step.user_input:
                continue
            if not step.depends_on:
                warnings.append({
                    "step": label, "agent_type": step.agent_type,
                    "input_key": key, "label": it.get("label", ""),
                    "message": "该必填输入既无上游依赖、也无内联输入/槽位映射，运行时可能为空",
                })
    return {"valid": True, "warnings": warnings}


@router.post("/templates", summary="保存工作流模板（兼容旧前端）")
async def save_template(
    req: TemplateSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = AgentSession(
        user_id=current_user.id,
        title=f"{WF_PREFIX}{req.name}",
        messages=[{
            "type": "workflow",
            "name": req.name,
            "description": req.description,
            "is_global": False,
            "project_id": None,
            "steps": req.steps,
            "process_ids": [st.get("agent_type") for st in req.steps if isinstance(st, dict) and str(st.get("agent_type", "")).startswith("pmbok:")],
        }],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {"success": True, "template_id": session.id, "name": req.name}


@router.get("/templates", summary="列出工作流模板（兼容旧前端）")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(AgentSession)
        .where(AgentSession.title.like(f"{WF_PREFIX}%"))
        .order_by(desc(AgentSession.updated_at))
        .limit(50)
    )).scalars().all()
    items = [_serialize(s) for s in rows]
    return {"items": items, "total": len(items)}
