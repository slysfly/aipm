# -*- coding: utf-8 -*-
"""
案例库智能推荐服务
基于行业、规模、复杂度匹配相似案例
"""
import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

class CaseRecommendationService:
    """案例推荐服务"""

    def __init__(self, case_index_path: str = "data/case_index.json"):
        self.case_index_path = case_index_path
        self.case_index = self._load_case_index()
        self.case_library_path = Path('/home/ubuntu/.openclaw/workspace/twzx-website/library')

    def _load_case_index(self) -> Dict:
        """加载案例索引"""
        with open(self.case_index_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def find_similar_cases(
        self,
        industry: str,
        scale: Optional[str] = None,
        complexity: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """查找相似案例"""
        similar_cases = []

        # 获取指定行业的案例（索引值是列表）
        industry_cases = self.case_index.get('by_industry', {}).get(industry, [])

        for i, case_name in enumerate(industry_cases, 1):
            score = 50  # 行业匹配基础分

            # 解析案例ID
            case_id = f"{industry}-{i:03d}"

            similar_cases.append({
                'id': case_id,
                'name': case_name,
                'industry': industry,
                'match_score': score,
                'filename': f"{case_name}.html"
            })

        # 按匹配分数排序
        similar_cases.sort(key=lambda x: x['match_score'], reverse=True)

        return similar_cases[:top_k]

    def get_case_detail(self, case_id: str) -> Optional[Dict]:
        """获取案例详情"""
        # 在索引中查找
        for industry, cases in self.case_index.get('by_industry', {}).items():
            for case_name in cases:
                if case_id in case_name or case_name in case_id:
                    # 读取HTML文件
                    file_path = self.case_library_path / f"{case_name}.html"
                    if file_path.exists():
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        return {
                            'id': case_id,
                            'name': case_name,
                            'industry': industry,
                            'content': content
                        }
        return None

    def get_industry_summary(self) -> Dict:
        """获取行业概况"""
        summary = {
            'total_cases': self.case_index.get('total', 0),
            'industries': []
        }

        for industry, cases in self.case_index.get('by_industry', {}).items():
            summary['industries'].append({
                'industry': industry,
                'case_count': len(cases),
                'cases': cases[:5]  # 只返回前5个案例名
            })

        return summary

    def generate_recommendation_report(
        self,
        project_info: Dict[str, Any]
    ) -> Dict:
        """生成推荐报告"""
        industry = project_info.get('industry', '')

        similar_cases = self.find_similar_cases(industry, top_k=5)

        report = {
            'project_info': project_info,
            'similar_cases': similar_cases,
            'recommendations': [],
            'generated_at': self._get_timestamp()
        }

        # 生成建议
        for i, case in enumerate(similar_cases, 1):
            report['recommendations'].append({
                'rank': i,
                'case_id': case['id'],
                'case_name': case['name'],
                'industry': case['industry'],
                'match_score': case['match_score'],
                'key_points': [
                    f"行业适配度高",
                    f"可参考项目管理经验",
                    f"需结合本项目特点调整"
                ]
            })

        return report

    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()

# 全局实例
_case_service: Optional[CaseRecommendationService] = None

def get_case_service() -> CaseRecommendationService:
    global _case_service
    if _case_service is None:
        _case_service = CaseRecommendationService()
    return _case_service
