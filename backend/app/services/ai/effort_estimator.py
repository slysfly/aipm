"""
PMI中国AI项目管理社区 - AI工时估算服务
基于历史数据 + LLM 智能估算任务工时

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: Machine Learning — AI工作量估算]"""

import json
import re
import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.ai_engine import ai_engine
from app.models import Task, Project
import logging

logger = logging.getLogger(__name__)


class EffortEstimator:
    """工时估算器：基于历史数据和LLM智能估算"""

    # 任务类型关键词映射
    TASK_TYPE_KEYWORDS = {
        "frontend": ["前端", "frontend", "ui", "界面", "页面", "css", "html", "react", "vue", "组件"],
        "backend": ["后端", "backend", "api", "接口", "服务器", "server", "数据库", "db", "服务"],
        "database": ["数据库", "表结构", "迁移", "sql", "schema", "存储过程"],
        "mobile": ["移动端", "mobile", "app", "ios", "android", "小程序", "flutter", "rn"],
        "devops": ["devops", "运维", "部署", "ci/cd", "docker", "k8s", "kubernetes", "jenkins", "流水线"],
        "testing": ["测试", "testing", "qa", "自动化测试", "单元测试", "集成测试", "压测"],
        "design": ["设计", "design", "ui设计", "ux", "原型", "figma", "sketch", "视觉"],
        "docs": ["文档", "docs", "documentation", "readme", "wiki", "手册"],
        "security": ["安全", "security", "认证", "授权", "加密", "jwt", "oauth", "漏洞"],
        "performance": ["性能", "performance", "优化", "缓存", "redis", "cdn", "压测", "调优"],
        "ai": ["ai", "人工智能", "机器学习", "ml", "模型", "算法", "gpt", "llm", "训练"],
    }

    def __init__(self):
        pass

    async def estimate_task(
        self,
        task_name: str,
        description: str,
        project_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        估算单个任务工时

        Args:
            task_name: 任务名称
            description: 任务描述
            project_id: 项目ID（用于查询历史数据）
            db: 数据库会话

        Returns:
            dict: 估算结果，包含estimated_hours, confidence, range_min, range_max, basis
        """
        if not task_name or not task_name.strip():
            raise ValueError("任务名称不能为空")

        # 1. 获取历史数据
        historical_data = []
        if db and project_id:
            historical_data = await self.get_historical_data(db, project_id, task_name, description)

        # 2. 基于历史数据计算基准估算
        historical_estimate = self._calculate_historical_estimate(historical_data)

        # 3. 使用LLM进行智能估算
        llm_estimate = await self._llm_estimate_task(task_name, description, historical_estimate, historical_data)

        # 4. 融合两种估算结果
        final_estimate = self._merge_estimates(historical_estimate, llm_estimate, historical_data)

        return final_estimate

    async def estimate_project(
        self,
        project_id: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        估算整个项目工时

        Args:
            project_id: 项目ID
            db: 数据库会话

        Returns:
            dict: 项目估算结果，包含total_hours, buffer_hours, estimated_duration_days, confidence
        """
        # 查询项目所有任务
        result = await db.execute(
            select(Task).where(
                Task.project_id == project_id,
                Task.is_deleted == False
            )
        )
        tasks = result.scalars().all()

        if not tasks:
            return {
                "total_hours": 0,
                "buffer_hours": 0,
                "estimated_duration_days": 0,
                "confidence": 0,
                "task_count": 0,
                "basis": "项目暂无任务",
            }

        # 汇总估算工时
        total_estimated = sum(float(t.estimated_hours or 0) for t in tasks)
        total_actual = sum(float(t.actual_hours or 0) for t in tasks if t.actual_hours)

        # 查询历史完成率（用于调整估算）
        completed_tasks = [t for t in tasks if t.status == "done" and t.actual_hours]
        if completed_tasks:
            # 计算估算准确率
            accuracy_ratios = []
            for t in completed_tasks:
                est = float(t.estimated_hours or 1)
                act = float(t.actual_hours or est)
                accuracy_ratios.append(act / est)

            avg_ratio = statistics.mean(accuracy_ratios)
            # 根据历史准确率调整剩余任务估算
            remaining_tasks = [t for t in tasks if t.status != "done"]
            adjusted_remaining = sum(float(t.estimated_hours or 0) * avg_ratio for t in remaining_tasks)
            adjusted_total = total_actual + adjusted_remaining
        else:
            adjusted_total = total_estimated
            avg_ratio = 1.0

        # 风险分析：计算缓冲时间
        # 基于任务数量、复杂度和历史偏差
        task_count = len(tasks)
        complexity_factor = self._assess_project_complexity(tasks)

        # 缓冲时间 = 基于历史偏差的调整 + 复杂度缓冲
        if completed_tasks and len(completed_tasks) >= 3:
            # 使用历史偏差的标准差计算缓冲
            std_ratio = statistics.stdev(accuracy_ratios) if len(accuracy_ratios) > 1 else 0.2
            buffer_ratio = std_ratio * complexity_factor
        else:
            # 没有足够历史数据，使用经验值
            buffer_ratio = 0.2 * complexity_factor

        buffer_hours = adjusted_total * buffer_ratio

        # 估算项目周期（假设每天8小时，考虑并行）
        # 简单估算：总工时 / (团队规模 * 8) * 并行系数
        # 这里使用简化模型
        estimated_duration_days = int((adjusted_total + buffer_hours) / 8 * 1.2)

        # 置信度计算
        confidence = self._calculate_project_confidence(
            task_count=task_count,
            completed_count=len(completed_tasks),
            historical_data_count=len(completed_tasks),
            avg_accuracy_ratio=avg_ratio,
        )

        # 构建依据说明
        basis_parts = []
        if completed_tasks:
            basis_parts.append(f"基于{len(completed_tasks)}个已完成任务的历史数据")
            basis_parts.append(f"历史估算准确率: {(1/avg_ratio*100):.0f}%" if avg_ratio > 0 else "")
        else:
            basis_parts.append("暂无历史完成数据，基于经验估算")

        basis_parts.append(f"项目复杂度评估: {complexity_factor:.1f}/5.0")
        basis_parts.append(f"缓冲时间比例: {buffer_ratio*100:.0f}%")

        return {
            "total_hours": round(adjusted_total, 1),
            "buffer_hours": round(buffer_hours, 1),
            "estimated_duration_days": max(1, estimated_duration_days),
            "confidence": round(confidence, 2),
            "task_count": task_count,
            "completed_task_count": len(completed_tasks),
            "historical_accuracy_ratio": round(avg_ratio, 2),
            "complexity_factor": round(complexity_factor, 1),
            "basis": "；".join(filter(None, basis_parts)),
        }

    async def get_historical_data(
        self,
        db: AsyncSession,
        project_id: Optional[str] = None,
        task_name: str = "",
        description: str = "",
    ) -> List[Dict[str, Any]]:
        """
        获取历史工时数据

        Args:
            db: 数据库会话
            project_id: 项目ID
            task_name: 当前任务名称（用于相似度匹配）
            description: 当前任务描述

        Returns:
            list[dict]: 历史数据列表
        """
        try:
            # 构建查询：查找同项目或同类型的已完成任务
            conditions = [
                Task.status == "done",
                Task.actual_hours > 0,
                Task.is_deleted == False,
            ]

            if project_id:
                conditions.append(Task.project_id == project_id)

            query = select(Task).where(and_(*conditions))
            result = await db.execute(query)
            tasks = result.scalars().all()

            # 计算相似度并排序
            current_text = f"{task_name} {description}".lower()
            historical = []

            for t in tasks:
                task_text = f"{t.name} {t.description or ''}".lower()
                similarity = self._calculate_text_similarity(current_text, task_text)

                historical.append({
                    "id": t.id,
                    "name": t.name,
                    "description": t.description or "",
                    "estimated_hours": float(t.estimated_hours or 0),
                    "actual_hours": float(t.actual_hours or 0),
                    "category": t.category or "",
                    "similarity": round(similarity, 3),
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                })

            # 按相似度排序，取前10条
            historical.sort(key=lambda x: x["similarity"], reverse=True)
            return historical[:10]

        except Exception:
            return []

    async def _llm_estimate_task(
        self,
        task_name: str,
        description: str,
        historical_estimate: Dict[str, Any],
        historical_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """使用LLM估算任务工时"""

        system_prompt = """你是一个资深的软件开发项目经理，擅长精确估算开发工时。

请根据任务描述，结合历史数据，给出精确的工时估算。

输出格式（JSON）：
{
  "estimated_hours": 预估工时（小时，数字）,
  "confidence": 置信度（0-1，基于信息完整度）,
  "range_min": 最乐观工时,
  "range_max": 最悲观工时,
  "basis": "估算依据的简要说明（50字以内）",
  "risk_factors": ["风险因素1", "风险因素2"],
  "complexity_score": 复杂度评分（1-10）
}

估算原则：
1. 考虑设计、开发、自测、Code Review全流程
2. 考虑技术难点和学习成本
3. 考虑联调和Bug修复时间
4. 不要低估，预留合理缓冲
5. 简单任务：2-4小时，中等任务：8-16小时，复杂任务：24-40小时
6. 如果有历史数据，参考历史实际工时进行调整"""

        # 构建历史数据上下文
        history_context = ""
        if historical_data:
            history_context = "\n\n历史参考数据（相似任务）：\n"
            for h in historical_data[:5]:
                history_context += f"- {h['name']}: 预估{h['estimated_hours']}h, 实际{h['actual_hours']}h\n"

        user_prompt = f"""请估算以下任务的工时：

任务名称：{task_name}
任务描述：{description or '暂无详细描述'}

历史估算参考：{historical_estimate.get('estimated_hours', '无')}小时
{history_context}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await ai_engine.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
            )

            # 提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "estimated_hours": float(result.get("estimated_hours", 0)),
                    "confidence": float(result.get("confidence", 0.7)),
                    "range_min": float(result.get("range_min", 0)),
                    "range_max": float(result.get("range_max", 0)),
                    "basis": result.get("basis", "AI智能估算"),
                    "risk_factors": result.get("risk_factors", []),
                    "complexity_score": float(result.get("complexity_score", 5)),
                }
        except Exception as e:
            logger.warning("解析 AI 工时估算结果失败，降级为规则估算: %s", e, exc_info=True)

        # 降级估算
        return self._fallback_estimate(task_name, description)

    def _calculate_historical_estimate(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """基于历史数据计算基准估算"""
        if not historical_data:
            return {"estimated_hours": 0, "confidence": 0, "basis": "无历史数据"}

        # 按相似度加权计算平均实际工时
        weighted_hours = 0
        total_weight = 0

        for h in historical_data:
            weight = h.get("similarity", 0.5)
            actual = h.get("actual_hours", 0)
            if actual > 0:
                weighted_hours += actual * weight
                total_weight += weight

        if total_weight > 0:
            avg_hours = weighted_hours / total_weight
            # 置信度基于历史数据数量和质量
            confidence = min(0.9, 0.3 + len(historical_data) * 0.1 + total_weight * 0.2)
            return {
                "estimated_hours": round(avg_hours, 1),
                "confidence": round(confidence, 2),
                "basis": f"基于{len(historical_data)}条历史数据的加权平均",
            }

        return {"estimated_hours": 0, "confidence": 0, "basis": "历史数据无效"}

    def _merge_estimates(
        self,
        historical: Dict[str, Any],
        llm: Dict[str, Any],
        historical_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """融合历史数据估算和LLM估算"""
        hist_hours = historical.get("estimated_hours", 0)
        hist_conf = historical.get("confidence", 0)
        llm_hours = llm.get("estimated_hours", 0)
        llm_conf = llm.get("confidence", 0.7)

        # 如果有可靠的历史数据，加权融合
        if hist_hours > 0 and hist_conf > 0.3:
            # 历史数据权重 = confidence, LLM权重 = 1 - confidence
            total_weight = hist_conf + llm_conf
            if total_weight > 0:
                final_hours = (hist_hours * hist_conf + llm_hours * llm_conf) / total_weight
            else:
                final_hours = (hist_hours + llm_hours) / 2
            final_confidence = min(0.95, max(hist_conf, llm_conf) + 0.1)
            basis = f"历史数据({hist_hours}h) + AI估算({llm_hours}h)加权融合"
        else:
            # 无历史数据，使用LLM估算
            final_hours = llm_hours
            final_confidence = llm_conf * 0.8  # 无历史数据时降低置信度
            basis = llm.get("basis", "AI智能估算")

        # 计算范围
        complexity = llm.get("complexity_score", 5)
        range_factor = 0.2 + (complexity / 10) * 0.3  # 复杂度越高，范围越大
        range_min = round(final_hours * (1 - range_factor), 1)
        range_max = round(final_hours * (1 + range_factor), 1)

        return {
            "estimated_hours": round(final_hours, 1),
            "confidence": round(final_confidence, 2),
            "range_min": max(0.5, range_min),
            "range_max": round(range_max, 1),
            "basis": basis,
            "risk_factors": llm.get("risk_factors", []),
            "complexity_score": complexity,
            "historical_data": historical_data[:5],  # 返回前5条历史数据用于展示
        }

    def _fallback_estimate(self, task_name: str, description: str) -> Dict[str, Any]:
        """降级估算策略"""
        text = f"{task_name} {description}".lower()

        # 基于关键词的粗略估算
        if any(k in text for k in ["重构", "架构", "框架", "迁移", "升级"]):
            hours = 24
            complexity = 8
        elif any(k in text for k in ["集成", "oauth", "支付", "第三方", "sdk"]):
            hours = 16
            complexity = 7
        elif any(k in text for k in ["优化", "性能", "缓存", "查询优化"]):
            hours = 12
            complexity = 6
        elif any(k in text for k in ["页面", "ui", "组件", "样式", "布局"]):
            hours = 8
            complexity = 4
        elif any(k in text for k in ["api", "接口", "crud", "增删改查"]):
            hours = 8
            complexity = 4
        elif any(k in text for k in ["测试", "用例", "自动化"]):
            hours = 6
            complexity = 3
        elif any(k in text for k in ["文档", "readme", "wiki"]):
            hours = 4
            complexity = 2
        else:
            hours = 8
            complexity = 5

        return {
            "estimated_hours": hours,
            "confidence": 0.5,
            "range_min": round(hours * 0.7, 1),
            "range_max": round(hours * 1.5, 1),
            "basis": "基于任务关键词的粗略估算",
            "risk_factors": ["信息不完整，建议细化需求"],
            "complexity_score": complexity,
        }

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度（简单Jaccard相似度）"""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def _assess_project_complexity(self, tasks: List[Task]) -> float:
        """评估项目复杂度（1-5分）"""
        score = 1.0

        # 基于任务数量
        task_count = len(tasks)
        if task_count > 50:
            score += 1.5
        elif task_count > 20:
            score += 1.0
        elif task_count > 10:
            score += 0.5

        # 基于任务类型多样性
        categories = set(t.category for t in tasks if t.category)
        score += min(1.5, len(categories) * 0.3)

        # 基于平均预估工时
        avg_hours = sum(float(t.estimated_hours or 0) for t in tasks) / max(1, task_count)
        if avg_hours > 20:
            score += 0.5
        elif avg_hours > 10:
            score += 0.3

        return min(5.0, score)

    def _calculate_project_confidence(
        self,
        task_count: int,
        completed_count: int,
        historical_data_count: int,
        avg_accuracy_ratio: float,
    ) -> float:
        """计算项目估算置信度"""
        confidence = 0.3  # 基础置信度

        # 任务数量加分
        if task_count >= 10:
            confidence += 0.1
        if task_count >= 20:
            confidence += 0.1

        # 历史完成数据加分
        if completed_count >= 3:
            confidence += 0.15
        if completed_count >= 10:
            confidence += 0.15

        # 历史准确率加分
        if 0.8 <= avg_accuracy_ratio <= 1.2:
            confidence += 0.2  # 估算很准
        elif 0.6 <= avg_accuracy_ratio <= 1.5:
            confidence += 0.1  # 估算还行

        return min(0.95, confidence)


# 全局实例
effort_estimator = EffortEstimator()
