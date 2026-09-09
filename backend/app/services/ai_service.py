import asyncio
import json
import re
import time
import logging
from typing import Dict, Any, List, Optional, AsyncIterator
from datetime import datetime, date, timedelta

from sqlalchemy import select
from app.db.session import async_session_maker
from app.core.ai_engine import ai_engine

logger = logging.getLogger(__name__)


# 知识库参考材料指令：所有 AI 生成内容在生成前会先检索知识库，命中后将此块前置到 prompt，
# 使生成结果优先遵循组织沉淀的规范 / 模板 / 经验（ requirement 3：AI 生成首先参照知识库 ）。
KB_REFERENCE_INSTRUCTION = """【知识库参考材料（系统已在生成前从知识库中检索得到）】
以下是组织沉淀的规范、模板与经验，请优先依据其内容生成，并保持与其一致；
当材料与用户需求冲突时，以用户需求为准，并在建议中说明差异。
------
{kb_context}
------"""

WBS_GENERATION_PROMPT = """你是一位资深项目管理专家，精通WBS（工作分解结构）方法论。
请根据以下项目信息，生成完整的WBS结构、里程碑、资源需求和风险识别。

项目名称：{project_name}
项目描述：{project_description}
行业类型：{industry_type}
约束条件：{constraints}

请严格按照以下JSON格式输出（不要包含任何markdown代码块标记，只输出纯JSON）：
{{
    "project_intent": {{
        "name": "项目名称",
        "goals": ["目标1", "目标2", "目标3"],
        "constraints": {{}},
        "industry": "行业类型"
    }},
    "wbs_structure": [
        {{
            "wbs_code": "1",
            "name": "阶段名称",
            "level": 1,
            "phase": "规划/设计/执行/交付",
            "duration_days": 14,
            "skills_required": ["技能1", "技能2"]
        }},
        {{
            "wbs_code": "1.1",
            "name": "子任务名称",
            "level": 2,
            "phase": "规划",
            "duration_days": 7,
            "skills_required": ["技能1"]
        }}
    ],
    "milestones": [
        {{
            "name": "里程碑名称",
            "due_date": 天数偏移量（整数，相对于今天）
        }}
    ],
    "resource_requirements": [
        {{
            "role": "角色名称",
            "count": 人数,
            "skills": ["技能1", "技能2"]
        }}
    ],
    "risk_identification": [
        {{
            "name": "风险名称",
            "probability": 0.5,
            "impact": 0.5,
            "response_strategy": "应对策略"
        }}
    ],
    "confidence_score": 0.92,
    "suggestions": ["建议1", "建议2", "建议3"]
}}

要求：
1. WBS结构至少包含3个层级，覆盖项目全生命周期
2. 里程碑设置合理，与WBS结构对应
3. 资源需求与任务技能要求匹配
4. 风险识别至少4条，概率和影响在0-1之间
5. 根据行业类型调整WBS内容的专业性
6. 只输出JSON，不要任何解释文字"""


PROJECT_ANALYSIS_PROMPT = """你是一位资深项目管理顾问，请对以下项目进行深度分析。

项目信息：
- 项目名称：{project_name}
- 项目ID：{project_id}
- 任务统计：总任务 {total_tasks}，已完成 {completed_tasks}，进行中 {in_progress_tasks}
- 平均进度：{avg_progress}%
- 风险统计：总风险 {total_risks}，活跃风险 {active_risks}，平均风险评分：{avg_risk_score}
- 基线开始：{baseline_start}
- 基线结束：{baseline_end}

请输出以下JSON格式的分析结果（只输出纯JSON，不要markdown）：
{{
    "overall_health": "healthy/warning/critical",
    "progress_summary": {{
        "completion_rate": 完成率数字,
        "avg_progress": 平均进度数字,
        "status": "进度状态描述"
    }},
    "risk_summary": {{
        "risk_level": "low/medium/high",
        "active_concerns": "活跃风险关注点描述"
    }},
    "schedule_analysis": {{
        "is_on_track": true/false,
        "schedule_status": "进度状态描述",
        "suggested_actions": ["建议1", "建议2"]
    }},
    "ai_insights": {{
        "key_findings": ["发现1", "发现2", "发现3"],
        "recommendations": ["建议1", "建议2", "建议3"],
        "confidence_score": 0.93
    }}
}}"""


