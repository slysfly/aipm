"""
通维AI项目管理系统 - Agent工厂系统
支持动态Agent注册、发现和实例化
基于PMBOK 128个工具技术构建专业Agent
"""

import uuid
import logging
from typing import Dict, Any, List, Optional, Type
from datetime import datetime
from dataclasses import dataclass, field
import json
import os

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    """Agent定义"""
    id: str
    name: str
    name_en: str
    role: str
    description: str
    tools: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    category: str = "general"
    pmbok_processes: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentFactory:
    """Agent工厂类"""

    def __init__(self):
        self._agents: Dict[str, AgentDefinition] = {}
        self._agent_classes: Dict[str, Dict[str, Any]] = {}
        self._register_agent_type("Planner", "planner", "规划Agent", ["expert_judgment", "analysis", "synthesis"])
        self._register_agent_type("Executor", "executor", "执行Agent", ["execution", "monitoring", "reporting"])
        self._register_agent_type("Reviewer", "reviewer", "审查Agent", ["quality_check", "validation", "recommendation"])
        self._register_agent_type("Coordinator", "coordinator", "协调Agent", ["coordination", "synchronization", "conflict_resolution"])
        self._load_pmbok_agents()

    def _register_agent_type(self, name, role, description, tools):
        """注册Agent类型"""
        self._agent_classes[name] = {
            "role": role,
            "description": description,
            "tools": tools,
            "category": "basic"
        }

    def _load_pmbok_agents(self):
        """从JSON文件加载PMBOK专业Agent配置"""
        agent_file = "/opt/AI-PM/backend/data/agent_library/pmbok_agents.json"
        if not os.path.exists(agent_file):
            logger.warning(f"PMBOK Agent库不存在: {agent_file}")
            return
        with open(agent_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for agent_cfg in data.get('agents', []):
            name = agent_cfg['name']
            self._agent_classes[name] = {
                "role": agent_cfg.get('role', 'specialist'),
                "description": agent_cfg.get('description', ''),
                "tools": agent_cfg.get('tools', []),
                "processes": agent_cfg.get('processes', []),
                "category": "pmbok"
            }
            logger.info(f"已加载PMBOK Agent: {name} ({len(agent_cfg.get('tools', []))}个工具)")

    def create_agent(self, agent_type, **kwargs):
        """创建Agent实例"""
        if agent_type not in self._agent_classes:
            logger.error(f"未知的Agent类型: {agent_type}")
            return None
        config = self._agent_classes[agent_type]
        agent_def = AgentDefinition(
            id=str(uuid.uuid4()),
            name=kwargs.get("name", agent_type),
            name_en=kwargs.get("name_en", config.get("description", agent_type)),
            role=config["role"],
            description=kwargs.get("description", config.get("description", "")),
            tools=config.get("tools", []),
            pmbok_processes=config.get("processes", []),
            category=kwargs.get("category", config.get("category", "general")),
            version=kwargs.get("version", "1.0.0"),
            metadata=kwargs.get("metadata", {})
        )
        self._agents[agent_def.id] = agent_def
        logger.info(f"Agent已创建: {agent_def.name} (ID: {agent_def.id})")
        return agent_def

    def get_agent(self, agent_id):
        """获取Agent定义"""
        return self._agents.get(agent_id)

    def list_agents(self):
        """列出所有已创建的Agent"""
        return list(self._agents.values())

    def list_agent_types(self):
        """列出所有可用的Agent类型"""
        return [
            {
                "name": name,
                "role": config["role"],
                "description": config["description"],
                "tool_count": len(config.get("tools", [])),
                "category": config.get("category", "basic")
            }
            for name, config in self._agent_classes.items()
        ]

    def list_agents_by_category(self, category):
        """按类别列出Agent"""
        return [a for a in self._agents.values() if a.category == category]

    def list_agents_by_role(self, role):
        """按角色列出Agent"""
        return [a for a in self._agents.values() if a.role == role]

    def create_team(self, team_name, agent_types):
        """创建Agent团队"""
        team = {
            "id": str(uuid.uuid4()),
            "name": team_name,
            "created_at": datetime.now().isoformat(),
            "agents": []
        }
        for agent_type in agent_types:
            agent = self.create_agent(agent_type)
            if agent:
                team["agents"].append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "role": agent.role,
                    "tools": agent.tools
                })
        logger.info(f"团队已创建: {team_name}, 包含 {len(team['agents'])} 个Agent")
        return team

    def to_dict(self):
        """序列化为字典"""
        return {
            "total_agents": len(self._agents),
            "agent_types": self.list_agent_types(),
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "description": a.description,
                    "tools": a.tools,
                    "category": a.category,
                    "version": a.version
                }
                for a in self._agents.values()
            ]
        }


# 全局工厂实例
_agent_factory = None


def get_agent_factory():
    """获取全局Agent工厂实例"""
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory()
    return _agent_factory


if __name__ == "__main__":
    factory = AgentFactory()
    print("Available Agent Types:")
    for at in factory.list_agent_types():
        print(f"  - {at['name']}: {at['description']} ({at['tool_count']} tools)")
    print(f"Total: {len(factory.list_agent_types())}")
