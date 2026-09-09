"""
Agent注册中心 - 管理所有Agent生命周期
支持动态加载、查询、注册
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent注册中心"""
    
    def __init__(self):
        self.agents: Dict[str, dict] = {}
        self.stats = {
            'total': 0,
            'by_domain': {},
            'by_process': {},
            'last_updated': None
        }
        self._initialize()
    
    def _initialize(self):
        """初始化注册表"""
        # 从v2 Agent库加载
        self._load_from_library()
        logger.info(f'Agent注册中心已初始化，共 {self.stats["total"]} 个Agent')
    
    def _load_from_library(self):
        """从v2 Agent库加载"""
        library_path = Path('/opt/aipm-install/backend/data/agent_library_v2/pmbok_agents_v2.json')
        
        if not library_path.exists():
            logger.warning(f'Agent库文件不存在: {library_path}')
            return
            
        with open(library_path, 'r', encoding='utf-8') as f:
            library = json.load(f)
            
        for agent in library.get('agents', []):
            self.register(agent)
            
        self.stats['last_updated'] = datetime.now().isoformat()
    
    def register(self, agent_config: dict) -> bool:
        """注册新Agent"""
        agent_id = agent_config.get('id')
        if not agent_id:
            logger.error('Agent配置缺少id字段')
            return False
            
        self.agents[agent_id] = {
            'config': agent_config,
            'registered_at': datetime.now().isoformat(),
            'status': 'active'
        }
        
        # 更新统计
        self.stats['total'] = len(self.agents)
        
        domain = agent_config.get('domain', 'unknown')
        self.stats['by_domain'][domain] = self.stats['by_domain'].get(domain, 0) + 1
        
        process = agent_config.get('pmbok_process', 'unknown')
        self.stats['by_process'][process] = self.stats['by_process'].get(process, 0) + 1
        
        logger.debug(f'已注册Agent: {agent_id}')
        return True
    
    def unregister(self, agent_id: str) -> bool:
        """注销Agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            self.stats['total'] = len(self.agents)
            return True
        return False
    
    def get(self, agent_id: str) -> Optional[dict]:
        """获取Agent配置"""
        entry = self.agents.get(agent_id)
        if entry:
            return entry['config']
        return None
    
    def list_all(self) -> List[dict]:
        """列出所有Agent"""
        result = []
        for entry in self.agents.values():
            agent = entry.get('config', {})
            if not agent:
                continue
            result.append({
                'id': agent.get('id', ''),
                'name': agent.get('name', ''),
                'name_en': agent.get('name_en', ''),
                'domain': agent.get('domain', ''),
                'pmbok_process': agent.get('pmbok_process', ''),
                'type': agent.get('type', 'tool_agent'),
                'description': agent.get('description', ''),
                'templates': agent.get('templates'),
                'inputs': agent.get('inputs', []),
                'outputs': agent.get('outputs', []),
                'tools': agent.get('tools', []),
                'metadata': agent.get('metadata', {})
            })
        return result
    
    def search(self, keyword: str) -> List[dict]:
        """搜索Agent"""
        keyword = keyword.lower()
        return [
            {
                'id': a['id'],
                'name': a['name'],
                'description': a.get('description', ''),
                'domain': a['domain']
            }
            for a in self.list_all()
            if keyword in a['id'].lower() or 
               keyword in a['name'].lower() or
               keyword in a.get('description', '').lower()
        ]
    
    def get_stats(self) -> dict:
        """获取注册统计"""
        return {
            **self.stats,
            'agents': self.list_all()
        }


# 全局注册中心实例
_registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    """获取注册中心实例"""
    return _registry


def get_all_agents() -> List[dict]:
    """获取所有Agent列表"""
    return _registry.list_all()


def get_agent_stats() -> dict:
    """获取Agent统计"""
    return _registry.get_stats()


# 向后兼容函数
def list_agents(source: str = None) -> List[dict]:
    agents = get_all_agents()
    if source == "domain":
        grouped = {}
        for a in agents:
            domain = a.get("domain", "unknown")
            if domain not in grouped:
                grouped[domain] = []
            grouped[domain].append(a)
        result = []
        for domain, agents_list in grouped.items():
            for a in agents_list:
                result.append({**a, "source": domain})
        return result
    return agents

def list_agents_grouped() -> dict:
    agents = get_all_agents()
    grouped = {}
    for a in agents:
        domain = a.get('domain', 'unknown')
        if domain not in grouped:
            grouped[domain] = []
        grouped[domain].append(a)
    return grouped

def list_domain_ids() -> List[str]:
    return list(get_agent_stats()['by_domain'].keys())

async def run_agent(agent_id: str, inputs: dict = None, context: dict = None) -> dict:
    return await execute_agent(agent_id, inputs or {}, context)

def get_structured_itto(agent_id: str) -> dict:
    agent = get_registry().get(agent_id)
    if not agent:
        return {}
    return {
        'inputs': agent.get('inputs', []),
        'tools': agent.get('tools', []),
        'outputs': agent.get('outputs', [])
    }

def normalize_agent_id(agent_id: str) -> str:
    return agent_id

def candidate_override_keys(agent_id: str) -> List[str]:
    return []

from app.services.ai.agent_engine_v2 import execute_agent
