"""
AI-PM v2.0 Agent 引擎 - 工具即Agent架构
每个PMBOK工具技术都是独立的专家Agent
完全基于PMBOK 6th + 7th Edition标准
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)
AGENT_LIBRARY_V2 = Path('/opt/AI-PM/backend/data/agent_library_v2/pmbok_agents_v2.json')

class ToolAgent:
    def __init__(self, agent_id: str, config: dict):
        self.id = agent_id
        self.name = config.get('name', '')
        self.name_en = config.get('name_en', '')
        self.type = config.get('type', 'tool_agent')
        self.domain = config.get('domain', '')
        self.pmbok_process = config.get('pmbok_process', '')
        self.description = config.get('description', '')
        self.templates = config.get('templates', {})

    async def execute(self, inputs: dict, context: dict = None) -> dict:
        context = context or {}
        return {
            'success': True,
            'agent_id': self.id,
            'agent_name': self.name,
            'output': f'{self.name}的执行结果'
        }

class AgentFactory:
    def __init__(self):
        self.agents: Dict[str, ToolAgent] = {}
        self._load_agents()

    def _load_agents(self):
        if not AGENT_LIBRARY_V2.exists():
            logger.error(f'Agent库文件不存在: {AGENT_LIBRARY_V2}')
            return
        with open(AGENT_LIBRARY_V2, 'r', encoding='utf-8') as f:
            library = json.load(f)
        for agent_config in library.get('agents', []):
            agent_id = agent_config.get('id')
            if agent_id:
                self.agents[agent_id] = ToolAgent(agent_id, agent_config)
        logger.info(f'已加载 {len(self.agents)} 个Agent')

    def get_agent(self, agent_id: str) -> Optional[ToolAgent]:
        return self.agents.get(agent_id)

    def list_all_agents(self) -> List[dict]:
        return [{'id': a.id, 'name': a.name, 'domain': a.domain} for a in self.agents.values()]

_agent_factory = AgentFactory()

def get_agent_factory() -> AgentFactory:
    return _agent_factory

async def execute_agent(agent_id: str, inputs: dict, context: dict = None) -> dict:
    factory = get_agent_factory()
    agent = factory.get_agent(agent_id)
    if not agent:
        return {'success': False, 'error': f'Agent不存在: {agent_id}'}
    return await agent.execute(inputs, context)
