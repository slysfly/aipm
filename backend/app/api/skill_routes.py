from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
import json
import os
import sqlite3
from datetime import datetime

router = APIRouter(tags=['Skills管理'])

SKILLS_FILE = '/opt/aipm-install/backend/data/skills/pmbok_skills_v1.json'
DB_FILE = '/opt/aipm-install/backend/test.db'

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@router.get('/')
async def list_skills(
    domain: Optional[str] = None,
    process_group: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    try:
        if not os.path.exists(SKILLS_FILE):
            return []
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        if domain:
            skills = [s for s in skills if s.get('domain') == domain]
        if process_group:
            skills = [s for s in skills if s.get('process_group') == process_group]
        if search:
            search_lower = search.lower()
            skills = [s for s in skills if 
                     search_lower in s.get('name', '').lower() or
                     search_lower in s.get('description', '').lower() or
                     search_lower in s.get('name_en', '').lower()]
        return skills[offset:offset+limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/stats')
async def get_skill_stats():
    try:
        if not os.path.exists(SKILLS_FILE):
            return {'total': 0}
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        by_group = {}
        by_domain = {}
        by_difficulty = {}
        for skill in skills:
            group = skill.get('process_group', '未知')
            domain = skill.get('domain', '未知')
            difficulty = skill.get('metadata', {}).get('difficulty', '未知')
            by_group[group] = by_group.get(group, 0) + 1
            by_domain[domain] = by_domain.get(domain, 0) + 1
            by_difficulty[difficulty] = by_difficulty.get(difficulty, 0) + 1
        return {
            'total': len(skills),
            'by_group': by_group,
            'by_domain': by_domain,
            'by_difficulty': by_difficulty,
            'version': data.get('version', '1.0'),
            'source': data.get('source', ''),
            'created_at': data.get('created_at', ''),
            'updated_at': data.get('updated_at', '')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/groups')
async def get_process_groups():
    try:
        if not os.path.exists(SKILLS_FILE):
            return []
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        groups = list(set([s.get('process_group', '未知') for s in skills]))
        return sorted(groups)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/detail/{skill_id}')
async def get_skill(skill_id: str):
    try:
        if not os.path.exists(SKILLS_FILE):
            raise HTTPException(status_code=404, detail='Skill文件不存在')
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        skill = next((s for s in skills if s.get('id') == skill_id), None)
        if not skill:
            raise HTTPException(status_code=404, detail='Skill不存在')
        return skill
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/')
async def create_skill(skill: dict):
    try:
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        if any(s['id'] == skill.get('id') for s in skills):
            raise HTTPException(status_code=400, detail='Skill ID已存在')
        skill['id'] = f"skill:{skill.get('domain', 'pmbok')}:{skill.get('pmbok_process', datetime.now().strftime('%Y%m%d%H%M%S'))}"
        skill['created_at'] = datetime.utcnow().isoformat()
        skill['updated_at'] = datetime.utcnow().isoformat()
        skills.append(skill)
        data['skills'] = skills
        data['total'] = len(skills)
        with open(SKILLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return skill
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put('/{skill_id}')
async def update_skill(skill_id: str, skill_update: dict):
    try:
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        for i, s in enumerate(skills):
            if s.get('id') == skill_id:
                skills[i].update(skill_update)
                skills[i]['updated_at'] = datetime.utcnow().isoformat()
                break
        else:
            raise HTTPException(status_code=404, detail='Skill不存在')
        data['skills'] = skills
        with open(SKILLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return skills[i]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete('/{skill_id}')
async def delete_skill(skill_id: str):
    try:
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        skills = data.get('skills', [])
        new_skills = [s for s in skills if s.get('id') != skill_id]
        if len(new_skills) == len(skills):
            raise HTTPException(status_code=404, detail='Skill不存在')
        data['skills'] = new_skills
        data['total'] = len(new_skills)
        with open(SKILLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {'message': 'Skill已删除', 'remaining': len(new_skills)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/{skill_id}/agents')
async def get_agents_by_skill(skill_id: str):
    try:
        with open(SKILLS_FILE, 'r', encoding='utf-8') as f:
            skills_data = json.load(f)
        skill = next((s for s in skills_data.get('skills', []) if s.get('id') == skill_id), None)
        if not skill:
            raise HTTPException(status_code=404, detail='Skill不存在')
        agents_file = '/opt/aipm-install/backend/data/agent_library_v2/pmbok_agents_v2.json'
        with open(agents_file, 'r', encoding='utf-8') as f:
            agents_data = json.load(f)
        agents = [
            {'id': a['id'], 'name': a['name'], 'domain': a.get('domain'), 
             'pmbok_process': a.get('pmbok_process')}
            for a in agents_data.get('agents', [])
            if skill_id in a.get('skills_needed', [])
        ]
        return {
            'skill_id': skill_id,
            'skill_name': skill.get('name'),
            'agents': agents,
            'count': len(agents)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
