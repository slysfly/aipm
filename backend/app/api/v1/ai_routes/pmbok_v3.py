# -*- coding: utf-8 -*-
"""
PMBOK / CPMAI / TAI 三层映射 V3 数据服务路由
================================================

## 数据来源
本路由数据来源于通维 AIPM 项目的「PMBOK/CPMAI 三层映射」成果，原始 JSON 位于：
    projects/pmi-mapping/data/
已复制至本地后端数据目录（启动时直接读文件，无需数据库）：
    backend/data/pmbok_v3/
        - skills.json      (248 条) Skill 能力单元
        - agents.json      ( 61 条) Agent 过程单元
        - workflows.json   ( 10 条) 工作流编排
        - principles.json  (  7 条) 原则
        - relations.json          三件套之间的关联关系

## 字段含义
### skills.json（Skill 能力）
    id, name_cn, name_en        标识与中英文名称
    category                    类别（如「专家判断」「数据分析」「CPMAI·AI技术」等）
    source_system               来源体系：PMBOK / CPMAI / TAI
    source_layers               来源层级
    reuse_count                 复用次数
    automation_mode             自动化模式
    automation_note             自动化说明
    definition                  定义
    prompt_template             提示词模板
    quality_criteria            质量准则
    aliases                     别名
    bound_to{agents,principles,workflows}  绑定的 agent / 原则 / 工作流 id 列表
    used_by_agent_count         被多少 agent 使用
    layer                       层级
    # 本路由在加载时额外聚合（便于前端按过程组/知识领域筛选）：
    agent_process_groups        绑定 agents 的过程组集合（如 ["启动","规划"]）
    agent_knowledge_areas       绑定 agents 的知识领域集合

### agents.json（Agent 过程）
    id, code, name_cn, name_en, layer
    system / system_label       所属体系（PMBOK / CPMAI / TAI / PMBOKv8）
    process_group / process_group_en   过程组（启动/规划/执行/监控/收尾 等）
    knowledge_area / knowledge_area_en 知识领域（整合/范围/进度...）
    v8_domain, summary, v8_note
    itto{inputs,tools,outputs}  输入/工具/输出
    itto_size{I,T,O}            ITTO 数量
    skill_ids / skill_count     绑定的 skill
    principle_ids               绑定的原则
    persona, system_prompt, difficulty

### workflows.json（工作流）
    id, code, name_cn, name_en, layer, system, system_label, summary, v8_note
    itto, nodes[{seq,type,ref,ref_id,name,note,is_pending}], node_count, node_stats
    principle_ids, is_meta, difficulty
    # 本路由在 /workflows/{id} 中为每个 node 额外带出 ref_name（ref 实体 name_cn）

### principles.json（原则）
    id, code, name_cn, name_en, layer, system, system_label, is_meta
    statement, v8_note, injection_target, rubric, enabling_skills, usage_rule

### relations.json（关系）
    agent_skills[{agent_id,skill_id,role}]
    workflow_nodes[{workflow_id,node_seq,node_type,ref_id,ref_name,is_pending}]
    agent_principles[{agent_id,principle_id}]
    workflow_principles[...], agent_links[{from_agent_id,to_agent_id,relation}]
    counts{...}

## 说明
- 本路由为**纯只读**数据服务，全部从 JSON 在 import 时加载进内存（dict 索引），不改动任何现有接口。
- 路由前缀 /pmbok，配合 main.py 的 /api/v1 前缀，最终路径为 /api/v1/pmbok/...
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

# backend/data/pmbok_v3 —— 本文件位于 backend/app/api/v1/ai_routes/，故取 parents[4]
_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "pmbok_v3"


def _load(name: str) -> Any:
    with open(_DATA_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


_SKILLS: List[Dict[str, Any]] = _load("skills")
_AGENTS: List[Dict[str, Any]] = _load("agents")
_WORKFLOWS: List[Dict[str, Any]] = _load("workflows")
_PRINCIPLES: List[Dict[str, Any]] = _load("principles")
_RELATIONS: Dict[str, Any] = _load("relations")

# 主键索引
_AGENT_BY_ID: Dict[str, Dict[str, Any]] = {a["id"]: a for a in _AGENTS}
_SKILL_BY_ID: Dict[str, Dict[str, Any]] = {s["id"]: s for s in _SKILLS}
_PRINCIPLE_BY_ID: Dict[str, Dict[str, Any]] = {p["id"]: p for p in _PRINCIPLES}
_WORKFLOW_BY_ID: Dict[str, Dict[str, Any]] = {w["id"]: w for w in _WORKFLOWS}


# 预计算：每个 Skill 聚合其绑定 agents 的过程组 / 知识领域，便于前端按过程组/知识领域筛选
for _s in _SKILLS:
    _pgs: set = set()
    _kas: set = set()
    for _aid in (_s.get("bound_to", {}) or {}).get("agents", []) or []:
        _ag = _AGENT_BY_ID.get(_aid)
        if _ag:
            if _ag.get("process_group"):
                _pgs.add(_ag["process_group"])
            if _ag.get("knowledge_area"):
                _kas.add(_ag["knowledge_area"])
    _s["agent_process_groups"] = sorted(_pgs)
    _s["agent_knowledge_areas"] = sorted(_kas)


router = APIRouter(prefix="/pmbok", tags=["pmbok-v3"])


# ---------------------------------------------------------------- Skills
@router.get("/skills")
def list_skills(
    process_group: Optional[str] = Query(None, description="过程组中文，如 启动/规划"),
    knowledge_area: Optional[str] = Query(None, description="知识领域中文，如 整合/范围"),
    category: Optional[str] = Query(None, description="Skill 类别"),
    source_system: Optional[str] = Query(None, description="来源体系 PMBOK/CPMAI/TAI"),
    search: Optional[str] = Query(None, description="模糊匹配 name_cn"),
):
    """Skill 能力列表（支持按关联 Agent 的过程组/知识领域过滤）。"""
    items = _SKILLS
    if process_group:
        items = [s for s in items if process_group in s["agent_process_groups"]]
    if knowledge_area:
        items = [s for s in items if knowledge_area in s["agent_knowledge_areas"]]
    if category:
        items = [s for s in items if s.get("category") == category]
    if source_system:
        items = [s for s in items if s.get("source_system") == source_system]
    if search:
        kw = search.lower()
        items = [s for s in items if kw in (s.get("name_cn") or "").lower()]
    return {"items": items, "total": len(items)}


@router.get("/skills/{skill_id}")
def get_skill(skill_id: str):
    """单个 Skill（Skill 无 ITTO，以 itto=null 占位，返回定义/模板/质量准则/bound_to）。"""
    s = _SKILL_BY_ID.get(skill_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    out = dict(s)
    out["itto"] = None
    return out


# ---------------------------------------------------------------- Agents
@router.get("/agents")
def list_agents(
    process_group: Optional[str] = Query(None, description="过程组中文"),
    knowledge_area: Optional[str] = Query(None, description="知识领域中文"),
    system: Optional[str] = Query(None, description="体系 PMBOK/CPMAI/TAI/PMBOKv8"),
    search: Optional[str] = Query(None, description="模糊匹配 name_cn/name_en"),
):
    """Agent 过程列表。"""
    items = _AGENTS
    if process_group:
        items = [a for a in items if a.get("process_group") == process_group]
    if knowledge_area:
        items = [a for a in items if a.get("knowledge_area") == knowledge_area]
    if system:
        items = [a for a in items if a.get("system") == system]
    if search:
        kw = search.lower()
        items = [
            a
            for a in items
            if kw in (a.get("name_cn") or "").lower()
            or kw in (a.get("name_en") or "").lower()
        ]
    return {"items": items, "total": len(items)}


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    """单个 Agent（含完整 itto、skill_ids、principle_ids、persona、system_prompt）。"""
    a = _AGENT_BY_ID.get(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"agent not found: {agent_id}")
    return a


# ---------------------------------------------------------------- Workflows
@router.get("/workflows")
def list_workflows():
    """工作流 summary 列表（10 条）。"""
    items = [
        {
            "id": w.get("id"),
            "code": w.get("code"),
            "layer": w.get("layer"),
            "system": w.get("system"),
            "system_label": w.get("system_label"),
            "name_cn": w.get("name_cn"),
            "name_en": w.get("name_en"),
            "summary": w.get("summary"),
            "difficulty": w.get("difficulty"),
            "node_count": w.get("node_count"),
        }
        for w in _WORKFLOWS
    ]
    return {"items": items, "total": len(items)}


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    """单个工作流（含完整节点链，每个 node 带出 ref 实体的 name_cn 作为 ref_name）。"""
    w = _WORKFLOW_BY_ID.get(workflow_id)
    if not w:
        raise HTTPException(status_code=404, detail=f"workflow not found: {workflow_id}")
    out = dict(w)
    nodes: List[Dict[str, Any]] = []
    for n in out.get("nodes", []) or []:
        nn = dict(n)
        ref = nn.get("ref")
        if nn.get("type") == "agent":
            nn["ref_name"] = _AGENT_BY_ID.get(ref, {}).get("name_cn")
        elif nn.get("type") == "skill":
            nn["ref_name"] = _SKILL_BY_ID.get(ref, {}).get("name_cn")
        else:
            nn["ref_name"] = None
        nodes.append(nn)
    out["nodes"] = nodes
    return out


# ---------------------------------------------------------------- Principles
@router.get("/principles")
def list_principles():
    """原则列表（7 条）。"""
    return {"items": _PRINCIPLES, "total": len(_PRINCIPLES)}


# ---------------------------------------------------------------- Stats
@router.get("/stats")
def stats():
    """三件套汇总数字与结构覆盖度。"""
    # 各过程组下的 agent 数
    pg_counter: Dict[str, int] = {}
    # 各知识领域下的 agent 集合
    ka_agents: Dict[str, set] = {}
    for a in _AGENTS:
        pg = a.get("process_group")
        if pg:
            pg_counter[pg] = pg_counter.get(pg, 0) + 1
        ka = a.get("knowledge_area")
        if ka:
            ka_agents.setdefault(ka, set()).add(a["id"])

    knowledge_areas = []
    for ka, aids in ka_agents.items():
        # 统计该知识领域下被绑定 agent 引用的 skill 数（去重）
        skill_ids_in_ka: set = set()
        for s in _SKILLS:
            if set((s.get("bound_to", {}) or {}).get("agents", []) or []) & aids:
                skill_ids_in_ka.add(s["id"])
        knowledge_areas.append(
            {"name": ka, "agents": len(aids), "skills": len(skill_ids_in_ka)}
        )
    knowledge_areas.sort(key=lambda x: (-x["agents"], x["name"]))

    # 各体系下 agent / skill 计数
    by_system: Dict[str, Dict[str, int]] = {}
    for a in _AGENTS:
        sys = a.get("system")
        if not sys:
            continue
        by_system.setdefault(sys, {"agents": 0, "skills": 0})["agents"] += 1
    for s in _SKILLS:
        sys = s.get("source_system")
        if not sys:
            continue
        by_system.setdefault(sys, {"agents": 0, "skills": 0})["skills"] += 1

    return {
        "skills_total": len(_SKILLS),
        "agents_total": len(_AGENTS),
        "workflows_total": len(_WORKFLOWS),
        "principles_total": len(_PRINCIPLES),
        "process_groups": pg_counter,
        "knowledge_areas": knowledge_areas,
        "by_system": by_system,
    }


# ---------------------------------------------------------------- Slots (ITTO structured slots)
@router.get("/slots/{agent_id}")
def get_agent_slots(agent_id: str):
    """Return Agent structured ITTO slots (inputs/tools/outputs) with required/optional flags.
    agent_id accepts two formats: AG-PMBOK-4.1 or pmbok:4.1 shorthand.
    """
    normalized = agent_id
    if ":" in agent_id and not agent_id.startswith("AG-"):
        suffix = agent_id.split(":")[-1]
        candidates = [a for a in _AGENTS if a.get("code") == suffix]
        if candidates:
            normalized = candidates[0]["id"]
        else:
            normalized = "AG-PMBOK-" + suffix

    agent = _AGENT_BY_ID.get(normalized)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found: " + agent_id)

    itto = agent.get("itto") or {}
    inputs = itto.get("inputs") or []
    tools = itto.get("tools") or []
    outputs = itto.get("outputs") or []

    def _to_slot_list(items, kind):
        out = []
        for idx, item in enumerate(items):
            name = item if isinstance(item, str) else item.get("name", item.get("label", ""))
            key = kind + "_" + str(idx)
            optional = kind != "input" and idx > 0
            out.append({
                "key": key,
                "label": name,
                "optional": optional,
                "enabled": True,
                "kind": kind,
            })
        return out

    return {
        "agent_id": normalized,
        "agent_name": agent.get("name_cn"),
        "inputs": _to_slot_list(inputs, "input"),
        "tools": _to_slot_list(tools, "tool"),
        "outputs": _to_slot_list(outputs, "output"),
    }
