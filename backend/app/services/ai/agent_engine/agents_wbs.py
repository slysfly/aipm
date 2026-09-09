"""
WBS (Work Breakdown Structure) Agent 模块
提供WBS相关工作分解结构相关的Agent逻辑
"""

from typing import List, Dict, Any


# WBS级别的提示模板
WBS_BREAKDOWN_PROMPT = """你是一位资深项目管理专家，擅长WBS工作分解结构。
请将以下项目任务分解为层级化的WBS结构。

项目名称：{project_name}
项目描述：{project_description}

要求：
1. 至少分解到3级WBS
2. 每个任务包含预估工期和负责人
3. 识别任务间的依赖关系
4. 标注关键路径
"""


def format_wbs_tree(tasks: List[Dict[str, Any]], level: int = 0) -> str:
    """将WBS任务列表格式化为树形文本"""
    lines = []
    indent = "  " * level
    for task in tasks:
        prefix = f"{indent}{task.get('wbs_code', '')}"
        lines.append(f"{prefix} {task.get('name', '')}")
        children = task.get("children", [])
        if children:
            lines.append(format_wbs_tree(children, level + 1))
    return "\n".join(lines)