RISK_PREDICTION_PROMPT = """你是一位项目风险管理专家，请基于以下项目数据预测未来14天的风险趋势。

项目信息：
- 项目名称：{project_name}
- 项目ID：{project_id}
- 当前活跃风险数：{active_risks}
- 平均风险评分：{avg_risk_score}
- 任务完成率：{completion_rate}%
- 平均进度：{avg_progress}%

请输出以下JSON格式的风险预测（只输出纯JSON，不要markdown）：
{{
    "risk_predictions": [
        {{
            "risk_id": "risk-001",
            "name": "风险名称",
            "category": "business/technical/resource/schedule",
            "current_probability": 0.3,
            "predicted_probability": 0.55,
            "trend": "increasing/decreasing/stable",
            "confidence": 0.88,
            "recommended_action": "应对建议"
        }}
    ],
    "overall_assessment": {{
        "risk_level": "low/medium/high",
        "project_health_score": 0.72,
        "predicted_outcome": "on_track/at_risk/critical",
        "confidence": 0.89
    }},
    "early_warnings": [
        {{
            "type": "warning/info",
            "title": "预警标题",
            "message": "预警详情",
            "suggested_action": "建议措施"
        }}
    ]
}}"""


CHAT_SYSTEM_PROMPT = """你是PMI中国AI项目管理社区的智能助手，专门帮助用户进行项目管理。
你可以：
1. 分析项目进度和风险
2. 提供任务分配建议
3. 生成项目报告摘要
4. 回答项目管理相关问题
5. 提供项目管理最佳实践建议
6. 帮助用户填写和优化各业务模块的表单字段

请用中文回答，保持专业、简洁、有帮助。

【项目感知模式（重要）】
当用户在对话中提供了 [项目全量数据] 段落时，你**必须先完整分析该数据，再基于真实数据给出答案**，并遵守以下规则：
1. 优先用项目的真实数据（任务进度、风险、里程碑、预算、EVM 等指标）来支撑你的结论，必要时用结构化分点/表格呈现；
2. 凡是涉及"任务、风险、进度、工时、预算、负责人"等判断，必须以 [项目全量数据] 中的内容为准；
3. 不得编造项目中不存在的任务、风险、里程碑或指标；若现有数据不足以回答，先说明"基于当前项目数据……"，再结合项目管理最佳实践给出建议；
4. 你被授权调用并解读该项目的全部数据，可主动指出数据中的异常（如进度滞后、风险评分偏高、关键路径任务延期等）。"""


