"""周报模板 / 提示词"""

WEEKLY_REPORT_PROMPT = """你是一位资深的项目管理专家，请根据以下用户本周的工作数据，生成一份结构化的周报。

用户本周工作数据（JSON格式）：
{work_data}

请严格按照以下JSON格式输出周报（不要包含任何markdown代码块标记，只输出纯JSON）：
{{
    "summary": "本周工作综述，3-5句话概括本周整体表现和关键成果",
    "highlights": [
        "本周亮点1：具体成果",
        "本周亮点2：具体成果",
        "本周亮点3：具体成果"
    ],
    "completed": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "project_name": "所属项目名称",
            "completed_at": "完成时间",
            "description": "完成情况描述"
        }}
    ],
    "in_progress": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "project_name": "所属项目名称",
            "progress": 65,
            "description": "当前进展"
        }}
    ],
    "blockers": [
        {{
            "type": "task|resource|dependency|other",
            "description": "阻塞项描述",
            "duration_days": 3,
            "related_task_id": ""
        }}
    ],
    "next_week_plan": [
        "下周计划1",
        "下周计划2",
        "下周计划3"
    ],
    "stats": {{
        "completed_tasks": 0,
        "total_hours": 0,
        "project_count": 0,
        "comment_count": 0,
        "avg_task_completion_time": 0
    }}
}}

要求：
1. summary 要全面概括本周工作，体现价值和进展
2. highlights 要突出本周最重要的3-5个成果
3. stats 中的数据要基于实际数据计算
4. next_week_plan 要基于未完成的工作和项目优先级合理安排
5. blockers 要识别本周遇到的和仍然存在的阻塞
6. 所有数据必须基于提供的工作数据，不要编造
7. 只输出JSON，不要任何解释文字"""
