from fastapi import APIRouter
from typing import Dict, Any, List

router = APIRouter(prefix='', tags=['i18n'])

TRANSLATIONS = {
    'process_groups': {
        'zh': {'启动': '启动', '规划': '规划', '执行': '执行', '监控': '监控', '收尾': '收尾'},
        'en': {'启动': 'Initiating', '规划': 'Planning', '执行': 'Executing', '监控': 'Monitoring & Controlling', '收尾': 'Closing'}
    },
    'knowledge_areas': {
        'zh': {'整合': '整合管理', '范围': '范围管理', '进度': '进度管理', '成本': '成本管理', '质量': '质量管理', '资源': '资源管理', '沟通': '沟通管理', '风险': '风险管理', '采购': '采购管理', '相关方': '相关方管理'},
        'en': {'整合': 'Integration', '范围': 'Scope', '进度': 'Schedule', '成本': 'Cost', '质量': 'Quality', '资源': 'Resource', '沟通': 'Communication', '风险': 'Risk', '采购': 'Procurement', '相关方': 'Stakeholder'}
    }
}

@router.get('/process-groups')
async def get_process_groups(lang: str = 'zh'):
    return TRANSLATIONS['process_groups'].get(lang, TRANSLATIONS['process_groups']['zh'])

@router.get('/knowledge-areas')
async def get_knowledge_areas(lang: str = 'zh'):
    return TRANSLATIONS['knowledge_areas'].get(lang, TRANSLATIONS['knowledge_areas']['zh'])

@router.post('/agents/localize')
async def localize_agents(agents: List[Dict[str, Any]], lang: str = 'zh'):
    pg_map = TRANSLATIONS['process_groups'].get(lang, TRANSLATIONS['process_groups']['zh'])
    ka_map = TRANSLATIONS['knowledge_areas'].get(lang, TRANSLATIONS['knowledge_areas']['zh'])
    result = []
    for agent in agents:
        localized = agent.copy()
        if agent.get('process_group') in pg_map:
            localized['process_group'] = pg_map[agent['process_group']]
        if agent.get('knowledge_area') in ka_map:
            localized['knowledge_area'] = ka_map[agent['knowledge_area']]
        if lang == 'en' and agent.get('name_en'):
            localized['name'] = agent['name_en']
        else:
            localized['name'] = agent.get('name_cn') or agent.get('name') or agent.get('id', '')
        result.append(localized)
    return result
