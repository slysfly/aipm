"""
AI模型评估与A/B测试框架
支持多Provider对比评估、A/B实验和基于任务类型的自动选型
"""

import time
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from statistics import mean, stdev

from app.core.ai_engine import ai_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """单个测试用例"""
    prompt: str
    expected_keywords: List[str] = field(default_factory=list)
    max_latency_ms: int = 10000


@dataclass
class EvaluationReport:
    """单个Provider的评估报告"""
    provider: str
    latency_ms: float
    response_length: int
    keyword_match_rate: float
    estimated_cost: float
    raw_response: str


@dataclass
class ABTestResult:
    """A/B测试结果"""
    control: EvaluationReport
    treatment: EvaluationReport
    winner: str  # "control" | "treatment" | "tie"
    improvement_pct: float


# ---------------------------------------------------------------------------
# 成本估算系数（元/千token，仅供参考）
# ---------------------------------------------------------------------------
COST_PER_1K_TOKENS: Dict[str, float] = {
    "openai": 0.03,
    "deepseek": 0.001,
    "anthropic": 0.015,
    "baidu": 0.008,
    "aliyun": 0.012,
    "tencent": 0.010,
    "zhipu": 0.008,
    "moonshot": 0.012,
    "qwen": 0.008,
    "siliconflow": 0.005,
    "minimax": 0.010,
}

# 各任务类型推荐的Provider优先级（按得分排列）
TASK_TYPE_PROVIDER_RANKING: Dict[str, List[str]] = {
    "wbs": ["minimax", "deepseek", "openai", "qwen"],
    "risk": ["openai", "anthropic", "minimax", "deepseek"],
    "chat": ["deepseek", "minimax", "qwen", "openai"],
    "report": ["openai", "anthropic", "minimax", "siliconflow"],
}