class AIService:
    def __init__(self):
        self.engine = ai_engine
        self._provider_cache: Any = None
        self._provider_cache_ts: float = 0.0
        self._cache_ttl: float = 60.0

    def invalidate_cache(self) -> None:
        """系统大模型配置变更时调用，使缓存失效。"""
        self._provider_cache = None
        self._provider_cache_ts = 0.0

    async def _get_provider(self):
        """返回当前生效的 LLM Provider：优先系统默认配置，否则回退内置默认。"""
        now = time.time()
        if self._provider_cache is not None and (now - self._provider_cache_ts) < self._cache_ttl:
            return self._provider_cache

        provider = None
        try:
            async with async_session_maker() as db:
                from app.models.system_llm_config import SystemLLMConfig
                result = await db.execute(
                    select(SystemLLMConfig).where(SystemLLMConfig.is_active == True)  # noqa: E712
                )
                cfg = result.scalar_one_or_none()
                if cfg and cfg.api_key:
                    provider = ai_engine.create_provider_from_config(
                        provider_name=cfg.provider_name,
                        api_key=cfg.api_key,
                        base_url=cfg.base_url,
                        model_name=cfg.model_name,
                        temperature=cfg.temperature,
                        max_tokens=cfg.max_tokens,
                    )
                elif cfg and not cfg.api_key:
                    # 系统已启用默认大模型但未填写 Key：明确置空，避免静默回退到
                    # 环境变量 provider 而产生迷惑性空错误
                    logger.warning(
                        "系统默认大模型已启用但未填写 API Key (provider=%s)，请到 系统设置 > 大模型设置 填写",
                        cfg.provider_name,
                    )
                    provider = None
        except Exception:
            provider = None

        if provider is None:
            # 回退到 ai_engine 内置默认（依赖环境变量，如 OPENAI_API_KEY）
            try:
                provider = ai_engine.get_provider()
            except Exception:
                provider = None

        self._provider_cache = provider
        self._provider_cache_ts = now
        return provider

    async def _retrieve_kb_context(self, kb_id: Optional[str], query: str) -> str:
        """检索单个知识库（单 scope）的 RAG 上下文文本；失败或为空时返回 ''。"""
        if not kb_id:
            return ""
        try:
            from app.services.rag_engine import get_rag_engine
            async with async_session_maker() as db:
                engine = get_rag_engine(db)
                ctx = await engine.get_context(query=query, kb_ids=[kb_id], top_k=5, max_tokens=2000)
            return ctx or ""
        except Exception as e:
            logger.warning("KB 上下文检索失败 (kb_id=%s): %s", kb_id, e, exc_info=False)
            return ""

    def _extract_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        return json.loads(text)

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        try:
            return self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _extract_error_detail(self, e: Exception) -> str:
        """把 provider 抛出的异常转成可读描述，尽量暴露供应商返回的真实原因（如 MiniMax 的 authorized_error (1004)）。"""
        resp = getattr(e, "response", None)
        if resp is not None and hasattr(resp, "status_code"):
            status = getattr(resp, "status_code", None)
            raw = (getattr(resp, "text", None) or "").strip()
            parsed_msg = None
            if raw:
                try:
                    j = json.loads(raw)
                    if isinstance(j.get("error"), dict):
                        parsed_msg = j["error"].get("message") or j["error"].get("type")
                    elif j.get("message"):
                        parsed_msg = j.get("message")
                except Exception:
                    parsed_msg = None
            if status in (401, 403):
                hint = "（鉴权失败：多半是 API Key 无效、被 IP 白名单拦截，或 Key 与当前网络出口不匹配——请到 系统设置 > 大模型设置 更换/补全 Key，或把本机出口 IP 加入供应商白名单）"
            elif status == 429:
                hint = "（触发限流，请稍后重试）"
            elif status is not None and 500 <= int(status) < 600:
                hint = "（供应商服务端异常，请稍后重试）"
            else:
                hint = ""
            detail = f"HTTP {status}" if status is not None else f"{type(e).__name__}"
            if parsed_msg:
                detail += f"：{parsed_msg}"
            elif raw:
                detail += f"：{raw[:200]}"
            if hint:
                detail += hint
            return detail
        return str(e) or f"({type(e).__name__})"

    def _convert_milestone_dates(self, milestones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        today = datetime.now().date()
        result = []
        for m in milestones:
            due_date = m.get("due_date")
            if isinstance(due_date, int):
                due_date = (today + timedelta(days=due_date)).isoformat()
            elif isinstance(due_date, str):
                try:
                    int(due_date)
                    due_date = (today + timedelta(days=int(due_date))).isoformat()
                except ValueError:
                    pass
            result.append({
                "name": m.get("name", ""),
                "due_date": due_date,
            })
        return result

    def _fallback_wbs(self, project_name: str, project_description: str, industry_type: str, constraints: Dict[str, Any]) -> Dict[str, Any]:
        """规则模式 WBS：在 LLM 不可用时生成一套通用的标准项目分解结构。"""
        phases = [
            ("1", "项目启动", "明确项目目标、范围与干系人", [
                ("1.1", "编制项目章程", 3),
                ("1.2", "识别关键干系人", 2),
                ("1.3", "召开项目启动会", 1),
            ]),
            ("2", "规划设计", "制定项目计划与技术方案", [
                ("2.1", "需求调研与分析", 5),
                ("2.2", "制定项目计划(WBS/进度/预算)", 4),
                ("2.3", "方案设计与评审", 5),
            ]),
            ("3", "执行实施", "按计划推进交付物开发", [
                ("3.1", "核心功能开发/实施", 15),
                ("3.2", "阶段性交付与验收", 5),
                ("3.3", "质量检查与测试", 6),
            ]),
            ("4", "监控收尾", "跟踪进度并完成项目收尾", [
                ("4.1", "进度与风险监控", 4),
                ("4.2", "变更与问题管理", 3),
                ("4.3", "项目验收与结项", 3),
            ]),
        ]
        wbs_structure: List[Dict[str, Any]] = []
        for code, name, desc, subs in phases:
            wbs_structure.append({
                "wbs_code": code, "name": name, "description": desc,
                "duration_days": sum(s[2] for s in subs),
            })
            for scode, sname, days in subs:
                wbs_structure.append({
                    "wbs_code": scode, "name": sname, "description": "",
                    "duration_days": days,
                })

        return {
            "project_intent": {
                "name": project_name,
                "goals": [f"完成{project_name}项目的既定目标"],
                "constraints": constraints,
                "industry": industry_type,
            },
            "wbs_structure": wbs_structure,
            "milestones": [
                {"name": "项目启动完成", "due_date": 7},
                {"name": "规划设计完成", "due_date": 21},
                {"name": "执行实施完成", "due_date": 60},
                {"name": "项目验收结项", "due_date": 70},
            ],
            "resource_requirements": [
                {"role": "项目经理", "count": 1},
                {"role": "核心成员", "count": 3},
            ],
            "risk_identification": [
                {"name": "需求变更风险", "level": "中"},
                {"name": "进度延误风险", "level": "中"},
            ],
            "confidence_score": 0.6,
            "suggestions": ["当前为规则模式生成的通用 WBS，配置系统大模型后可获得更贴合业务的智能分解结果。"],
        }

    async def generate_wbs(self, project_name: str, project_description: str, industry_type: str, constraints: Dict[str, Any], kb_id: Optional[str] = None) -> Dict[str, Any]:
        prompt = WBS_GENERATION_PROMPT.format(
            project_name=project_name,
            project_description=project_description,
            industry_type=industry_type,
            constraints=json.dumps(constraints, ensure_ascii=False),
        )

        # 知识库增强：AI 生成首先参照知识库沉淀（requirement 3）
        kb_context = await self._retrieve_kb_context(kb_id, f"{project_name} {project_description} {industry_type}")
        if kb_context:
            prompt = KB_REFERENCE_INSTRUCTION.format(kb_context=kb_context) + "\n\n" + prompt

        try:
            provider = await self._get_provider()
            if provider is None:
                raise RuntimeError("AI 大模型未配置：请在系统设置中配置系统默认大模型")
            try:
                # 大模型推理可能很慢（MiniMax 等可达 60~120s），加 wait_for 护栏：
                # 超时即降级为规则模式，避免请求挂死到 httpx 的 120s 上限
                response = await asyncio.wait_for(
                    provider.generate(prompt, temperature=0.3, max_tokens=4000),
                    timeout=90,
                )
            except asyncio.TimeoutError:
                logger.warning("WBS 生成超时（>90s），降级为规则模式")
                response = None
            data = self._safe_json_loads(response) if response else {}
        except Exception:
            data = {}

        if not data or "wbs_structure" not in data:
            # LLM 不可用或返回无效时，降级为规则模式，保证功能可用（不抛错）
            data = self._fallback_wbs(project_name, project_description, industry_type, constraints)

        data["milestones"] = self._convert_milestone_dates(data.get("milestones", []))

        return {
            "project_intent": data.get("project_intent", {
                "name": project_name,
                "goals": [f"完成{project_name}项目"],
                "constraints": constraints,
                "industry": industry_type,
            }),
            "wbs_structure": data.get("wbs_structure", []),
            "milestones": data.get("milestones", []),
            "resource_requirements": data.get("resource_requirements", []),
            "risk_identification": data.get("risk_identification", []),
            "confidence_score": data.get("confidence_score", 0.85),
            "suggestions": data.get("suggestions", []),
        }

    @staticmethod
    def _classify_error(e: Exception) -> "tuple[bool, str]":
        """异常分级：返回 (retryable, error_type)。

        - 可重试（瞬时故障）：网络超时 / 连接 / 传输错误 / 服务端 5xx / 限流 429；
        - 不可重试：鉴权 / 参数 / 配置 / 类型错误（重试无意义，需人工修复）。
        调用方据 retryable 决定是否重试。
        """
        retryable_exceptions = (asyncio.TimeoutError,)
        try:
            import httpx
            retryable_exceptions = retryable_exceptions + (
                httpx.TimeoutException,
                httpx.TransportError,
            )
        except ImportError:
            pass
        if isinstance(e, retryable_exceptions):
            return True, "network_or_timeout"

        # HTTP 状态码错误：5xx / 429 可重试，其余 4xx 不可重试
        try:
            import httpx
            if isinstance(e, httpx.HTTPStatusError):
                resp = getattr(e, "response", None)
                status = resp.status_code if resp is not None else None
                if status is not None and (500 <= status < 600 or status == 429):
                    return True, "server_or_rate_limit"
                return False, "http_client_error"
        except ImportError:
            pass

        etype = type(e).__name__.lower()
        non_retryable_keywords = (
            "auth", "unauthor", "forbidden", "permission",
            "value", "valid", "param", "config", "key", "credential", "argument",
        )
        if isinstance(e, (ValueError, TypeError)) or any(k in etype for k in non_retryable_keywords):
            return False, "auth_or_param"

        # 其余未知错误保守按可重试处理
        return True, "transient"

    async def _gather_project_context(self, project_id: str) -> Optional[str]:
        """聚合选中项目的全量数据，返回结构化文本块；项目不存在/无权限返回 None。

        对应需求：AI 项目经理在选中项目并提问时，应先分析该项目的所有数据再作答。
        本方法即"调用并解读项目数据"的落地——在 API 层已通过 ensure_project_access 鉴权后调用。
        """
        try:
            async with async_session_maker() as db:
                from app.models import (  # noqa: F401
                    Project, Task, Risk, Milestone, User, EVMSnapshot,
                )
                from sqlalchemy import func, select
                from sqlalchemy.orm import selectinload

                proj = (
                    await db.execute(
                        select(Project).where(
                            Project.id == project_id, Project.is_deleted == False  # noqa: E712
                        )
                    )
                ).scalar_one_or_none()
                if not proj:
                    return None

                # 项目基本信息
                owner = None
                if proj.owner_id:
                    owner = (
                        await db.execute(select(User).where(User.id == proj.owner_id))
                    ).scalar_one_or_none()
                proj_lines = [
                    f"- 项目名称：{proj.name}",
                    f"- 项目ID：{proj.id}",
                    f"- 描述：{proj.description or '（无）'}",
                    f"- 状态：{proj.status}",
                    f"- 行业/类型：{proj.industry_type} / {proj.project_type}",
                    f"- 优先级：{proj.priority}（1最高）",
                    f"- 负责人：{owner.username if owner else '未指定'}",
                    f"- 计划周期：{proj.start_date} ~ {proj.end_date}",
                    f"- 基线周期：{proj.baseline_start} ~ {proj.baseline_end}",
                    f"- 预算：{proj.budget}（基线 {proj.baseline_budget}）/ 实际成本：{proj.actual_cost}",
                ]

                # 任务（含负责人，按层级/排序）
                task_rows = (
                    await db.execute(
                        select(Task)
                        .where(Task.project_id == project_id, Task.is_deleted == False)  # noqa: E712
                        .options(selectinload(Task.assignee))
                        .order_by(Task.sort_order, Task.wbs_code)
                    )
                ).scalars().all()

                total = len(task_rows)
                done = sum(1 for t in task_rows if t.status == "done")
                in_prog = sum(1 for t in task_rows if t.status in ("in_progress", "in_review", "testing"))
                avg_progress = round(sum(float(t.progress or 0) for t in task_rows) / total, 1) if total else 0.0

                task_lines = []
                for t in task_rows:
                    ps = t.planned_start.strftime("%Y-%m-%d") if t.planned_start else "-"
                    pe = t.planned_end.strftime("%Y-%m-%d") if t.planned_end else "-"
                    assignee = t.assignee.username if t.assignee else "未分配"
                    wbs = t.wbs_code or "-"
                    task_lines.append(
                        f"  · [{wbs}] {t.name} | 状态:{t.status} | 进度:{float(t.progress or 0):.0f}% "
                        f"| 优先级:{t.priority} | 负责人:{assignee} | 计划:{ps}~{pe}"
                    )
                # 任务过多时仅展示未完成任务明细 + 已完成数量，控制 token
                if total > 120:
                    open_tasks = [l for l in task_lines if "状态:done" not in l]
                    task_block = "\n".join(open_tasks[:200])
                    task_block += f"\n  （另有 {done} 个已完成任务未逐一列出）"
                else:
                    task_block = "\n".join(task_lines) if task_lines else "  （无任务）"

                # 风险
                risk_rows = (
                    await db.execute(select(Risk).where(Risk.project_id == project_id))
                ).scalars().all()
                risk_lines = []
                for r in risk_rows:
                    risk_lines.append(
                        f"  · {r.name} | 类别:{r.category} | 概率:{float(r.probability or 0):.2f} "
                        f"影响:{float(r.impact or 0):.2f} | 风险分:{r.risk_score} | 状态:{r.status} "
                        f"| 应对策略:{r.response_strategy or '-'}"
                    )
                risk_block = "\n".join(risk_lines) if risk_lines else "  （无风险登记）"

                # 里程碑
                mile_rows = (
                    await db.execute(
                        select(Milestone)
                        .where(Milestone.project_id == project_id)
                        .order_by(Milestone.due_date)
                    )
                ).scalars().all()
                mile_lines = []
                for m in mile_rows:
                    dd = m.due_date.strftime("%Y-%m-%d") if m.due_date else "-"
                    mile_lines.append(f"  · {m.name} | 到期:{dd} | 状态:{m.status}")
                mile_block = "\n".join(mile_lines) if mile_lines else "  （无里程碑）"

                # 最新 EVM 快照
                evm_rows = (
                    await db.execute(
                        select(EVMSnapshot)
                        .where(EVMSnapshot.project_id == project_id)
                        .order_by(EVMSnapshot.snapshot_date.desc())
                        .limit(1)
                    )
                ).scalars().all()
                evm_block = "  （暂无 EVM 快照）"
                if evm_rows:
                    e = evm_rows[0]
                    evm_block = (
                        f"  · 快照日期:{e.snapshot_date} | PV:{e.planned_value} EV:{e.earned_value} "
                        f"AC:{e.actual_cost} | CPI:{e.cost_performance_index} SPI:{e.schedule_performance_index} "
                        f"| EAC:{e.estimate_at_completion}"
                    )

                header = (
                    "【项目全量数据（AI 已获权调用并分析，请先分析再作答）】\n"
                    f"项目概览：\n" + "\n".join(proj_lines) + "\n"
                    f"任务统计：共 {total} 个，已完成 {done}，进行中 {in_prog}，平均进度 {avg_progress}%\n"
                    f"任务明细：\n{task_block}\n"
                    f"风险登记：\n{risk_block}\n"
                    f"里程碑：\n{mile_block}\n"
                    f"最新 EVM：\n{evm_block}"
                )
                return header
        except Exception as exc:  # 聚合失败不应阻断对话，降级为仅传 ID
            logger.warning("聚合项目上下文失败 (project_id=%s): %s", project_id, exc)
            return None

    async def chat(self, message: str, project_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None, kb_id: Optional[str] = None) -> Dict[str, Any]:
        messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

        # 动态上下文放入 user 角色并加明确边界，避免项目数据中的指令注入劫持 system 提示
        user_parts = []
        if project_id:
            # 先聚合项目全量数据：选中项目并提问时，AI 应基于真实数据分析作答
            proj_ctx = await self._gather_project_context(project_id)
            if proj_ctx:
                user_parts.append(proj_ctx)
            else:
                user_parts.append(f"[项目ID] {project_id}（未能加载项目明细）")
        if context:
            user_parts.append(f"[项目上下文]\n{json.dumps(context, ensure_ascii=False)}")
        # 个人知识问答：若指定了知识库（私密库限本人），将其作为参考材料注入
        if kb_id:
            kb_ctx = await self._retrieve_kb_context(kb_id, message)
            if kb_ctx:
                user_parts.append("【知识库参考】\n" + kb_ctx)
        user_parts.append(f"[用户问题]\n{message}")
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        try:
            provider = await self._get_provider()
            if provider is None:
                return {
                    "message": "AI 大模型未配置：请在系统设置 > 大模型设置 中配置系统默认大模型（默认已内置 MiniMax M2.7）。",
                    "suggested_actions": [],
                    "related_tasks": [],
                    "confidence": 0.0,
                }
            response = await provider.chat(messages, temperature=0.7, max_tokens=2000)
        except Exception as e:
            retryable, error_type = self._classify_error(e)
            # 不吞异常：记录完整异常链，并暴露 retryable/error_type 供上层决策（重试或上报）
            logger.warning(
                "AI chat 调用失败 (retryable=%s, error_type=%s): %s",
                retryable, error_type, e, exc_info=True,
            )
            detail = self._extract_error_detail(e)
            return {
                "message": f"AI服务暂时不可用：{detail}。请稍后重试或联系管理员。",
                "suggested_actions": [],
                "related_tasks": [],
                "confidence": 0.0,
                "retryable": retryable,
                "error_type": error_type,
            }

        return {
            "message": response,
            "suggested_actions": [],
            "related_tasks": [],
            "confidence": 0.9,
        }

    async def stream_chat(self, message: str, project_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None, kb_id: Optional[str] = None) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

        # 动态上下文放入 user 角色并加明确边界，避免项目数据中的指令注入劫持 system 提示
        user_parts = []
        if project_id:
            # 先聚合项目全量数据：选中项目并提问时，AI 应基于真实数据分析作答
            proj_ctx = await self._gather_project_context(project_id)
            if proj_ctx:
                user_parts.append(proj_ctx)
            else:
                user_parts.append(f"[项目ID] {project_id}（未能加载项目明细）")
        if context:
            user_parts.append(f"[项目上下文]\n{json.dumps(context, ensure_ascii=False)}")
        if kb_id:
            kb_ctx = await self._retrieve_kb_context(kb_id, message)
            if kb_ctx:
                user_parts.append("【知识库参考】\n" + kb_ctx)
        user_parts.append(f"[用户问题]\n{message}")
        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        try:
            provider = await self._get_provider()
            if provider is None:
                yield "AI 大模型未配置：请在系统设置 > 大模型设置 中配置系统默认大模型。"
                return
            async for chunk in provider.stream_chat(messages, temperature=0.7, max_tokens=2000):
                yield chunk
        except Exception as e:
            retryable, error_type = self._classify_error(e)
            # 不吞异常：记录完整异常链（流式无法直接回传结构化字段，仅在日志中分级）
            logger.warning(
                "AI stream_chat 调用失败 (retryable=%s, error_type=%s): %s",
                retryable, error_type, e, exc_info=True,
            )
            detail = self._extract_error_detail(e)
            yield f"AI服务暂时不可用：{detail}。请稍后重试或联系管理员。"

    async def analyze_project(self, project_data: Dict[str, Any], kb_id: Optional[str] = None) -> Dict[str, Any]:
        prompt = PROJECT_ANALYSIS_PROMPT.format(
            project_name=project_data.get("name", ""),
            project_id=project_data.get("id", ""),
            total_tasks=project_data.get("total_tasks", 0),
            completed_tasks=project_data.get("completed_tasks", 0),
            in_progress_tasks=project_data.get("in_progress_tasks", 0),
            avg_progress=project_data.get("avg_progress", 0),
            total_risks=project_data.get("total_risks", 0),
            active_risks=project_data.get("active_risks", 0),
            avg_risk_score=project_data.get("avg_risk_score", 0),
            baseline_start=project_data.get("baseline_start", "未设置"),
            baseline_end=project_data.get("baseline_end", "未设置"),
        )

        # 知识库增强
        kb_context = await self._retrieve_kb_context(kb_id, f"项目分析 {project_data.get('name', '')}")
        if kb_context:
            prompt = KB_REFERENCE_INSTRUCTION.format(kb_context=kb_context) + "\n\n" + prompt

        try:
            provider = await self._get_provider()
            if provider is None:
                raise RuntimeError("AI 大模型未配置")
            response = await provider.generate(prompt, temperature=0.3, max_tokens=2000)
            data = self._safe_json_loads(response)
        except Exception:
            data = {}

        completion_rate = round(
            project_data.get("completed_tasks", 0) / max(project_data.get("total_tasks", 1), 1) * 100, 2
        )
        avg_progress = round(project_data.get("avg_progress", 0), 2)
        avg_risk_score = round(project_data.get("avg_risk_score", 0), 4)

        return {
            "project_id": project_data.get("id", ""),
            "project_name": project_data.get("name", ""),
            "analysis_time": datetime.now().isoformat(),
            "overall_health": data.get("overall_health", "healthy" if avg_progress > 50 else "warning"),
            "progress_summary": data.get("progress_summary", {
                "total_tasks": project_data.get("total_tasks", 0),
                "completed_tasks": project_data.get("completed_tasks", 0),
                "in_progress_tasks": project_data.get("in_progress_tasks", 0),
                "completion_rate": completion_rate,
                "avg_progress": avg_progress,
                "status": "进度良好" if avg_progress > 50 else "需要关注",
            }),
            "risk_summary": data.get("risk_summary", {
                "total_risks": project_data.get("total_risks", 0),
                "active_risks": project_data.get("active_risks", 0),
                "avg_risk_score": avg_risk_score,
                "risk_level": "low" if avg_risk_score < 0.3 else "medium" if avg_risk_score < 0.6 else "high",
            }),
            "schedule_analysis": data.get("schedule_analysis", {
                "baseline_start": project_data.get("baseline_start"),
                "baseline_end": project_data.get("baseline_end"),
                "current_start": project_data.get("start_date"),
                "current_end": project_data.get("end_date"),
                "is_on_track": True,
                "suggested_actions": [],
            }),
            "ai_insights": data.get("ai_insights", {
                "key_findings": [
                    f"项目整体进度：{completion_rate}%",
                    f"当前有 {project_data.get('active_risks', 0)} 个活跃风险需要关注",
                ],
                "recommendations": [
                    "定期进行风险评审会议",
                    "关注关键路径上的任务进度",
                ],
                "confidence_score": 0.85,
            }),
        }

    async def predict_risks(self, project_data: Dict[str, Any], kb_id: Optional[str] = None) -> Dict[str, Any]:
        prompt = RISK_PREDICTION_PROMPT.format(
            project_name=project_data.get("name", ""),
            project_id=project_data.get("id", ""),
            active_risks=project_data.get("active_risks", 0),
            avg_risk_score=project_data.get("avg_risk_score", 0),
            completion_rate=round(
                project_data.get("completed_tasks", 0) / max(project_data.get("total_tasks", 1), 1) * 100, 2
            ),
            avg_progress=round(project_data.get("avg_progress", 0), 2),
        )

        # 知识库增强
        kb_context = await self._retrieve_kb_context(kb_id, f"风险预测 {project_data.get('name', '')}")
        if kb_context:
            prompt = KB_REFERENCE_INSTRUCTION.format(kb_context=kb_context) + "\n\n" + prompt

        try:
            provider = await self._get_provider()
            if provider is None:
                raise RuntimeError("AI 大模型未配置")
            response = await provider.generate(prompt, temperature=0.3, max_tokens=3000)
            data = self._safe_json_loads(response)
        except Exception:
            data = {}

        return {
            "project_id": project_data.get("id", ""),
            "project_name": project_data.get("name", ""),
            "prediction_time": datetime.now().isoformat(),
            "prediction_horizon_days": 14,
            "risk_predictions": data.get("risk_predictions", []),
            "overall_assessment": data.get("overall_assessment", {
                "risk_level": "medium",
                "project_health_score": 0.72,
                "predicted_outcome": "on_track",
                "confidence": 0.85,
            }),
            "early_warnings": data.get("early_warnings", []),
        }

    ASSIST_FILL_PROMPT = """你是项目管理系统的"表单智能填写助手"。请根据表单类型与用户已填字段，自动补全缺失字段并对已有字段做专业优化。
表单类型：{form_type}
已填字段（JSON）：{fields}
补充上下文：{context}
请只输出如下 JSON，不要任何解释：
{{
  "suggestions": {{ "字段名": "建议值或优化后的值" }},
  "improve_tips": ["优化建议1", "优化建议2"]
}}
要求：
1. 补全所有缺失且有业务意义的字段（如名称、描述、负责人角色、优先级建议等）；
2. 对已有字段在保持原意基础上进行专业润色，不要歪曲原意；
3. 字段名使用与输入一致的英文/中文名；
4. 若无可补全项，suggestions 返回空对象。"""

    async def assist_fill(
        self,
        form_type: str,
        fields: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """AI 辅助填写：根据已有字段补全缺失项并优化。"""
        prompt = self.ASSIST_FILL_PROMPT.format(
            form_type=form_type,
            fields=json.dumps(fields, ensure_ascii=False),
            context=json.dumps(context or {}, ensure_ascii=False),
        )
        try:
            provider = await self._get_provider()
            if provider is None:
                return {
                    "suggestions": {},
                    "improve_tips": ["AI 大模型未配置：请在系统设置 > 大模型设置 中配置系统默认大模型"],
                    "form_type": form_type,
                    "error": "no_llm",
                }
            text = await provider.generate(prompt, temperature=0.4, max_tokens=2000)
            data = self._safe_json_loads(text)
        except Exception:
            data = {}
        return {
            "suggestions": data.get("suggestions", {}),
            "improve_tips": data.get("improve_tips", []),
            "form_type": form_type,
        }


ai_service = AIService()
