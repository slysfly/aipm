"""
PMI中国AI项目管理社区 - 甘特图算法服务
实现 EVM 挣值管理计算、WBS 工作分解结构生成等核心算法。

（关键路径 / CPM 相关逻辑已拆分至 app.services.cpm 模块；
 为保持向后兼容，此处重新导出 TaskNode / Dependency / GanttAlgorithmService。）
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
import random
import math

from app.services.cpm import TaskNode, Dependency, GanttAlgorithmService


class EVMCalculationService:
    """EVM挣值管理计算服务"""
    
    @staticmethod
    def calculate_evm_metrics(
        tasks: List[Dict],
        current_date: datetime = None
    ) -> Dict:
        """
        计算EVM指标
        
        Args:
            tasks: 任务列表
            current_date: 当前日期
            
        Returns:
            metrics: EVM指标字典
        """
        if current_date is None:
            current_date = datetime.now()
        
        # 计算总计划值 (PV)
        total_pv = sum(task.get('planned_value', 0) for task in tasks)
        
        # 计算总挣值 (EV)
        total_ev = 0
        for task in tasks:
            progress = task.get('progress', 0) / 100
            pv = task.get('planned_value', 0)
            total_ev += pv * progress
        
        # 计算总实际成本 (AC)
        total_ac = sum(task.get('actual_cost', 0) for task in tasks)
        
        # 计算偏差
        cv = total_ev - total_ac  # 成本偏差
        sv = total_ev - total_pv  # 进度偏差
        
        # 计算绩效指数
        cpi = total_ev / total_ac if total_ac > 0 else 0  # 成本绩效指数
        spi = total_ev / total_pv if total_pv > 0 else 0  # 进度绩效指数
        
        # 完工估算 (EAC)
        budget_at_completion = total_pv
        
        # 方法1: 基于当前CPI预测
        eac_method1 = budget_at_completion / cpi if cpi > 0 else budget_at_completion
        
        # 方法2: 基于当前SPI和CPI预测
        eac_method2 = budget_at_completion / (cpi * spi) if (cpi > 0 and spi > 0) else budget_at_completion
        
        # 方法3: 基于剩余工作预测
        etc = (budget_at_completion - total_ev) / cpi if cpi > 0 else (budget_at_completion - total_ev)
        eac_method3 = total_ac + etc
        
        # 选择最合适的预测方法
        if cpi >= 0.95 and spi >= 0.95:
            eac = eac_method1
        elif cpi < 0.95 and spi < 0.95:
            eac = eac_method2
        else:
            eac = eac_method3
        
        # 完工尚需估算 (ETC)
        etc = eac - total_ac
        
        # 完工偏差 (VAC)
        vac = budget_at_completion - eac
        
        # 完工绩效指数 (TCPI)
        tpci = budget_at_completion / eac if eac > 0 else 0
        
        return {
            'planned_value': total_pv,
            'earned_value': total_ev,
            'actual_cost': total_ac,
            'cost_variance': cv,
            'schedule_variance': sv,
            'cost_performance_index': cpi,
            'schedule_performance_index': spi,
            'estimate_at_completion': eac,
            'estimate_to_complete': etc,
            'variance_at_completion': vac,
            'to_complete_performance_index': tpci,
            'budget_at_completion': budget_at_completion,
            'forecast_method': 'cpi_based' if cpi >= 0.95 else 'spi_cpi_based' if cpi < 0.95 and spi < 0.95 else 'remaining_work'
        }
    
    @staticmethod
    def monte_carlo_simulation(
        task_durations: List[Dict],
        iterations: int = 10000
    ) -> Dict:
        """
        蒙特卡洛模拟
        
        Args:
            task_durations: 任务工期列表，每个包含mean, std_dev, distribution
            iterations: 模拟次数
            
        Returns:
            results: 模拟结果
        """
        results = []

        for _ in range(iterations):
            total_duration = 0

            for task in task_durations:
                mean = task.get('mean', 1)
                std_dev = task.get('std_dev', 0)
                dist_type = task.get('distribution', 'normal')

                if dist_type == 'normal':
                    duration = random.gauss(mean, std_dev) if std_dev > 0 else mean
                elif dist_type == 'triangular':
                    low = mean - std_dev * 2
                    high = mean + std_dev * 2
                    duration = random.triangular(low, high, mean)
                elif dist_type == 'uniform':
                    duration = random.uniform(mean - std_dev, mean + std_dev)
                else:
                    duration = mean

                total_duration += max(0, duration)

            results.append(total_duration)

        results.sort()
        n = len(results)
        mean_val = sum(results) / n

        def _percentile(p: float) -> float:
            if n == 1:
                return float(results[0])
            k = (n - 1) * p / 100.0
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return float(results[int(k)])
            return float(results[f] * (c - k) + results[c] * (k - f))

        # 直方图（20 个桶）
        hist_counts = [0] * 20
        if n > 0:
            lo, hi = results[0], results[-1]
            span = (hi - lo) or 1.0
            for v in results:
                idx = int((v - lo) / span * 19)
                idx = max(0, min(19, idx))
                hist_counts[idx] += 1

        return {
            'mean': float(mean_val),
            'median': float(_percentile(50)),
            'std_dev': float(math.sqrt(sum((x - mean_val) ** 2 for x in results) / n)),
            'min': float(results[0]),
            'max': float(results[-1]),
            'percentile_5': float(_percentile(5)),
            'percentile_10': float(_percentile(10)),
            'percentile_25': float(_percentile(25)),
            'percentile_50': float(_percentile(50)),
            'percentile_75': float(_percentile(75)),
            'percentile_90': float(_percentile(90)),
            'percentile_95': float(_percentile(95)),
            'prob_overdue_7': float(sum(1 for x in results if x > mean_val + 7) / n),
            'prob_overdue_14': float(sum(1 for x in results if x > mean_val + 14) / n),
            'histogram': (hist_counts, 20),
        }


class WBSGeneratorService:
    """WBS工作分解结构生成服务"""
    
    @staticmethod
    def generate_wbs(
        project_name: str,
        project_type: str = "it_software",
        constraints: Dict = None
    ) -> List[Dict]:
        """
        生成WBS结构
        
        Args:
            project_name: 项目名称
            project_type: 项目类型
            constraints: 约束条件
            
        Returns:
            wbs: WBS结构列表
        """
        templates = {
            'it_software': [
                {
                    'code': '1',
                    'name': '需求分析',
                    'tasks': ['业务调研', '需求访谈', '需求规格说明书', '需求评审']
                },
                {
                    'code': '2',
                    'name': '系统设计',
                    'tasks': ['架构设计', '数据库设计', '接口设计', '详细设计', '设计评审']
                },
                {
                    'code': '3',
                    'name': '开发',
                    'tasks': ['前端开发', '后端开发', '数据库开发', '接口开发', '单元测试']
                },
                {
                    'code': '4',
                    'name': '集成测试',
                    'tasks': ['集成测试', '系统测试', '性能测试', '安全测试']
                },
                {
                    'code': '5',
                    'name': '部署上线',
                    'tasks': ['部署准备', '数据迁移', '上线发布', '验收测试']
                },
                {
                    'code': '6',
                    'name': '项目管理',
                    'tasks': ['项目启动', '进度管理', '质量管理', '风险管理', '项目收尾']
                }
            ],
            'construction': [
                {
                    'code': '1',
                    'name': '项目准备',
                    'tasks': ['场地平整', '临时设施', '图纸会审']
                },
                {
                    'code': '2',
                    'name': '基础工程',
                    'tasks': ['土方开挖', '地基处理', '基础施工', '基础验收']
                },
                {
                    'code': '3',
                    'name': '主体工程',
                    'tasks': ['结构施工', '防水工程', '装饰工程']
                },
                {
                    'code': '4',
                    'name': '机电安装',
                    'tasks': ['电气安装', '给排水', '暖通空调', '消防系统']
                },
                {
                    'code': '5',
                    'name': '竣工验收',
                    'tasks': ['分项验收', '竣工验收', '交付使用']
                }
            ],
            'consulting': [
                {
                    'code': '1',
                    'name': '项目启动',
                    'tasks': ['合同签订', '项目启动会', '团队组建']
                },
                {
                    'code': '2',
                    'name': '调研分析',
                    'tasks': ['现状调研', '数据分析', '问题诊断']
                },
                {
                    'code': '3',
                    'name': '方案设计',
                    'tasks': ['方案设计', '方案评审', '方案定稿']
                },
                {
                    'code': '4',
                    'name': '实施支持',
                    'tasks': ['实施指导', '培训', '效果评估']
                },
                {
                    'code': '5',
                    'name': '项目收尾',
                    'tasks': ['成果汇报', '项目验收', '知识沉淀']
                }
            ]
        }
        
        template = templates.get(project_type, templates['it_software'])
        
        wbs = []
        wbs_code_counter = {}
        
        for phase in template:
            phase_code = phase['code']
            wbs_code_counter[phase_code] = 0
            
            for task_name in phase['tasks']:
                wbs_code_counter[phase_code] += 1
                task_code = f"{phase_code}.{wbs_code_counter[phase_code]}"
                
                wbs.append({
                    'wbs_code': task_code,
                    'name': task_name,
                    'level': 2,
                    'phase': phase['name'],
                    'duration_days': WBSGeneratorService._estimate_duration(task_name, project_type),
                    'skills_required': WBSGeneratorService._estimate_skills(task_name)
                })
        
        return wbs
    
    @staticmethod
    def _estimate_duration(task_name: str, project_type: str) -> int:
        """估算任务工期"""
        duration_map = {
            '业务调研': 10,
            '需求访谈': 5,
            '需求规格说明书': 7,
            '需求评审': 2,
            '架构设计': 10,
            '数据库设计': 7,
            '详细设计': 5,
            '设计评审': 2,
            '前端开发': 30,
            '后端开发': 30,
            '单元测试': 10,
            '集成测试': 15,
            '系统测试': 10,
            '部署上线': 5,
            '项目验收': 3
        }
        return duration_map.get(task_name, 5)
    
    @staticmethod
    def _estimate_skills(task_name: str) -> List[str]:
        """估算任务所需技能"""
        skills_map = {
            '业务调研': ['沟通', '分析'],
            '需求访谈': ['沟通', '访谈'],
            '架构设计': ['架构设计', '技术选型'],
            '数据库设计': ['数据库', 'SQL'],
            '前端开发': ['HTML', 'CSS', 'JavaScript', 'React'],
            '后端开发': ['Python', 'Java', 'Go', 'API设计'],
            '单元测试': ['测试', '自动化'],
            '集成测试': ['测试', '质量保障'],
            '系统测试': ['测试', '性能'],
        }
        return skills_map.get(task_name, ['项目管理'])