class ModelEvaluator:
    """AI模型评估与A/B测试框架"""

    def __init__(self):
        self.engine = ai_engine

    # ------------------------------------------------------------------ #
    #  单次评估
    # ------------------------------------------------------------------ #

    async def evaluate_response(
        self,
        prompt: str,
        providers: List[str],
        metrics: List[str] = None,
    ) -> Dict[str, EvaluationReport]:
        """对比多个Provider的响应质量

        Args:
            prompt: 输入提示词
            providers: 要测试的Provider名称列表
            metrics: 评估指标列表（默认全部: latency, quality, cost）

        Returns:
            每个Provider对应的评估报告字典
        """
        if metrics is None:
            metrics = ["latency", "quality", "cost"]

        reports: Dict[str, EvaluationReport] = {}

        for provider_name in providers:
            try:
                start = time.monotonic()
                response = await self.engine.generate(
                    prompt,
                    provider=provider_name,
                    temperature=0.3,
                    max_tokens=1024,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

                # 响应长度（字符数，作为简单指标）
                resp_length = len(response)

                # 关键词命中率
                keyword_rate = self._calc_keyword_match_rate(
                    response, prompt
                )

                # 估算成本
                est_cost = self._estimate_cost(
                    provider_name,
                    len(prompt),
                    resp_length,
                )

                reports[provider_name] = EvaluationReport(
                    provider=provider_name,
                    latency_ms=round(elapsed_ms, 2),
                    response_length=resp_length,
                    keyword_match_rate=round(keyword_rate, 4),
                    estimated_cost=round(est_cost, 6),
                    raw_response=response,
                )

            except Exception as e:
                logger.warning(
                    "Provider %s 评估失败: %s", provider_name, e
                )
                reports[provider_name] = EvaluationReport(
                    provider=provider_name,
                    latency_ms=-1,
                    response_length=0,
                    keyword_match_rate=0.0,
                    estimated_cost=0.0,
                    raw_response=f"<ERROR: {e}>",
                )

        return reports

    # ------------------------------------------------------------------ #
    #  A/B 测试
    # ------------------------------------------------------------------ #

    async def ab_test(
        self,
        test_cases: List[TestCase],
        control_provider: str = "minimax",
        treatment_provider: str = "openai",
    ) -> ABTestResult:
        """A/B测试两个Provider的性能差异

        Args:
            test_cases: 测试用例列表
            control_provider: 对照组Provider
            treatment_provider: 实验组Provider

        Returns:
            A/B测试结果
        """
        control_metrics: List[float] = []
        treatment_metrics: List[float] = []

        control_latency: List[float] = []
        treatment_latency: List[float] = []

        control_cost: List[float] = []
        treatment_cost: List[float] = []

        control_responses: List[str] = []
        treatment_responses: List[str] = []

        for tc in test_cases:
            reports = await self.evaluate_response(
                prompt=tc.prompt,
                providers=[control_provider, treatment_provider],
                metrics=None,
            )

            ctrl = reports.get(control_provider)
            trtm = reports.get(treatment_provider)

            if ctrl and ctrl.latency_ms >= 0:
                score = self._composite_score(ctrl, tc)
                control_metrics.append(score)
                control_latency.append(ctrl.latency_ms)
                control_cost.append(ctrl.estimated_cost)
                control_responses.append(ctrl.raw_response)

            if trtm and trtm.latency_ms >= 0:
                score = self._composite_score(trtm, tc)
                treatment_metrics.append(score)
                treatment_latency.append(trtm.latency_ms)
                treatment_cost.append(trtm.estimated_cost)
                treatment_responses.append(trtm.raw_response)

        # 汇总对照组
        control_avg = mean(control_metrics) if control_metrics else 0.0
        treatment_avg = (
            mean(treatment_metrics) if treatment_metrics else 0.0
        )

        # 生成聚合报告
        control_report = EvaluationReport(
            provider=control_provider,
            latency_ms=round(mean(control_latency), 2) if control_latency else -1,
            response_length=sum(len(r) for r in control_responses),
            keyword_match_rate=round(control_avg, 4),
            estimated_cost=round(sum(control_cost), 6) if control_cost else 0.0,
            raw_response="\n---\n".join(control_responses),
        )

        treatment_report = EvaluationReport(
            provider=treatment_provider,
            latency_ms=round(mean(treatment_latency), 2) if treatment_latency else -1,
            response_length=sum(len(r) for r in treatment_responses),
            keyword_match_rate=round(treatment_avg, 4),
            estimated_cost=round(sum(treatment_cost), 6) if treatment_cost else 0.0,
            raw_response="\n---\n".join(treatment_responses),
        )

        # 判定胜者
        if control_avg <= 0 and treatment_avg <= 0:
            winner = "tie"
            improvement = 0.0
        elif control_avg <= 0:
            winner = "treatment"
            improvement = 100.0
        elif treatment_avg <= 0:
            winner = "control"
            improvement = 0.0
        else:
            diff = treatment_avg - control_avg
            improvement_pct = (diff / control_avg) * 100
            if improvement_pct > 5:
                winner = "treatment"
            elif improvement_pct < -5:
                winner = "control"
            else:
                winner = "tie"
            improvement = round(improvement_pct, 2)

        return ABTestResult(
            control=control_report,
            treatment=treatment_report,
            winner=winner,
            improvement_pct=improvement,
        )

    # ------------------------------------------------------------------ #
    #  自动选型
    # ------------------------------------------------------------------ #

    async def auto_select_best_provider(
        self,
        task_type: str,
    ) -> str:
        """根据任务类型自动选择最佳Provider

        策略：
        1. 按优先级依次尝试各Provider
        2. 通过实际调用评估质量（关键词理解）
        3. 返回得分最高的已配置Provider

        Args:
            task_type: 任务类型 ("wbs" | "risk" | "chat" | "report")

        Returns:
            选中的Provider名称
        """
        providers_to_test = TASK_TYPE_PROVIDER_RANKING.get(
            task_type,
            ["minimax", "deepseek", "openai"],
        )

        # 每个任务类型有默认的探测Prompt
        probe_prompts = {
            "wbs": "请为一个软件开发项目创建3个WBS工作包：需求分析、系统设计、编码实现。",
            "risk": "请列出项目管理中最常见的3个风险，并简要说明缓解措施。",
            "chat": "请用简洁的语言解释什么是敏捷开发方法。",
            "report": "请生成一个项目周报的模板框架，包含进度、问题、下一步计划。",
        }

        probe_prompt = probe_prompts.get(
            task_type,
            "请用中文回答：项目管理中最重要的三个要素是什么？",
        )

        candidate_scores: Dict[str, float] = {}

        for provider_name in providers_to_test:
            try:
                # 检查Provider是否可用
                status = self.engine.check_provider(provider_name)
                if not status.get("available", False):
                    logger.info("Provider %s 不可用，跳过", provider_name)
                    continue

                # 实际调用评估
                start = time.monotonic()
                response = await self.engine.generate(
                    probe_prompt,
                    provider=provider_name,
                    temperature=0.3,
                    max_tokens=512,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

                # 综合得分 = 关键词匹配率 * 0.5 + 延迟评分 * 0.3 + 成本评分 * 0.2
                keyword_rate = self._calc_keyword_match_rate(
                    response, probe_prompt
                )
                latency_score = self._latency_score(elapsed_ms)
                cost = self._estimate_cost(
                    provider_name, len(probe_prompt), len(response)
                )
                cost_score = self._cost_score(cost)

                composite = (
                    keyword_rate * 0.5
                    + latency_score * 0.3
                    + cost_score * 0.2
                )
                candidate_scores[provider_name] = round(composite, 4)

                logger.info(
                    "Provider %s 评估: keyword=%.3f latency=%.3f cost=%.3f -> composite=%.3f",
                    provider_name, keyword_rate, latency_score, cost_score, composite,
                )

            except Exception as e:
                logger.warning(
                    "Provider %s 自动选型失败: %s", provider_name, e
                )

        if not candidate_scores:
            logger.warning("所有Provider均不可用，回退到默认Provider")
            return providers_to_test[0] if providers_to_test else "minimax"

        # 选择综合得分最高的Provider
        best_provider = max(candidate_scores, key=candidate_scores.get)
        logger.info(
            "任务类型 %s 自动选型结果: %s (scores: %s)",
            task_type, best_provider, candidate_scores,
        )
        return best_provider

    # ------------------------------------------------------------------ #
    #  内部辅助方法
    # ------------------------------------------------------------------ #

    def _calc_keyword_match_rate(
        self, response: str, prompt: str
    ) -> float:
        """计算响应对提示词中关键词的理解程度

        从prompt中提取有意义的词汇，检查response中出现的比例。
        """
        # 提取中文/英文关键词（去除停用词）
        keywords = set()
        # 中文词（2个字以上）
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,}", prompt)
        keywords.update(cn_words)
        # 英文词（长度>=4，排除常见词）
        en_words = re.findall(r"\b[a-zA-Z]{4,}\b", prompt)
        stop_words = {
            "this", "that", "with", "from", "have", "been",
            "what", "when", "where", "which", "their",
        }
        keywords.update(w.lower() for w in en_words if w.lower() not in stop_words)

        if not keywords:
            return 1.0  # 没有可提取的关键词，视为满分

        response_lower = response.lower()
        match_count = sum(
            1 for kw in keywords if kw.lower() in response_lower
        )
        return match_count / len(keywords)

    def _estimate_cost(
        self,
        provider: str,
        prompt_chars: int,
        response_chars: int,
    ) -> float:
        """估算本次调用的成本（人民币元）"""
        rate = COST_PER_1K_TOKENS.get(provider, 0.01)
        # 粗略估算：1个token ≈ 2个中文字符
        total_tokens = (prompt_chars + response_chars) // 2
        return (total_tokens / 1000) * rate

    def _composite_score(
        self,
        report: EvaluationReport,
        test_case: TestCase,
    ) -> float:
        """计算单次响应的综合评分

        评分维度：
        - 关键词匹配率（越高越好）
        - 延迟评分（越低越好）
        - 长度合理性（既不过短也不过长）
        """
        kw_score = report.keyword_match_rate

        if report.latency_ms <= 0:
            latency_score = 0.0
        elif report.latency_ms >= test_case.max_latency_ms:
            latency_score = 0.1
        else:
            latency_score = 1.0 - (report.latency_ms / test_case.max_latency_ms)

        # 长度合理性：50～5000字符为合理区间
        length = report.response_length
        if 50 <= length <= 5000:
            length_score = 1.0
        elif length < 50:
            length_score = length / 50
        else:
            length_score = max(0, 1.0 - (length - 5000) / 5000)

        return kw_score * 0.5 + latency_score * 0.3 + length_score * 0.2

    def _latency_score(self, latency_ms: float) -> float:
        """延迟评分：0～1，延迟越低分数越高"""
        if latency_ms <= 0:
            return 0.0
        if latency_ms <= 1000:
            return 1.0
        if latency_ms >= 30000:
            return 0.0
        return 1.0 - (latency_ms - 1000) / 29000

    def _cost_score(self, cost: float) -> float:
        """成本评分：0～1，成本越低分数越高"""
        if cost <= 0:
            return 0.5
        if cost <= 0.001:
            return 1.0
        if cost >= 1.0:
            return 0.0
        return 1.0 - (cost / 1.0)

    def get_supported_task_types(self) -> List[str]:
        """返回支持的评估任务类型列表"""
        return list(TASK_TYPE_PROVIDER_RANKING.keys())
