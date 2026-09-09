"""项目报告模板 / 提示词"""

PROJECT_REPORT_PROMPT = """你是一位资深的项目管理和业务分析专家，请根据以下项目数据，生成一份项目状态报告。

项目数据（JSON格式）：
{project_data}

请严格按照以下JSON格式输出项目报告（不要包含任何markdown代码块标记，只输出纯JSON）：
{{
    "summary": "项目整体状态摘要，3-5句话概括项目健康状况、关键进展和风险",
    "health_score": 85,
    "health_status": "healthy|warning|critical",
    "progress": {{
        "total_tasks": 0,
        "completed_tasks": 0,
        "completion_rate": 0,
        "avg_progress": 0,
        "milestone_status": "on_track|at_risk|delayed"
    }},
    "risks": [
        {{
            "name": "风险名称",
            "level": "high|medium|low",
            "description": "风险描述",
            "impact": "对项目的影响描述"
        }}
    ],
    "team_contributions": [
        {{
            "user_id": "用户ID",
            "user_name": "用户姓名",
            "completed_tasks": 0,
            "total_hours": 0,
            "contribution_summary": "贡献描述"
        }}
    ],
    "milestones": [
        {{
            "name": "里程碑名称",
            "due_date": "截止日期",
            "status": "completed|on_track|at_risk|delayed",
            "description": "状态描述"
        }}
    ],
    "recommendations": [
        "建议1：基于项目数据的 actionable 建议",
        "建议2：基于项目数据的 actionable 建议",
        "建议3：基于项目数据的 actionable 建议"
    ],
    "stats": {{
        "total_tasks": 0,
        "completed_tasks": 0,
        "in_progress_tasks": 0,
        "total_risks": 0,
        "high_risks": 0,
        "team_size": 0,
        "total_hours": 0
    }}
}}

要求：
1. summary 要客观反映项目真实状态
2. health_score 是0-100的分数，基于进度、风险、里程碑综合评估
3. health_status 基于 health_score：>=80 healthy, >=60 warning, <60 critical
4. team_contributions 要体现每个成员的实际贡献
5. recommendations 要具体、可执行
6. 所有数据必须基于提供的项目数据，不要编造
7. 只输出JSON，不要任何解释文字"""
