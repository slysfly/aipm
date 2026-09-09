"""
PMI中国AI项目管理社区 - 报表导出（CSV 序列化）

从 report_service 拆分而来，负责将各类报表数据序列化为 CSV 字节流。
仅依赖标准库，不反向依赖 report_service。
"""

import csv
import io
from typing import Any, Dict, Tuple


def build_report_csv(data: Dict[str, Any], report_type: str) -> Tuple[bytes, str]:
    """将报表数据序列化为 CSV 字节流，返回 (字节内容, MIME 类型)。"""
    output = io.StringIO()
    writer = csv.writer(output)

    if report_type == "project-progress":
        writer.writerow(["项目进度报表"])
        writer.writerow(["项目ID", data.get("project_id", "")])
        writer.writerow(["项目名称", data.get("project_name", "")])
        writer.writerow(["总任务数", data.get("total_tasks", 0)])
        writer.writerow(["已完成", data.get("completed_tasks", 0)])
        writer.writerow(["完成率(%)", data.get("completion_rate", 0)])
        writer.writerow([])
        writer.writerow(["周期", "创建数", "完成数", "完成率(%)"])
        for item in data.get("trend", []):
            writer.writerow([
                item.get("period", ""),
                item.get("created", 0),
                item.get("completed", 0),
                item.get("completion_rate", 0)
            ])

    elif report_type == "burndown":
        writer.writerow(["燃尽图数据"])
        writer.writerow(["项目ID", data.get("project_id", "")])
        writer.writerow(["总任务数", data.get("total_tasks", 0)])
        writer.writerow([])
        writer.writerow(["日期", "理想剩余", "实际剩余", "创建数", "完成数"])
        for item in data.get("data", []):
            writer.writerow([
                item.get("date", ""),
                item.get("ideal_remaining", 0),
                item.get("actual_remaining", 0),
                item.get("created", 0),
                item.get("completed", 0)
            ])

    elif report_type == "velocity":
        writer.writerow(["速度图数据"])
        writer.writerow(["项目ID", data.get("project_id", "")])
        writer.writerow(["平均速度", data.get("avg_velocity", 0)])
        writer.writerow([])
        writer.writerow(["迭代", "开始日期", "完成任务", "估算工时", "实际工时", "速度"])
        for item in data.get("sprints", []):
            writer.writerow([
                item.get("sprint", 0),
                item.get("start_date", ""),
                item.get("completed_tasks", 0),
                item.get("estimated_hours", 0),
                item.get("actual_hours", 0),
                item.get("velocity", 0)
            ])

    elif report_type == "evm":
        writer.writerow(["EVM挣值管理报表"])
        writer.writerow(["项目ID", data.get("project_id", "")])
        writer.writerow([])
        current = data.get("current", {})
        writer.writerow(["指标", "数值"])
        writer.writerow(["PV(计划值)", current.get("pv", 0)])
        writer.writerow(["EV(挣值)", current.get("ev", 0)])
        writer.writerow(["AC(实际成本)", current.get("ac", 0)])
        writer.writerow(["BAC(预算)", current.get("bac", 0)])
        writer.writerow(["CV(成本偏差)", current.get("cv", 0)])
        writer.writerow(["SV(进度偏差)", current.get("sv", 0)])
        writer.writerow(["CPI(成本绩效)", current.get("cpi", 0)])
        writer.writerow(["SPI(进度绩效)", current.get("spi", 0)])
        writer.writerow(["EAC(完工估算)", current.get("eac", 0)])
        writer.writerow(["ETC(完工尚需)", current.get("etc", 0)])
        writer.writerow(["VAC(完工偏差)", current.get("vac", 0)])
        writer.writerow(["TCPI(完工绩效)", current.get("tcpi", 0)])
        writer.writerow([])
        writer.writerow(["日期", "PV", "EV", "AC", "CPI", "SPI"])
        for item in data.get("trend", []):
            writer.writerow([
                item.get("date", ""),
                item.get("pv", 0),
                item.get("ev", 0),
                item.get("ac", 0),
                item.get("cpi", 0),
                item.get("spi", 0)
            ])

    elif report_type == "resource-utilization":
        writer.writerow(["资源利用率报表"])
        writer.writerow(["项目ID", data.get("project_id", "")])
        writer.writerow(["平均利用率(%)", data.get("avg_utilization_rate", 0)])
        writer.writerow([])
        writer.writerow(["资源ID", "分配工时", "分配次数", "利用率(%)"])
        for item in data.get("resources", []):
            writer.writerow([
                item.get("resource_id", ""),
                item.get("allocated_hours", 0),
                item.get("allocation_count", 0),
                item.get("utilization_rate", 0)
            ])

    else:
        writer.writerow(["报表数据"])
        writer.writerow([str(data)])

    return output.getvalue().encode("utf-8-sig"), "text/csv"
