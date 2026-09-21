"""
工具技术API路由
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import json
import re
from pathlib import Path
import uuid
from app import paths

# [安全修复 Issue #11] 该路由此前零鉴权挂载在 /api/v1/tools 下，
# 攻击者无需任何凭证即可读取全量工具/Agent 目录，并可调用
# POST /tools/generate（写盘）与 POST /tools/agents/create（创建 Agent）。
# 现统一在路由级强制认证，覆盖该文件中全部端点（含后续新增端点）。
from app.core.security import get_current_active_user

router = APIRouter(
    prefix='/tools',
    tags=['工具技术'],
    dependencies=[Depends(get_current_active_user)],
)

class GenerateOutputRequest(BaseModel):
    tool_id: str
    data: Dict[str, Any]
    project_id: Optional[str] = None

@router.get('/catalog')
async def list_tool_catalog():
    from app.services.ai.tool_catalog import TOOL_CATALOG, list_tools
    tools = list_tools()
    return {
        'total': len(tools),
        'tools': [
            {
                'id': t.id,
                'name': t.name,
                'name_en': t.name_en,
                'category': t.category.value if hasattr(t.category, 'value') else str(t.category),
                'description': t.description,
                'input_types': t.input_types,
                'output_formats': t.output_formats,
                'processes': t.processes,
                'usage_notes': t.usage_notes
            }
            for t in tools
        ]
    }

@router.get('/categories')
async def get_tool_categories():
    from app.services.ai.tool_catalog import ToolCategory
    return {
        'categories': [
            {'id': c.value, 'name': c.value}
            for c in ToolCategory
        ]
    }

@router.get('/{tool_id}')
async def get_tool_detail(tool_id: str):
    from app.services.ai.tool_catalog import get_tool
    tool = get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail='工具不存在')
    return {
        'id': tool.id,
        'name': tool.name,
        'name_en': tool.name_en,
        'category': tool.category.value if hasattr(tool.category, 'value') else str(tool.category),
        'description': tool.description,
        'input_types': tool.input_types,
        'output_formats': tool.output_formats,
        'processes': tool.processes,
        'usage_notes': tool.usage_notes,
        'template': tool.results_template.__dict__
    }

@router.post('/generate')
async def generate_tool_output(req: GenerateOutputRequest):
    from app.services.ai.tool_catalog import get_tool, generate_tool_output
    tool = get_tool(req.tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail='工具不存在')
    output = generate_tool_output(req.tool_id, req.data)
    pid = req.project_id or '_global'
    # [评审修复] project_id 为客户端可控分段，直接拼入 data_path 并 mkdir/write，
    # 白名单校验防止 '../..' 等穿越写盘（paths.data_path 另有兜底拦截，双保险）
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', pid):
        raise HTTPException(status_code=400, detail='project_id 含非法字符')
    ref = uuid.uuid4().hex[:12]
    output_path = paths.data_path('tool_outputs', pid, f'{ref}.md')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding='utf-8')
    return {
        'success': True,
        'tool_id': req.tool_id,
        'tool_name': tool.name,
        'ref': ref,
        'output': output,
        'download_url': f'/api/v1/tools/output/{ref}'
    }

@router.get('/output/{ref}')
async def get_tool_output(ref: str):
    # [评审修复] ref 直接进入 glob 模式，'*' 等通配符可命中任意 .md——先做格式白名单
    if not re.fullmatch(r'[0-9a-f]{12}', ref):
        raise HTTPException(status_code=404, detail='输出不存在')
    base_path = paths.data_path('tool_outputs')
    for pid_dir in base_path.iterdir() if base_path.exists() else []:
        if pid_dir.is_dir():
            for f in pid_dir.glob(f'{ref}.md'):
                return {'content': f.read_text(encoding='utf-8')}
    raise HTTPException(status_code=404, detail='输出不存在')

@router.get('/process/{process_id}/tools')
async def get_process_tools(process_id: str):
    from app.services.ai.tool_catalog import get_tools_for_process
    tools = get_tools_for_process(process_id)
    return {
        'process_id': process_id,
        'tools': [
            {
                'id': t.id,
                'name': t.name,
                'name_en': t.name_en,
                'category': t.category.value if hasattr(t.category, 'value') else str(t.category),
                'description': t.description
            }
            for t in tools
        ]
    }

@router.get('/process/{process_id}/output')
async def get_process_tool_output(process_id: str, tool_id: str = None):
    from app.services.ai.tool_catalog import get_tools_for_process
    tools = get_tools_for_process(process_id)
    result = []
    for tool in tools:
        if tool_id and tool.id != tool_id:
            continue
        template = tool.results_template
        result.append({
            'tool_id': tool.id,
            'tool_name': tool.name,
            'tool_name_en': tool.name_en,
            'template': template.example if template else None
        })
    return {'process_id': process_id, 'tools': result}

@router.get('/agents/types')
async def list_agent_types():
    from app.services.ai.agent_factory import get_agent_factory
    factory = get_agent_factory()
    return {
        'total': len(factory.list_agent_types()),
        'agent_types': factory.list_agent_types()
    }

@router.post('/agents/create')
async def create_agent(req: dict):
    from app.services.ai.agent_factory import get_agent_factory
    factory = get_agent_factory()
    agent = factory.create_agent(
        agent_type=req.get('agent_type'),
        name=req.get('name'),
        description=req.get('description')
    )
    if agent:
        return {
            'success': True,
            'agent': {
                'id': agent.id,
                'name': agent.name,
                'role': agent.role,
                'tools': agent.tools,
                'category': agent.category
            }
        }
    return {'success': False, 'error': 'Agent创建失败'}

@router.get('/agents')
async def list_agents():
    from app.services.ai.agent_factory import get_agent_factory
    factory = get_agent_factory()
    return {
        'total': len(factory.list_agents()),
        'agents': [
            {
                'id': a.id,
                'name': a.name,
                'role': a.role,
                'description': a.description,
                'tools': a.tools,
                'category': a.category
            }
            for a in factory.list_agents()
        ]
    }

@router.get('/agents/v2/list')
async def list_agents_v2():
    from app.services.ai.agent_registry import get_all_agents
    agents = get_all_agents()
    return {
        'success': True,
        'total': len(agents),
        'agents': agents
    }

@router.get('/agents/v2/stats')
async def agent_stats_v2():
    from app.services.ai.agent_registry import get_agent_stats
    stats = get_agent_stats()
    return {
        'success': True,
        'data': stats
    }
