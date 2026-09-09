"""
PMI中国AI项目管理社区 - AI自然语言任务解析服务
使用OpenAI GPT-4进行自然语言任务描述的结构化提取

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — NLP任务解析]"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.ai_engine import ai_engine
from app.models import User, Task


class NLPTaskParser:
    """自然语言任务解析器"""

    # 优先级映射
    PRIORITY_MAP = {
        "highest": 1, "critical": 1, "p1": 1, "最高": 1, "紧急": 1, "critical": 1,
        "high": 2, "p2": 2, "高": 2,
        "medium": 3, "normal": 3, "p3": 3, "中": 3, "普通": 3,
        "low": 4, "p4": 4, "低": 4,
        "lowest": 5, "p5": 5, "最低": 5,
    }

    # 标签关键词映射
    LABEL_KEYWORDS = {
        "frontend": ["前端", "frontend", "ui", "界面", "页面", "css", "html", "react", "vue"],
        "backend": ["后端", "backend", "api", "接口", "服务器", "server", "数据库", "db"],
        "mobile": ["移动端", "mobile", "app", "ios", "android", "小程序", "flutter"],
        "devops": ["devops", "运维", "部署", "ci/cd", "docker", "k8s", "kubernetes", "jenkins"],
        "testing": ["测试", "testing", "qa", "自动化测试", "单元测试", "集成测试"],
        "design": ["设计", "design", "ui设计", "ux", "原型", "figma", "sketch"],
        "docs": ["文档", "docs", "documentation", "readme", "wiki"],
        "security": ["安全", "security", "认证", "授权", "加密", "jwt", "oauth"],
        "performance": ["性能", "performance", "优化", "缓存", "redis", "cdn"],
        "ai": ["ai", "人工智能", "机器学习", "ml", "模型", "算法", "gpt", "llm"],
    }

    def __init__(self):
        self._weekday_names_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        self._weekday_names_en = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    async def parse_task_description(
        self,
        text: str,
        db: Optional[AsyncSession] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        解析自然语言任务描述，提取结构化信息
        
        Args:
            text: 自然语言描述
            db: 数据库会话（用于用户模糊匹配）
            project_id: 项目ID（用于限定用户查询范围）
            
        Returns:
            dict: 解析结果，包含name, description, due_date, priority, assignee, labels, estimated_hours等
        """
        if not text or not text.strip():
            raise ValueError("任务描述不能为空")

        # 先使用GPT-4进行主要解析
        parsed = await self._gpt_parse(text)

        # 后处理：解析相对日期
        if parsed.get("due_date"):
            parsed["due_date"] = self._parse_relative_date(parsed["due_date"])

        # 后处理：模糊匹配用户
        assignee_name = parsed.get("assignee")
        if assignee_name and db:
            matched_user = await self._fuzzy_match_user(db, assignee_name, project_id)
            if matched_user:
                parsed["assignee_id"] = matched_user["id"]
                parsed["assignee"] = matched_user["full_name"] or matched_user["username"]
            else:
                parsed["assignee_id"] = None
        else:
            parsed["assignee_id"] = None

        # 后处理：提取标签
        if not parsed.get("labels"):
            parsed["labels"] = self._extract_labels(text)

        # 后处理：标准化优先级
        if parsed.get("priority"):
            parsed["priority"] = self._normalize_priority(parsed["priority"])
        else:
            parsed["priority"] = 3  # 默认中优先级

        # 后处理：预估工时
        if parsed.get("estimated_hours") is None:
            parsed["estimated_hours"] = 0

        # 确保字段完整
        result = {
            "name": parsed.get("name", ""),
            "description": parsed.get("description", ""),
            "due_date": parsed.get("due_date"),
            "priority": parsed["priority"],
            "assignee": parsed.get("assignee"),
            "assignee_id": parsed.get("assignee_id"),
            "labels": parsed["labels"],
            "estimated_hours": parsed["estimated_hours"],
            "confidence": parsed.get("confidence", 0.8),
        }

        return result

    async def _gpt_parse(self, text: str) -> Dict[str, Any]:
        """使用GPT-4解析自然语言描述"""
        system_prompt = """你是一个专业的项目管理AI助手。你的任务是从用户的自然语言描述中提取结构化任务信息。

请提取以下字段（JSON格式）：
- name: 任务名称（简洁明了，去除时间、负责人等修饰语）
- description: 任务描述（保留核心内容）
- due_date: 截止日期（保持原始描述，如"下周三"、"明天"、"3天后"，后续会解析）
- priority: 优先级（high/medium/low 或 高/中/低）
- assignee: 负责人姓名
- labels: 标签数组（如["frontend", "backend"]）
- estimated_hours: 预估工时（数字，单位小时）
- confidence: 解析置信度（0-1）

规则：
1. 如果某个字段无法从文本中推断，使用null
2. 支持中英文输入
3. 日期保持原始文本描述，不要转换为具体日期
4. 任务名称应该简洁，去掉"让张三完成"、"下周三之前"等修饰语
5. 预估工时如果提到"天"，按1天=8小时转换

示例输入："下周三之前让张三完成登录页面的前端开发，优先级高，预计8小时"
示例输出：
{
  "name": "登录页面前端开发",
  "description": "完成登录页面的前端开发工作",
  "due_date": "下周三",
  "priority": "high",
  "assignee": "张三",
  "labels": ["frontend"],
  "estimated_hours": 8,
  "confidence": 0.95
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请解析以下任务描述：\n\n{text}"},
        ]

        try:
            response = await ai_engine.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
            )

            # 提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return parsed
            else:
                # 如果GPT没有返回JSON，尝试直接解析
                return self._fallback_parse(text)
        except Exception:
            return self._fallback_parse(text)

    def _fallback_parse(self, text: str) -> Dict[str, Any]:
        """当GPT解析失败时的降级解析"""
        result = {
            "name": text[:50],
            "description": text,
            "due_date": None,
            "priority": "medium",
            "assignee": None,
            "labels": [],
            "estimated_hours": 0,
            "confidence": 0.3,
        }

        # 提取人名（中文）
        name_match = re.search(r'让([\u4e00-\u9fa5]{2,4})(?:完成|做|负责)', text)
        if name_match:
            result["assignee"] = name_match.group(1)

        # 提取日期关键词
        date_patterns = [
            r'(下周[一二三四五六日])',
            r'(明天)',
            r'(后天)',
            r'(\d+)天后',
            r'(本?周[一二三四五六日])',
            r'(\d{4}-\d{2}-\d{2})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                result["due_date"] = match.group(1)
                break

        # 提取优先级
        if re.search(r'优先级高|高优先级|紧急|priority high', text, re.I):
            result["priority"] = "high"
        elif re.search(r'优先级低|低优先级|priority low', text, re.I):
            result["priority"] = "low"

        # 提取工时
        hour_match = re.search(r'(\d+)(?:个)?小时', text)
        if hour_match:
            result["estimated_hours"] = int(hour_match.group(1))
        else:
            day_match = re.search(r'(\d+)(?:个)?天', text)
            if day_match:
                result["estimated_hours"] = int(day_match.group(1)) * 8

        # 提取标签
        result["labels"] = self._extract_labels(text)

        return result

    def _parse_relative_date(self, date_text: Optional[str]) -> Optional[str]:
        """
        解析相对日期为ISO格式日期字符串
        
        支持：
        - 明天、后天
        - 下周三、本周五
        - 3天后、一周后
        - 2024-06-01（直接返回）
        """
        if not date_text:
            return None

        date_text = date_text.strip().lower()
        today = datetime.now().date()

        # 已经是ISO格式
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_text):
            return date_text

        # 明天
        if date_text in ("明天", "tomorrow", "明日"):
            return (today + timedelta(days=1)).isoformat()

        # 后天
        if date_text in ("后天", "day after tomorrow", "明后天"):
            return (today + timedelta(days=2)).isoformat()

        # 今天
        if date_text in ("今天", "today", "今日"):
            return today.isoformat()

        # N天后
        days_later_match = re.match(r'(\d+)\s*天后?', date_text)
        if days_later_match:
            days = int(days_later_match.group(1))
            return (today + timedelta(days=days)).isoformat()

        # N周后
        weeks_later_match = re.match(r'(\d+)\s*周?后?', date_text)
        if weeks_later_match:
            weeks = int(weeks_later_match.group(1))
            return (today + timedelta(weeks=weeks)).isoformat()

        # 下周X / 本周X
        weekday_map = {
            "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
            "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        }

        week_prefix = None
        if date_text.startswith("下周") or date_text.startswith("next week"):
            week_prefix = 1
            weekday_str = date_text[2:].strip()
        elif date_text.startswith("本周") or date_text.startswith("this week"):
            week_prefix = 0
            weekday_str = date_text[2:].strip()
        elif date_text.startswith("下") and len(date_text) >= 3:
            week_prefix = 1
            weekday_str = date_text[1:].strip()
        else:
            weekday_str = date_text

        target_weekday = None
        for key, val in weekday_map.items():
            if key in weekday_str:
                target_weekday = val
                break

        if target_weekday is not None:
            current_weekday = today.weekday()
            if week_prefix == 1:
                # 下周
                days_until = (7 - current_weekday) + target_weekday
            elif week_prefix == 0:
                # 本周
                days_until = target_weekday - current_weekday
                if days_until < 0:
                    days_until += 7
            else:
                # 默认本周，如果已过则下周
                days_until = target_weekday - current_weekday
                if days_until <= 0:
                    days_until += 7
            return (today + timedelta(days=days_until)).isoformat()

        # 无法解析，返回原始文本
        return None

    async def _fuzzy_match_user(
        self,
        db: AsyncSession,
        name: str,
        project_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        从数据库中模糊匹配用户
        
        优先匹配：
        1. full_name 完全匹配
        2. username 完全匹配
        3. full_name 包含匹配
        """
        if not name:
            return None

        # 构建查询
        query = select(User).where(User.is_active == True)

        # 先尝试精确匹配 full_name
        result = await db.execute(
            query.where(func.lower(User.full_name) == name.lower())
        )
        user = result.scalar_one_or_none()
        if user:
            return {"id": user.id, "full_name": user.full_name, "username": user.username}

        # 精确匹配 username
        result = await db.execute(
            query.where(func.lower(User.username) == name.lower())
        )
        user = result.scalar_one_or_none()
        if user:
            return {"id": user.id, "full_name": user.full_name, "username": user.username}

        # 模糊匹配 full_name（包含）
        result = await db.execute(
            query.where(User.full_name.ilike(f"%{name}%"))
        )
        user = result.scalar_one_or_none()
        if user:
            return {"id": user.id, "full_name": user.full_name, "username": user.username}

        # 模糊匹配 username
        result = await db.execute(
            query.where(User.username.ilike(f"%{name}%"))
        )
        user = result.scalar_one_or_none()
        if user:
            return {"id": user.id, "full_name": user.full_name, "username": user.username}

        return None

    def _extract_labels(self, text: str) -> List[str]:
        """从文本中提取标签"""
        text_lower = text.lower()
        labels = []
        for label, keywords in self.LABEL_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    labels.append(label)
                    break
        return labels

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


# 全局解析器实例
nlp_task_parser = NLPTaskParser()
