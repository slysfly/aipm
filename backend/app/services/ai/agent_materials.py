"""
PMI中国AI项目管理社区 - Agent 物料工作区（结构化 ITTO 运行时管线）

设计：
- 每个 Agent 的 ITTO 升级为「可配置项」（输入为必选物料 / 工具技术可勾选 / 输出为指定文件）。
- 运行前：检查系统已有内容（项目知识库文档 + 本工作区历史物料），标记每个输入物料是否存在。
- 缺失时：用户手工上传基础信息 → AI 生成统一格式模板文件材料 → 落库到工作区。
- 运行时：聚合输入物料 + 勾选的工具技术，由 AI 在环境中完成信息处理，输出指定文件。

物料以文件形式存放在 backend/data/agent_materials/{project_id}/ 下，配套 index.json。
零数据库迁移、可回滚，与 agent_overrides.json 同一持久化思路。

[AI Orchestration | Material-Driven Agent Pipeline | ITTO as Configurable Items]
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.models import KnowledgeBase, KnowledgeDocument
from app.services.ai.out_of_box_agents import _llm
from app.services.ai.agent_registry import get_structured_itto

logger = logging.getLogger(__name__)

_MATERIAL_ROOT = Path(__file__).resolve().parents[3] / "data" / "agent_materials"


# --------------------------------------------------------------------------- #
# 存储工具
# --------------------------------------------------------------------------- #
def _project_dir(project_id: str) -> Path:
    d = _MATERIAL_ROOT / (project_id or "_global")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(project_id: str) -> Path:
    return _project_dir(project_id) / "index.json"


def _load_index(project_id: str) -> Dict[str, Any]:
    p = _index_path(project_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            logger.warning("read agent_materials index failed: %s", p)
    return {"inputs": {}, "outputs": []}


def _save_index(project_id: str, idx: Dict[str, Any]) -> None:
    p = _index_path(project_id)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def store_material(
    project_id: str, title: str, content: str, kind: str, source: str,
    agent_id: str, input_key: Optional[str] = None, mime: str = "text/markdown",
) -> Dict[str, Any]:
    """保存一份物料（模板/输出）到工作区，并在 index 中登记。返回记录。"""
    pid = project_id or "_global"
    d = _project_dir(pid)
    mid = uuid.uuid4().hex[:12]
    fname = f"{mid}.md"
    (d / fname).write_text(content, encoding="utf-8")
    idx = _load_index(pid)
    rec = {
        "ref": mid, "title": title, "kind": kind, "source": source,
        "agent_id": agent_id, "file": fname, "mime": mime,
        "generated_at": datetime.now().isoformat(),
    }
    if input_key:
        idx.setdefault("inputs", {})[input_key] = rec
    else:
        idx.setdefault("outputs", []).append(rec)
    _save_index(pid, idx)
    return rec


def get_material_content(project_id: str, ref: str) -> Optional[Dict[str, Any]]:
    d = _project_dir(project_id or "_global")
    f = d / f"{ref}.md"
    if not f.exists():
        return None
    return {"ref": ref, "content": f.read_text(encoding="utf-8"), "file": str(f)}


# --------------------------------------------------------------------------- #
# 阶段一：运行前物料检查
# --------------------------------------------------------------------------- #
async def prepare(
    project_id: Optional[str], agent_id: str, db: Any,
) -> Dict[str, Any]:
    """检查系统已有内容，返回每个输入物料的存在状态与缺失清单。

    检查来源：
    ① 本工作区历史物料（index.json 中按 input_key 登记）；
    ② 项目知识库文档（KnowledgeDocument）标题关键字匹配。
    """
    sitto = get_structured_itto(agent_id)
    inputs = sitto.get("inputs", [])

    # 已登记的历史物料
    idx = _load_index(project_id or "_global") if project_id else {"inputs": {}}
    stored = idx.get("inputs", {})

    # 项目知识库文档标题集合
    kb_titles: List[str] = []
    if project_id:
        try:
            kb_rows = (await db.execute(
                select(KnowledgeBase.id).where(KnowledgeBase.project_id == project_id)
            )).scalars().all()
            if kb_rows:
                doc_rows = (await db.execute(
                    select(KnowledgeDocument.title)
                    .where(KnowledgeDocument.kb_id.in_(kb_rows))
                )).scalars().all()
                kb_titles = [t for t in doc_rows if t]
        except Exception:  # noqa: BLE001
            logger.warning("prepare: KB 文档查询失败（已忽略）: %s", project_id)

    def _match_kb(label: str) -> Optional[str]:
        for t in kb_titles:
            if not t:
                continue
            # 标签中的任意 2+ 字片段命中文档标题即认为存在
            for token in re.findall(r"[一-龥]{2,}|[A-Za-z]{3,}", label):
                if token.lower() in (t or "").lower():
                    return t
        return None

    items: List[Dict[str, Any]] = []
    missing: List[str] = []
    for it in inputs:
        # 过滤未启用的输入项（enabled=False 表示本次运行不参与）
        if it.get("enabled") is False:
            continue
        key = it.get("key")
        label = it.get("label", "")
        rec = stored.get(key)
        exists = bool(rec)
        ref = rec.get("ref") if rec else None
        title = rec.get("title") if rec else None
        source = rec.get("source") if rec else None
        if not exists:
            kb_match = _match_kb(label)
            if kb_match:
                exists = True
                title = kb_match
                source = "project_kb"
        # 仅「启用 且 必需」的缺失输入才进入缺失清单
        if not exists and not it.get("optional"):
            missing.append(key)
        items.append({
            "key": key, "label": label, "optional": it.get("optional", False),
            "enabled": it.get("enabled", True),
            "kind": it.get("kind", "file"), "exists": exists,
            "ref": ref, "title": title, "source": source,
        })

    # 仅返回启用的工具/输出项，与 run-material 过滤口径一致
    tools = [t for t in sitto.get("tools", []) if t.get("enabled") is not False]
    outputs = [o for o in sitto.get("outputs", []) if o.get("enabled") is not False]

    return {
        "agent_id": agent_id,
        "project_id": project_id,
        "has_project": bool(project_id),
        "inputs": items,
        "missing_required": missing,
        "tools": tools,
        "outputs": outputs,
    }


# --------------------------------------------------------------------------- #
# 阶段二：手工上传基础信息 → AI 生成统一格式模板
# --------------------------------------------------------------------------- #
async def generate_template(
    project_id: Optional[str], agent_id: str, input_key: str,
    input_label: str, basic_info: str = "", file_content: str = "",
    file_name: str = "",
) -> Dict[str, Any]:
    """用户手工上传基础信息（文本/文件内容），由 AI 生成统一格式模板文件材料。"""
    raw = basic_info or file_content or ""
    prompt = (
        "你是项目管理文档模板专家。请基于用户提供的基础信息，生成一份符合 PMBOK 标准、"
        f"结构统一、可直接填写的「{input_label}」模板文档（使用 Markdown 格式）。\n"
        "要求：\n"
        "1. 开头注明文档目的与适用范围；\n"
        "2. 按章节/字段列出统一结构（含填写说明与示例占位符）；\n"
        "3. 风格专业、严谨、可执行；\n"
        "4. 不要输出多余解释，直接给出模板正文。\n"
        f"【基础信息】{raw or '（用户未提供，请生成通用空白模板）'}\n"
        f"【原始文件名】{file_name or '（无）'}"
    )
    text = await _llm(prompt, temperature=0.4, max_tokens=2400, timeout=90, retries=2)
    if not text:
        # 降级：基于标签生成极简模板
        text = (
            f"# {input_label}（模板）\n\n"
            f"> 由 AI 生成的统一格式模板。\n\n"
            f"## 一、文档目的\n（请填写）\n\n"
            f"## 二、适用范围\n（请填写）\n\n"
            f"## 三、主要内容\n（请填写，参考基础信息：{raw[:200]}）\n\n"
            f"## 四、签署与日期\n负责人：________  日期：________\n"
        )
    title = f"{input_label}·模板"
    rec = store_material(
        project_id or "_global", title, text, kind="file",
        source="template", agent_id=agent_id, input_key=input_key,
    )
    rec["download_url"] = f"/api/v1/agents/materials/{rec['ref']}/download"
    return rec


# --------------------------------------------------------------------------- #
# 阶段三：聚合输入物料 + 工具技术 → AI 处理 → 输出指定文件
# --------------------------------------------------------------------------- #
def _read_input(ref: str, project_id: str) -> str:
    m = get_material_content(project_id or "_global", ref)
    return m["content"] if m else ""


async def run_material(
    project_id: Optional[str], agent_id: str, db: Any,
    input_refs: Dict[str, str], selected_tools: List[str], user_input: str = "",
) -> Dict[str, Any]:
    """执行 Agent 物料管线：读取输入物料 + 勾选工具技术，AI 处理，输出指定文件。

    - 领域 Agent：复用 registry_run_agent 得到结果，序列化后作为输出文件。
    - PMBOK 过程：构建提示聚合输入物料与工具技术，调用 LLM 生成输出，每个 Output 一个文件。
    """
    sitto = get_structured_itto(agent_id)
    pid = project_id or "_global"

    # 聚合输入物料内容（仅启用项）
    input_blocks: List[str] = []
    for it in sitto.get("inputs", []):
        if it.get("enabled") is False:
            continue
        key = it.get("key")
        ref = input_refs.get(key)
        content = _read_input(ref, pid) if ref else ""
        input_blocks.append(f"### 输入物料：{it.get('label', key)}\n{content or '（系统/用户提供）'}")
    inputs_text = "\n\n".join(input_blocks)

    # 工具技术：仅启用项，且未显式勾选时默认全选、已勾选时取交集
    sel = selected_tools or []
    tool_items = [
        t for t in sitto.get("tools", [])
        if t.get("enabled") is not False and (not sel or t.get("key") in sel)
    ]
    tool_labels = [t.get("label") for t in tool_items]
    tool_text = "、".join(tool_labels) if tool_labels else "（默认全部适用工具技术）"

    # 输出规格：仅启用项
    outputs = [o for o in sitto.get("outputs", []) if o.get("enabled") is not False]
    output_labels = [o.get("label", o.get("key")) for o in outputs] or ["执行结果"]

    # 领域 Agent：直接复用既有执行逻辑
    if agent_id in ("report", "evm", "risk", "meeting_minutes", "wbs", "resource",
                    "quality", "compliance", "health_check", "decision") or agent_id in ("weekly_report",):
        try:
            from app.services.ai.agent_registry import run_agent as registry_run_agent
            result = await registry_run_agent(
                agent_type=agent_id, db=db, user_id="system",
                project_id=project_id, input_text=user_input or inputs_text,
                options={},
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("run_material: 领域 Agent 执行失败 %s", agent_id)
            result = {"error": str(e)}
        import json as _json
        out_content = (
            f"# {output_labels[0] if output_labels else '执行结果'}\n\n"
            f"> Agent：{agent_id}　生成时间：{datetime.now().isoformat()}\n\n"
            f"```json\n{_json.dumps(result, ensure_ascii=False, indent=2)[:6000]}\n```"
        )
        rec = store_material(
            pid, title=f"{agent_id} 执行结果", content=out_content,
            kind="file", source="output", agent_id=agent_id,
        )
        rec["download_url"] = f"/api/v1/agents/materials/{rec['ref']}/download"
        rec["content"] = out_content
        return {
            "agent_id": agent_id, "outputs": [rec],
            "inputs_used": list(input_refs.keys()), "tools_used": tool_labels,
            "applied_tools": [{"key": t.get("key"), "label": t.get("label")} for t in tool_items],
        }

    # PMBOK 过程：构建提示
    proc_name = agent_id
    proc_summary = ""
    if agent_id.startswith("pmbok:"):
        from app.services.ai.pmbok_agents import PMBOK_REGISTRY
        proc = PMBOK_REGISTRY.get(agent_id.split(":", 1)[1])
        if proc:
            proc_name = f"{proc.name_cn}（{proc.name_en}）"
            proc_summary = proc.summary or ""
    prompt = (
        f"你是项目管理与 AI 治理专家，正在应用《{proc_name}》。\n"
        f"释义：{proc_summary}\n"
        f"请使用的工具与技术：{tool_text}。\n\n"
        f"【输入物料】\n{inputs_text}\n\n"
        f"【用户补充】{user_input or '（无）'}\n\n"
        f"【预期输出（请逐项生成，每项用二级标题 ## 分隔）】\n"
        + "\n".join(f"- {l}" for l in output_labels)
        + "\n\n请直接输出 Markdown，按上述输出项分节，专业、可执行、落到本项目。"
    )
    text = await _llm(prompt, temperature=0.3, max_tokens=3200, timeout=120, retries=2)
    if not text:
        text = f"# {proc_name} 执行结果\n\n（AI 服务暂不可用，已生成占位结果。）\n\n{inputs_text[:1000]}"

    # 按输出项拆分（以 ## 标题匹配）
    out_recs: List[Dict[str, Any]] = []
    sections = re.split(r"\n##\s+", text)
    # sections[0] 是开头（可能含 # 标题），其余每个对应一个 ## 章节
    for idx_o, olabel in enumerate(output_labels):
        body = ""
        if idx_o == 0 and len(sections) > 1:
            body = sections[1]
        elif idx_o + 1 < len(sections):
            body = sections[idx_o + 1]
        else:
            body = text
        content = f"# {olabel}\n\n{body.strip()}\n"
        rec = store_material(
            pid, title=f"{proc_name}·{olabel}", content=content,
            kind="file", source="output", agent_id=agent_id,
        )
        rec["download_url"] = f"/api/v1/agents/materials/{rec['ref']}/download"
        rec["content"] = content
        out_recs.append(rec)

    return {
        "agent_id": agent_id, "outputs": out_recs,
        "inputs_used": list(input_refs.keys()), "tools_used": tool_labels,
        "applied_tools": [{"key": t.get("key"), "label": t.get("label")} for t in tool_items],
    }


# --------------------------------------------------------------------------- #
# 物料列表 / 下载
# --------------------------------------------------------------------------- #
def list_materials(project_id: Optional[str]) -> Dict[str, Any]:
    idx = _load_index(project_id or "_global")
    inputs = list((idx.get("inputs") or {}).values())
    outputs = idx.get("outputs", [])
    for r in inputs + outputs:
        r["download_url"] = f"/api/v1/agents/materials/{r['ref']}/download"
    return {"project_id": project_id, "inputs": inputs, "outputs": outputs,
            "total": len(inputs) + len(outputs)}
