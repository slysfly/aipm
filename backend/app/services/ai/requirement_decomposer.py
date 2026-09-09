"""
PMI中国AI项目管理社区 - AI需求自动拆分服务
使用LLM将需求描述拆分为结构化子任务

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — AI需求分解]"""

import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.ai_engine import ai_engine
from app.models import User, Task, Project


class RequirementDecomposer:
    """需求拆分器：将需求描述拆分为可执行的子任务"""

    PRIORITY_MAP = {
        "highest": 1, "critical": 1, "p1": 1, "最高": 1, "紧急": 1,
        "high": 2, "p2": 2, "高": 2,
        "medium": 3, "normal": 3, "p3": 3, "中": 3, "普通": 3,
        "low": 4, "p4": 4, "低": 4,
        "lowest": 5, "p5": 5, "最低": 5,
    }

    def __init__(self):
        pass

    async def decompose(
        self,
        requirement_text: str,
        project_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        """
        将需求拆分为子任务

        Args:
            requirement_text: 需求描述文本
            project_id: 项目ID（用于上下文分析）
            db: 数据库会话

        Returns:
            list[dict]: 子任务列表，每个包含name, description, estimated_hours, priority, dependencies, assignee_suggestion
        """
        if not requirement_text or not requirement_text.strip():
            raise ValueError("需求描述不能为空")

        # 获取项目上下文
        project_context = ""
        if db and project_id:
            project_context = await self._get_project_context(db, project_id)

        # 使用LLM进行需求拆分
        tasks = await self._llm_decompose(requirement_text, project_context)

        # 分析依赖关系
        tasks = self.analyze_dependencies(tasks)

        # 建议负责人
        if db and project_id:
            members = await self._get_project_members(db, project_id)
            tasks = self.suggest_assignees(tasks, members)

        return tasks

    async def _llm_decompose(
        self,
        requirement_text: str,
        project_context: str = "",
    ) -> List[Dict[str, Any]]:
        """使用LLM拆分需求"""

        system_prompt = """你是一个资深软件架构师和项目经理。你的任务是将用户需求拆分为详细的、可执行的技术子任务。

请分析需求，提取功能点和技术点，输出子任务列表（JSON数组格式）。

每个子任务必须包含以下字段：
- name: 子任务名称（简洁明确，20字以内）
- description: 详细描述（包含具体要实现的功能、技术方案、验收标准）
- estimated_hours: 预估工时（小时，基于实际开发经验，不要低估）
- priority: 优先级（high/medium/low）
- dependencies: 依赖的子任务名称列表（该任务依赖哪些前置任务，用name匹配）
- category: 任务类别（frontend/backend/database/devops/testing/design/docs）
- skills_required: 所需技能列表

拆分原则：
1. 每个子任务应该是独立可执行的，粒度适中（通常4-16小时）
2. 必须包含前端、后端、数据库、测试等相关任务
3. 识别任务间的依赖关系
4. 考虑非功能性需求（性能、安全、日志等）
5. 如果需求涉及第三方集成，单独列出集成任务
6. 必须包含文档和测试相关任务

示例输入："开发一个用户登录系统，支持手机号+验证码登录、微信扫码登录、密码找回功能"

示例输出：
[
  {
    "name": "设计登录页面UI",
    "description": "设计并实现登录页面的用户界面，包含手机号输入框、验证码输入框、微信扫码入口、密码找回链接。使用响应式设计，支持移动端适配。",
    "estimated_hours": 8,
    "priority": "high",
    "dependencies": [],
    "category": "frontend",
    "skills_required": ["React", "CSS", "UI设计"]
  },
  {
    "name": "实现手机号验证码登录API",
    "description": "开发手机号验证码登录后端接口：发送验证码（集成短信服务商）、验证码校验、JWT Token生成、登录态管理。包含频率限制和防刷机制。",
    "estimated_hours": 12,
    "priority": "high",
    "dependencies": ["设计数据库用户表结构"],
    "category": "backend",
    "skills_required": ["Python", "FastAPI", "Redis"]
  },
  {
    "name": "集成微信扫码登录",
    "description": "集成微信开放平台扫码登录：申请微信应用、实现OAuth2授权流程、用户信息获取与绑定、回调处理。",
    "estimated_hours": 10,
    "priority": "medium",
    "dependencies": ["设计数据库用户表结构"],
    "category": "backend",
    "skills_required": ["OAuth2", "微信SDK", "Python"]
  },
  {
    "name": "实现密码找回功能",
    "description": "开发密码找回流程：验证身份（手机验证码或邮箱）、生成重置令牌、安全重置密码、邮件/短信通知。",
    "estimated_hours": 8,
    "priority": "medium",
    "dependencies": ["设计数据库用户表结构"],
    "category": "backend",
    "skills_required": ["Python", "FastAPI", "邮件服务"]
  },
  {
    "name": "编写登录模块单元测试",
    "description": "为登录相关接口编写单元测试和集成测试，覆盖正常流程和异常流程，确保代码覆盖率>80%。",
    "estimated_hours": 6,
    "priority": "medium",
    "dependencies": ["实现手机号验证码登录API", "集成微信扫码登录", "实现密码找回功能"],
    "category": "testing",
    "skills_required": ["pytest", "自动化测试"]
  }
]"""

        user_prompt = f"请拆分以下需求：\n\n{requirement_text}"
        if project_context:
            user_prompt += f"\n\n项目背景：\n{project_context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await ai_engine.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=4000,
            )

            # 提取JSON数组
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                tasks = json.loads(json_match.group())
            else:
                # 尝试解析整个响应
                tasks = json.loads(response)

            # 标准化字段
            for task in tasks:
                task["priority"] = self._normalize_priority(task.get("priority", "medium"))
                task["estimated_hours"] = float(task.get("estimated_hours", 0))
                task["dependencies"] = task.get("dependencies", []) or []
                task["category"] = task.get("category", "backend")
                task["skills_required"] = task.get("skills_required", []) or []
                task["assignee_suggestion"] = task.get("assignee_suggestion", "")

            return tasks

        except json.JSONDecodeError:
            # LLM返回格式不正确，使用降级策略
            return self._fallback_decompose(requirement_text)
        except Exception:
            return self._fallback_decompose(requirement_text)

    def _fallback_decompose(self, requirement_text: str) -> List[Dict[str, Any]]:
        """当LLM解析失败时的降级拆分"""
        tasks = []

        # 提取关键词判断需求类型
        text_lower = requirement_text.lower()

        # 通用任务模板
        tasks.append({
            "name": "需求分析与方案设计",
            "description": f"分析需求：{requirement_text[:100]}，输出技术方案和接口设计文档",
            "estimated_hours": 4,
            "priority": 1,
            "dependencies": [],
            "category": "design",
            "skills_required": ["需求分析", "架构设计"],
            "assignee_suggestion": "",
        })

        if any(k in text_lower for k in ["页面", "ui", "界面", "前端", "组件"]):
            tasks.append({
                "name": "前端页面开发",
                "description": "根据设计稿实现前端页面和交互逻辑",
                "estimated_hours": 16,
                "priority": 2,
                "dependencies": ["需求分析与方案设计"],
                "category": "frontend",
                "skills_required": ["React", "TypeScript", "CSS"],
                "assignee_suggestion": "",
            })

        if any(k in text_lower for k in ["api", "接口", "后端", "服务", "数据库"]):
            tasks.append({
                "name": "后端API开发",
                "description": "设计和实现后端接口，包含业务逻辑和数据处理",
                "estimated_hours": 16,
                "priority": 2,
                "dependencies": ["需求分析与方案设计"],
                "category": "backend",
                "skills_required": ["Python", "FastAPI", "SQLAlchemy"],
                "assignee_suggestion": "",
            })

        if any(k in text_lower for k in ["数据库", "表", "存储", "数据"]):
            tasks.append({
                "name": "数据库设计与实现",
                "description": "设计数据库表结构，编写迁移脚本",
                "estimated_hours": 8,
                "priority": 1,
                "dependencies": ["需求分析与方案设计"],
                "category": "database",
                "skills_required": ["SQL", "数据库设计"],
                "assignee_suggestion": "",
            })

        # 测试任务
        tasks.append({
            "name": "功能测试与Bug修复",
            "description": "编写测试用例，执行功能测试，修复发现的问题",
            "estimated_hours": 8,
            "priority": 3,
            "dependencies": [t["name"] for t in tasks if t["category"] in ["frontend", "backend"]],
            "category": "testing",
            "skills_required": ["测试", "Bug跟踪"],
            "assignee_suggestion": "",
        })

        # 文档任务
        tasks.append({
            "name": "技术文档编写",
            "description": "编写接口文档、部署文档和使用说明",
            "estimated_hours": 4,
            "priority": 4,
            "dependencies": ["功能测试与Bug修复"],
            "category": "docs",
            "skills_required": ["技术写作"],
            "assignee_suggestion": "",
        })

        return tasks

    def analyze_dependencies(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        分析任务间依赖关系，添加依赖索引和拓扑排序信息

        Args:
            tasks: 子任务列表

        Returns:
            添加了依赖分析信息的任务列表
        """
        # 建立名称到索引的映射
        name_to_index = {t["name"]: i for i, t in enumerate(tasks)}

        for i, task in enumerate(tasks):
            deps = task.get("dependencies", [])
            resolved_deps = []
            dep_indices = []

            for dep_name in deps:
                if dep_name in name_to_index:
                    resolved_deps.append(dep_name)
                    dep_indices.append(name_to_index[dep_name])

            task["dependencies"] = resolved_deps
            task["dependency_indices"] = dep_indices

            # 计算层级（拓扑层级）
            if not dep_indices:
                task["level"] = 0
            else:
                task["level"] = max(tasks[j].get("level", 0) for j in dep_indices) + 1

        return tasks

    def suggest_assignees(
        self,
        tasks: List[Dict[str, Any]],
        project_members: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        根据技能匹配建议负责人

        Args:
            tasks: 子任务列表
            project_members: 项目成员列表，每个包含id, full_name, username, skills等

        Returns:
            添加了负责人建议的任务列表
        """
        if not project_members:
            for task in tasks:
                task["assignee_suggestion"] = ""
                task["assignee_match_score"] = 0
            return tasks

        for task in tasks:
            task_skills = set(s.lower() for s in task.get("skills_required", []))
            best_match = None
            best_score = 0

            for member in project_members:
                member_skills = set(s.lower() for s in member.get("skills", []))
                if not member_skills and not task_skills:
                    score = 0.5
                elif not member_skills:
                    score = 0.1
                else:
                    intersection = task_skills & member_skills
                    union = task_skills | member_skills
                    if union:
                        score = len(intersection) / len(union)
                    else:
                        score = 0.5

                # 根据类别额外加分
                category = task.get("category", "")
                position = member.get("position", "").lower()
                if category == "frontend" and any(k in position for k in ["前端", "frontend", "ui"]):
                    score += 0.3
                elif category == "backend" and any(k in position for k in ["后端", "backend", "服务端"]):
                    score += 0.3
                elif category == "testing" and any(k in position for k in ["测试", "qa", "质量"]):
                    score += 0.3
                elif category == "design" and any(k in position for k in ["设计", "design", "产品"]):
                    score += 0.3

                if score > best_score:
                    best_score = score
                    best_match = member

            if best_match and best_score > 0.1:
                task["assignee_suggestion"] = best_match.get("full_name") or best_match.get("username", "")
                task["assignee_suggestion_id"] = best_match.get("id", "")
                task["assignee_match_score"] = round(best_score, 2)
            else:
                task["assignee_suggestion"] = ""
                task["assignee_suggestion_id"] = ""
                task["assignee_match_score"] = 0

        return tasks

    async def _get_project_context(self, db: AsyncSession, project_id: str) -> str:
        """获取项目上下文信息"""
        try:
            result = await db.execute(
                select(Project).where(Project.id == project_id, Project.is_deleted == False)
            )
            project = result.scalar_one_or_none()
            if project:
                return f"项目名称：{project.name}\n项目描述：{project.description or ''}\n项目类型：{project.project_type}"
            return ""
        except Exception:
            return ""

    async def _get_project_members(self, db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
        """获取项目成员列表"""
        try:
            # 查询项目成员（通过任务分配推断，或查询项目关联用户）
            # 这里简化处理，查询所有活跃用户
            result = await db.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()
            return [
                {
                    "id": u.id,
                    "full_name": u.full_name,
                    "username": u.username,
                    "skills": [],  # 可以从用户profile或历史任务推断
                    "position": u.position or "",
                }
                for u in users
            ]
        except Exception:
            return []

    def _normalize_priority(self, priority: Any) -> int:
        """标准化优先级为1-5的数字"""
        if isinstance(priority, int):
            if 1 <= priority <= 5:
                return priority
            return 3
        if isinstance(priority, str):
            p_lower = priority.lower()
            if p_lower in self.PRIORITY_MAP:
                return self.PRIORITY_MAP[p_lower]
        return 3


# 全局实例
requirement_decomposer = RequirementDecomposer()
