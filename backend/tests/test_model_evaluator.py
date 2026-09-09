"""
测试AI模型评估与A/B测试框架
使用mock避免真实LLM调用
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict

from app.services.ai.model_evaluator import (
    ModelEvaluator,
    TestCase,
    EvaluationReport,
    ABTestResult,
)


@pytest.fixture
def mock_ai_engine():
    """Mock AIEngine实例，避免真实的LLM调用"""
    with patch("app.services.ai.model_evaluator.ai_engine") as mock:
        # generate() 返回模拟响应
        mock.generate = AsyncMock(side_effect=_mock_generate)

        # check_provider() 默认返回可用
        mock.check_provider = MagicMock(
            return_value={"available": True, "error": None}
        )

        yield mock


def _mock_generate(prompt: str, provider: str = None, **kwargs) -> str:
    """根据不同的provider返回模拟响应"""
    responses: Dict[str, str] = {
        "minimax": (
            "根据项目管理最佳实践，WBS应包含以下工作包："
            "1. 需求分析 - 收集和确认用户需求；"
            "2. 系统设计 - 架构设计和详细设计；"
            "3. 编码实现 - 按迭代开发功能模块。"
        ),
        "openai": (
            "WBS分解为三个主要工作包：\n"
            "- 需求分析：包括需求调研、需求评审\n"
            "- 系统设计：包含架构设计、接口设计\n"
            "- 编码实现：包括单元测试、集成测试"
        ),
        "deepseek": (
            "项目WBS如下：\n"
            "需求分析阶段：需求收集、需求确认\n"
            "设计阶段：概要设计、详细设计\n"
            "开发阶段：编码、测试、部署"
        ),
        "anthropic": (
            "工作分解结构建议：\n"
            "1. 需求分析\n"
            "2. 系统设计\n"
            "3. 编码实现\n"
            "4. 测试验证\n"
            "5. 部署上线"
        ),
    }

    # 返回对应provider的模拟响应，或默认响应
    return responses.get(
        provider or "minimax",
        "这是一个模拟的AI响应，用于测试模型评估器。",
    )


class TestModelEvaluator:
    """ModelEvaluator 单元测试"""

    @pytest.mark.asyncio
    async def test_evaluate_response_single_provider(self, mock_ai_engine):
        """测试单个Provider的评估"""
        evaluator = ModelEvaluator()
        reports = await evaluator.evaluate_response(
            prompt="请创建一个项目的WBS分解",
            providers=["minimax"],
        )

        assert "minimax" in reports
        report = reports["minimax"]
        assert isinstance(report, EvaluationReport)
        assert report.provider == "minimax"
        assert report.latency_ms >= 0
        assert report.response_length > 0
        assert 0 <= report.keyword_match_rate <= 1
        assert report.estimated_cost >= 0
        assert len(report.raw_response) > 0

    @pytest.mark.asyncio
    async def test_evaluate_response_multiple_providers(self, mock_ai_engine):
        """测试多个Provider的对比评估"""
        evaluator = ModelEvaluator()
        reports = await evaluator.evaluate_response(
            prompt="请列出敏捷开发的核心原则",
            providers=["minimax", "openai", "deepseek"],
        )

        assert len(reports) == 3
        for name in ("minimax", "openai", "deepseek"):
            assert name in reports
            assert reports[name].latency_ms >= 0

    @pytest.mark.asyncio
    async def test_evaluate_response_provider_failure(self, mock_ai_engine):
        """测试当某个provider调用失败时的容错"""
        evaluator = ModelEvaluator()

        # 让openai抛出异常，minimax正常返回
        async def _failing_generate(prompt, provider=None, **kwargs):
            if provider == "openai":
                raise RuntimeError("API key invalid")
            return _mock_generate(prompt, provider, **kwargs)

        mock_ai_engine.generate.side_effect = _failing_generate

        reports = await evaluator.evaluate_response(
            prompt="测试用例",
            providers=["minimax", "openai"],
        )

        assert "minimax" in reports
        assert reports["minimax"].latency_ms >= 0

        assert "openai" in reports
        assert reports["openai"].latency_ms == -1
        assert "<ERROR:" in reports["openai"].raw_response

    @pytest.mark.asyncio
    async def test_ab_test_tie(self, mock_ai_engine):
        """测试A/B测试 - 两个Provider性能接近"""
        evaluator = ModelEvaluator()

        test_cases = [
            TestCase(
                prompt="请创建一个项目计划",
                expected_keywords=["计划", "任务", "时间"],
                max_latency_ms=10000,
            ),
            TestCase(
                prompt="请列出风险管理步骤",
                expected_keywords=["风险", "识别", "应对"],
                max_latency_ms=10000,
            ),
        ]

        result = await evaluator.ab_test(
            test_cases=test_cases,
            control_provider="minimax",
            treatment_provider="openai",
        )

        assert isinstance(result, ABTestResult)
        assert result.control.provider == "minimax"
        assert result.treatment.provider == "openai"
        assert result.winner in ("control", "treatment", "tie")
        assert isinstance(result.improvement_pct, float)

    @pytest.mark.asyncio
    async def test_ab_test_clear_winner(self, mock_ai_engine):
        """测试A/B测试 - 某一方明显更优"""
        evaluator = ModelEvaluator()

        # 让openai的响应质量显著高于minimax
        orig_generate = mock_ai_engine.generate

        async def _biased_generate(prompt, provider=None, **kwargs):
            if provider == "minimax":
                return "好"
            # openai返回包含更多关键词
            return (
                "项目管理和风险识别非常重要，"
                "需要制定计划和时间表，分配任务和资源。"
            )

        mock_ai_engine.generate.side_effect = _biased_generate

        test_cases = [
            TestCase(
                prompt="项目管理 风险 计划 任务 时间 资源",
                max_latency_ms=10000,
            ),
        ]

        result = await evaluator.ab_test(
            test_cases=test_cases,
            control_provider="minimax",
            treatment_provider="openai",
        )

        assert result.winner == "treatment"
        assert result.improvement_pct > 0

    @pytest.mark.asyncio
    async def test_auto_select_best_provider(self, mock_ai_engine):
        """测试根据任务类型自动选择最佳Provider"""
        evaluator = ModelEvaluator()

        # 让 deepseek 返回更高质量响应
        orig_generate = mock_ai_engine.generate

        async def _biased_generate(prompt, provider=None, **kwargs):
            if provider == "deepseek":
                return (
                    "项目WBS分解包含三个核心工作包："
                    "需求分析、系统设计、编码实现。"
                    "每个工作包需要详细的任务分解。"
                )
            return "WBS分解"

        mock_ai_engine.generate.side_effect = _biased_generate

        best = await evaluator.auto_select_best_provider(task_type="wbs")
        assert isinstance(best, str)
        assert len(best) > 0

    @pytest.mark.asyncio
    async def test_auto_select_fallback_on_failure(self, mock_ai_engine):
        """测试所有Provider均不可用时的回退行为"""
        evaluator = ModelEvaluator()

        mock_ai_engine.check_provider.return_value = {
            "available": False,
            "error": "not configured",
        }

        best = await evaluator.auto_select_best_provider(task_type="chat")
        # 应该回退到列表中的第一个
        assert best == "deepseek"

    @pytest.mark.asyncio
    async def test_get_supported_task_types(self):
        """测试获取支持的任务类型列表"""
        evaluator = ModelEvaluator()
        types = evaluator.get_supported_task_types()
        assert "wbs" in types
        assert "risk" in types
        assert "chat" in types
        assert "report" in types
        assert len(types) == 4

    def test_keyword_match_rate(self):
        """测试关键词匹配率计算"""
        evaluator = ModelEvaluator()

        response = "需求分析包括需求收集和需求评审"
        prompt = "请描述需求分析阶段的工作内容"

        rate = evaluator._calc_keyword_match_rate(response, prompt)
        assert 0 <= rate <= 1

    def test_composite_score(self):
        """测试综合评分计算"""
        evaluator = ModelEvaluator()

        report = EvaluationReport(
            provider="minimax",
            latency_ms=500,
            response_length=300,
            keyword_match_rate=0.8,
            estimated_cost=0.01,
            raw_response="测试响应",
        )
        test_case = TestCase(
            prompt="测试",
            max_latency_ms=10000,
        )

        score = evaluator._composite_score(report, test_case)
        assert 0 <= score <= 1

    def test_estimate_cost(self):
        """测试成本估算"""
        evaluator = ModelEvaluator()

        cost = evaluator._estimate_cost(
            provider="openai",
            prompt_chars=100,
            response_chars=500,
        )
        assert cost > 0

        # minimax 成本应该不同
        cost2 = evaluator._estimate_cost(
            provider="minimax",
            prompt_chars=100,
            response_chars=500,
        )
        assert cost2 != cost
