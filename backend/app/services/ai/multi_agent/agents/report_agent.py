"""
PMI中国AI项目管理社区 - 报告生成 Agent
提供日志收集、格式化和报告生成功能
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from ..helpers import AgentLog, AgentResult, BaseAgent


class ReportAgent:
    """
    报告生成Agent
    收集Agent执行日志，生成格式化报告
    """

    @staticmethod
    def format_logs(logs: List[AgentLog]) -> List[Dict[str, Any]]:
        """格式化日志为字典列表"""
        return [
            {
                "id": log.id,
                "agent_name": log.agent_name,
                "action": log.action,
                "content": log.content,
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
            }
            for log in sorted(logs, key=lambda x: x.timestamp)
        ]

    @staticmethod
    def collect_agent_logs(agents: List[BaseAgent]) -> List[AgentLog]:
        """收集多个Agent的日志"""
        all_logs: List[AgentLog] = []
        for agent in agents:
            all_logs.extend(agent.get_logs())
        return all_logs

    @staticmethod
    def generate_summary_report(
        objective: str,
        subtask_results: List[Dict[str, Any]],
        review: Optional[Dict[str, Any]] = None,
        execution_time: float = 0.0,
    ) -> Dict[str, Any]:
        """生成摘要报告"""
        total = len(subtask_results)
        succeeded = sum(1 for r in subtask_results if r.get("status") == "completed")
        failed = total - succeeded

        report = {
            "objective": objective,
            "total_subtasks": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": f"{succeeded / total * 100:.1f}%" if total > 0 else "N/A",
            "execution_time_seconds": execution_time,
            "generated_at": datetime.now().isoformat(),
        }

        if review:
            report["review"] = review

        return report
