"""
行业项目模板库

为 AI-PM 系统提供 10 个标准行业项目模板，每个模板包含：
- 模板元信息（名称、描述、行业类型）
- 阶段划分（phases）
- 预定义任务（含估算工时）
- 里程碑（milestones）
- 常见风险（risks）

使用方式：
    from app.services.project_templates import PROJECT_TEMPLATES, get_template_by_industry
"""

from typing import Dict, Any, Optional

# --------------------------------------------------------------------------- #
# 模板数据结构
# --------------------------------------------------------------------------- #

PROJECT_TEMPLATES: list[Dict[str, Any]] = [
    # =========================================================================
    # 1. IT软件开发 - Scrum敏捷开发模板
    # =========================================================================
    {
        "name": "Scrum敏捷开发",
        "description": "基于Scrum框架的敏捷软件开发项目模板，适用于Web/移动端/后端等软件开发项目",
        "industry_type": "it_software",
        "phases": [
            {"name": "项目启动", "description": "组建团队、搭建环境、确认需求范围", "order": 1},
            {"name": "Sprint规划", "description": "产品待办列表梳理、Sprint计划会议", "order": 2},
            {"name": "迭代开发", "description": "Scrum迭代开发、每日站会、Sprint评审", "order": 3},
            {"name": "测试与修复", "description": "集成测试、回归测试、Bug修复", "order": 4},
            {"name": "发布上线", "description": "生产环境部署、发布评审、上线监控", "order": 5},
            {"name": "项目复盘", "description": "Sprint回顾、项目总结、知识归档", "order": 6},
        ],
        "tasks": [
            {"name": "组建Scrum团队", "estimated_hours": 8, "phase": "项目启动"},
            {"name": "开发环境搭建", "estimated_hours": 16, "phase": "项目启动"},
            {"name": "产品待办列表梳理", "estimated_hours": 24, "phase": "Sprint规划"},
            {"name": "用户故事拆分与评估", "estimated_hours": 16, "phase": "Sprint规划"},
            {"name": "Sprint Backlog确认", "estimated_hours": 4, "phase": "Sprint规划"},
            {"name": "架构设计与技术选型", "estimated_hours": 24, "phase": "迭代开发"},
            {"name": "数据库设计与建模", "estimated_hours": 16, "phase": "迭代开发"},
            {"name": "后端API开发", "estimated_hours": 80, "phase": "迭代开发"},
            {"name": "前端界面开发", "estimated_hours": 80, "phase": "迭代开发"},
            {"name": "单元测试编写", "estimated_hours": 40, "phase": "迭代开发"},
            {"name": "接口联调", "estimated_hours": 24, "phase": "测试与修复"},
            {"name": "集成测试", "estimated_hours": 32, "phase": "测试与修复"},
            {"name": "性能测试与优化", "estimated_hours": 24, "phase": "测试与修复"},
            {"name": "Bug修复", "estimated_hours": 32, "phase": "测试与修复"},
            {"name": "UAT测试", "estimated_hours": 16, "phase": "测试与修复"},
            {"name": "生产环境部署", "estimated_hours": 8, "phase": "发布上线"},
            {"name": "数据迁移与校验", "estimated_hours": 8, "phase": "发布上线"},
            {"name": "上线后监控与应急响应", "estimated_hours": 16, "phase": "发布上线"},
            {"name": "Sprint回顾会议", "estimated_hours": 4, "phase": "项目复盘"},
            {"name": "项目文档归档", "estimated_hours": 8, "phase": "项目复盘"},
        ],
        "milestones": [
            {"name": "项目启动完成", "description": "团队组建完毕，环境可用", "phase": "项目启动"},
            {"name": "Sprint Backlog确认", "description": "第一个Sprint计划完成", "phase": "Sprint规划"},
            {"name": "核心功能开发完成", "description": "主要功能模块代码提交", "phase": "迭代开发"},
            {"name": "测试通过", "description": "所有测试用例通过，无P0/P1级Bug", "phase": "测试与修复"},
            {"name": "正式上线", "description": "系统在生产环境稳定运行", "phase": "发布上线"},
        ],
        "risks": [
            {"name": "需求频繁变更", "category": "business", "probability": 0.7, "impact": 0.6},
            {"name": "关键技术选型失误", "category": "technical", "probability": 0.3, "impact": 0.8},
            {"name": "开发资源不足", "category": "resource", "probability": 0.5, "impact": 0.6},
        ],
    },
    # =========================================================================
    # 2. 系统集成项目 - 硬件+软件集成模板
    # =========================================================================
    {
        "name": "系统集成实施",
        "description": "涵盖硬件部署、软件对接、联调测试的全流程系统集成项目模板",
        "industry_type": "it_hardware",
        "phases": [
            {"name": "需求调研", "description": "现场勘查、接口需求确认、技术方案设计", "order": 1},
            {"name": "方案设计", "description": "系统架构设计、接口规范定义、部署方案", "order": 2},
            {"name": "硬件部署", "description": "设备采购、安装、网络布线", "order": 3},
            {"name": "软件开发与对接", "description": "接口开发、数据同步、协议适配", "order": 4},
            {"name": "联调测试", "description": "系统联调、压力测试、容灾演练", "order": 5},
            {"name": "试运行与验收", "description": "试运行、问题修复、正式验收", "order": 6},
        ],
        "tasks": [
            {"name": "现场环境勘查", "estimated_hours": 16, "phase": "需求调研"},
            {"name": "接口需求调研", "estimated_hours": 24, "phase": "需求调研"},
            {"name": "技术方案编制", "estimated_hours": 32, "phase": "方案设计"},
            {"name": "系统架构设计", "estimated_hours": 24, "phase": "方案设计"},
            {"name": "接口规范定义", "estimated_hours": 16, "phase": "方案设计"},
            {"name": "设备采购与到货", "estimated_hours": 40, "phase": "硬件部署"},
            {"name": "硬件安装上架", "estimated_hours": 24, "phase": "硬件部署"},
            {"name": "网络布线与调试", "estimated_hours": 16, "phase": "硬件部署"},
            {"name": "接口协议适配开发", "estimated_hours": 64, "phase": "软件开发与对接"},
            {"name": "数据同步中间件开发", "estimated_hours": 48, "phase": "软件开发与对接"},
            {"name": "系统联调测试", "estimated_hours": 40, "phase": "联调测试"},
            {"name": "压力与稳定性测试", "estimated_hours": 24, "phase": "联调测试"},
            {"name": "容灾与备份演练", "estimated_hours": 16, "phase": "联调测试"},
            {"name": "试运行监控", "estimated_hours": 40, "phase": "试运行与验收"},
            {"name": "问题整改与优化", "estimated_hours": 24, "phase": "试运行与验收"},
            {"name": "验收文档编制", "estimated_hours": 16, "phase": "试运行与验收"},
        ],
        "milestones": [
            {"name": "技术方案评审通过", "description": "集成方案通过专家评审", "phase": "方案设计"},
            {"name": "硬件部署完成", "description": "所有设备安装调试完毕", "phase": "硬件部署"},
            {"name": "接口开发完成", "description": "所有接口开发与单元测试完成", "phase": "软件开发与对接"},
            {"name": "联调测试通过", "description": "系统联调测试达到验收标准", "phase": "联调测试"},
            {"name": "项目验收", "description": "客户签署验收报告", "phase": "试运行与验收"},
        ],
        "risks": [
            {"name": "硬件到货延迟", "category": "schedule", "probability": 0.5, "impact": 0.7},
            {"name": "第三方接口变更", "category": "external", "probability": 0.6, "impact": 0.5},
            {"name": "兼容性问题", "category": "technical", "probability": 0.5, "impact": 0.6},
        ],
    },
    # =========================================================================
    # 3. 市场营销活动 - 从策划到复盘模板
    # =========================================================================
    {
        "name": "市场营销活动全流程",
        "description": "涵盖市场调研、活动策划、执行落地到效果复盘的完整市场营销活动模板",
        "industry_type": "service",
        "phases": [
            {"name": "市场调研", "description": "目标市场分析、竞品调研、用户洞察", "order": 1},
            {"name": "活动策划", "description": "活动方案制定、预算编制、资源筹备", "order": 2},
            {"name": "素材制作", "description": "视觉设计、文案撰写、宣传物料制作", "order": 3},
            {"name": "活动执行", "description": "渠道推广、活动现场管理、用户互动", "order": 4},
            {"name": "效果评估", "description": "数据收集、ROI分析、效果报告", "order": 5},
            {"name": "项目复盘", "description": "经验总结、知识沉淀、优化建议", "order": 6},
        ],
        "tasks": [
            {"name": "目标市场分析", "estimated_hours": 24, "phase": "市场调研"},
            {"name": "竞品营销策略调研", "estimated_hours": 16, "phase": "市场调研"},
            {"name": "用户画像与需求洞察", "estimated_hours": 16, "phase": "市场调研"},
            {"name": "活动目标与KPI设定", "estimated_hours": 8, "phase": "活动策划"},
            {"name": "活动方案编制", "estimated_hours": 24, "phase": "活动策划"},
            {"name": "预算编制与审批", "estimated_hours": 8, "phase": "活动策划"},
            {"name": "视觉设计（主KV/海报）", "estimated_hours": 32, "phase": "素材制作"},
            {"name": "宣传文案撰写", "estimated_hours": 16, "phase": "素材制作"},
            {"name": "宣传物料制作与印刷", "estimated_hours": 24, "phase": "素材制作"},
            {"name": "预热推广与渠道投放", "estimated_hours": 40, "phase": "活动执行"},
            {"name": "活动现场组织与管理", "estimated_hours": 48, "phase": "活动执行"},
            {"name": "用户互动与社群运营", "estimated_hours": 32, "phase": "活动执行"},
            {"name": "活动数据采集与整理", "estimated_hours": 16, "phase": "效果评估"},
            {"name": "ROI及效果分析", "estimated_hours": 16, "phase": "效果评估"},
            {"name": "活动效果报告编制", "estimated_hours": 16, "phase": "效果评估"},
            {"name": "项目复盘会议", "estimated_hours": 4, "phase": "项目复盘"},
            {"name": "经验文档归档", "estimated_hours": 8, "phase": "项目复盘"},
        ],
        "milestones": [
            {"name": "调研报告完成", "description": "市场调研报告评审通过", "phase": "市场调研"},
            {"name": "活动方案审批通过", "description": "活动策划方案获管理层批准", "phase": "活动策划"},
            {"name": "宣传物料就绪", "description": "所有设计物料定稿交付", "phase": "素材制作"},
            {"name": "活动正式上线", "description": "活动按计划启动执行", "phase": "活动执行"},
            {"name": "复盘报告交付", "description": "活动效果复盘报告完成", "phase": "项目复盘"},
        ],
        "risks": [
            {"name": "活动曝光不足", "category": "business", "probability": 0.5, "impact": 0.6},
            {"name": "预算超支", "category": "cost", "probability": 0.4, "impact": 0.5},
            {"name": "竞品同期活动干扰", "category": "external", "probability": 0.5, "impact": 0.4},
        ],
    },
    # =========================================================================
    # 4. 建筑工程 - 设计-采购-施工模板
    # =========================================================================
    {
        "name": "建筑工程EPC总承包",
        "description": "依据EPC管理模式，覆盖设计(Engineering)、采购(Procurement)、施工(Construction)全过程的建筑工程模板",
        "industry_type": "construction",
        "phases": [
            {"name": "项目策划", "description": "项目立项、可行性研究、初步设计", "order": 1},
            {"name": "工程设计", "description": "详细设计、施工图设计、图纸审查", "order": 2},
            {"name": "采购与招标", "description": "设备材料采购、分包招标、合同签订", "order": 3},
            {"name": "施工准备", "description": "现场三通一平、临建搭设、施工组织设计", "order": 4},
            {"name": "主体施工", "description": "基础工程、主体结构、安装工程", "order": 5},
            {"name": "竣工验收", "description": "专项验收、竣工资料整理、交付", "order": 6},
        ],
        "tasks": [
            {"name": "项目可行性研究", "estimated_hours": 80, "phase": "项目策划"},
            {"name": "初步设计方案编制", "estimated_hours": 120, "phase": "项目策划"},
            {"name": "详细施工图设计", "estimated_hours": 240, "phase": "工程设计"},
            {"name": "图纸内部审查", "estimated_hours": 40, "phase": "工程设计"},
            {"name": "施工图外审报批", "estimated_hours": 40, "phase": "工程设计"},
            {"name": "主要设备采购招标", "estimated_hours": 80, "phase": "采购与招标"},
            {"name": "分包单位招标与评审", "estimated_hours": 60, "phase": "采购与招标"},
            {"name": "采购合同签订", "estimated_hours": 40, "phase": "采购与招标"},
            {"name": "现场三通一平", "estimated_hours": 120, "phase": "施工准备"},
            {"name": "临时设施搭建", "estimated_hours": 80, "phase": "施工准备"},
            {"name": "施工组织设计编制", "estimated_hours": 60, "phase": "施工准备"},
            {"name": "基础工程施工", "estimated_hours": 320, "phase": "主体施工"},
            {"name": "主体结构施工", "estimated_hours": 480, "phase": "主体施工"},
            {"name": "机电安装工程", "estimated_hours": 320, "phase": "主体施工"},
            {"name": "装饰装修工程", "estimated_hours": 240, "phase": "主体施工"},
            {"name": "分项工程验收", "estimated_hours": 80, "phase": "竣工验收"},
            {"name": "竣工资料整理归档", "estimated_hours": 80, "phase": "竣工验收"},
            {"name": "项目交付与移交", "estimated_hours": 40, "phase": "竣工验收"},
        ],
        "milestones": [
            {"name": "施工图审查通过", "description": "施工图纸通过政府审查", "phase": "工程设计"},
            {"name": "主要设备到货", "description": "核心设备完成采购到货", "phase": "采购与招标"},
            {"name": "主体结构封顶", "description": "主体结构施工完成", "phase": "主体施工"},
            {"name": "竣工预验收", "description": "各专项验收完成", "phase": "竣工验收"},
            {"name": "项目交付", "description": "项目正式交付业主", "phase": "竣工验收"},
        ],
        "risks": [
            {"name": "图纸变更导致返工", "category": "technical", "probability": 0.6, "impact": 0.7},
            {"name": "材料价格上涨", "category": "cost", "probability": 0.5, "impact": 0.6},
            {"name": "恶劣天气影响工期", "category": "external", "probability": 0.6, "impact": 0.4},
            {"name": "安全事故", "category": "quality", "probability": 0.2, "impact": 0.9},
        ],
    },
    # =========================================================================
    # 5. 产品研发 - 从概念到上市模板
    # =========================================================================
    {
        "name": "产品研发全流程",
        "description": "从产品概念、设计验证到量产上市的完整产品研发管理模板",
        "industry_type": "manufacturing",
        "phases": [
            {"name": "概念阶段", "description": "市场机会分析、产品概念定义、商业论证", "order": 1},
            {"name": "设计验证", "description": "产品详细设计、原型制作、设计验证测试", "order": 2},
            {"name": "工程验证", "description": "工程样机制作、性能测试、设计优化", "order": 3},
            {"name": "生产验证", "description": "小批量试产、生产工艺验证、供应链准备", "order": 4},
            {"name": "量产上市", "description": "量产爬坡、市场推广、上市后监控", "order": 5},
        ],
        "tasks": [
            {"name": "市场机会分析与调研", "estimated_hours": 40, "phase": "概念阶段"},
            {"name": "产品概念定义", "estimated_hours": 24, "phase": "概念阶段"},
            {"name": "商业论证与立项", "estimated_hours": 16, "phase": "概念阶段"},
            {"name": "产品详细设计", "estimated_hours": 80, "phase": "设计验证"},
            {"name": "外观与结构设计", "estimated_hours": 80, "phase": "设计验证"},
            {"name": "手板原型制作", "estimated_hours": 60, "phase": "设计验证"},
            {"name": "设计评审", "estimated_hours": 8, "phase": "设计验证"},
            {"name": "工程样机制作", "estimated_hours": 120, "phase": "工程验证"},
            {"name": "性能与可靠性测试", "estimated_hours": 80, "phase": "工程验证"},
            {"name": "安规与认证测试", "estimated_hours": 80, "phase": "工程验证"},
            {"name": "设计优化与改进", "estimated_hours": 40, "phase": "工程验证"},
            {"name": "模具开发与制造", "estimated_hours": 240, "phase": "生产验证"},
            {"name": "小批量试产", "estimated_hours": 80, "phase": "生产验证"},
            {"name": "生产工艺验证", "estimated_hours": 40, "phase": "生产验证"},
            {"name": "供应链入库与备料", "estimated_hours": 40, "phase": "生产验证"},
            {"name": "量产爬坡", "estimated_hours": 120, "phase": "量产上市"},
            {"name": "市场推广与渠道铺货", "estimated_hours": 80, "phase": "量产上市"},
            {"name": "上市后质量监控", "estimated_hours": 60, "phase": "量产上市"},
        ],
        "milestones": [
            {"name": "产品概念确认", "description": "产品概念通过评审委员会审批", "phase": "概念阶段"},
            {"name": "设计冻结", "description": "产品设计定型，不再做重大变更", "phase": "设计验证"},
            {"name": "工程验证通过", "description": "工程样机通过全部性能测试", "phase": "工程验证"},
            {"name": "试产通过", "description": "小批量试产良率达到目标", "phase": "生产验证"},
            {"name": "产品正式上市", "description": "首批量产产品完成发货", "phase": "量产上市"},
        ],
        "risks": [
            {"name": "设计缺陷导致返工", "category": "technical", "probability": 0.5, "impact": 0.7},
            {"name": "模具开发延误", "category": "schedule", "probability": 0.4, "impact": 0.6},
            {"name": "认证不通过", "category": "external", "probability": 0.3, "impact": 0.8},
            {"name": "量产良率不达标", "category": "quality", "probability": 0.4, "impact": 0.6},
        ],
    },
    # =========================================================================
    # 6. 咨询项目实施 - 从诊断到交付模板
    # =========================================================================
    {
        "name": "管理咨询项目实施",
        "description": "标准管理咨询项目流程：从企业诊断、方案设计到落地辅导的全过程模板",
        "industry_type": "consulting",
        "phases": [
            {"name": "项目启动", "description": "团队组建、项目章程制定、初步调研", "order": 1},
            {"name": "现状诊断", "description": "深度调研、数据分析、问题识别", "order": 2},
            {"name": "方案设计", "description": "解决方向确定、方案设计、可行性评估", "order": 3},
            {"name": "方案汇报", "description": "阶段汇报、方案论证、客户反馈", "order": 4},
            {"name": "落地辅导", "description": "实施指导、培训赋能、效果跟踪", "order": 5},
            {"name": "项目收尾", "description": "成果交付、项目总结、知识沉淀", "order": 6},
        ],
        "tasks": [
            {"name": "项目启动会", "estimated_hours": 4, "phase": "项目启动"},
            {"name": "项目章程制定", "estimated_hours": 8, "phase": "项目启动"},
            {"name": "高层访谈", "estimated_hours": 16, "phase": "项目启动"},
            {"name": "深度调研与数据收集", "estimated_hours": 40, "phase": "现状诊断"},
            {"name": "业务流程梳理", "estimated_hours": 40, "phase": "现状诊断"},
            {"name": "数据分析与问题诊断", "estimated_hours": 32, "phase": "现状诊断"},
            {"name": "诊断报告编制", "estimated_hours": 24, "phase": "现状诊断"},
            {"name": "解决方向确认", "estimated_hours": 8, "phase": "方案设计"},
            {"name": "详细方案设计", "estimated_hours": 60, "phase": "方案设计"},
            {"name": "方案可行性评估", "estimated_hours": 16, "phase": "方案设计"},
            {"name": "阶段性汇报与论证", "estimated_hours": 8, "phase": "方案汇报"},
            {"name": "方案修订与确认", "estimated_hours": 16, "phase": "方案汇报"},
            {"name": "实施行动计划制定", "estimated_hours": 16, "phase": "落地辅导"},
            {"name": "客户方培训赋能", "estimated_hours": 24, "phase": "落地辅导"},
            {"name": "实施过程辅导", "estimated_hours": 40, "phase": "落地辅导"},
            {"name": "效果跟踪与评估", "estimated_hours": 24, "phase": "落地辅导"},
            {"name": "最终报告交付", "estimated_hours": 24, "phase": "项目收尾"},
            {"name": "项目总结与知识沉淀", "estimated_hours": 8, "phase": "项目收尾"},
        ],
        "milestones": [
            {"name": "诊断报告交付", "description": "现状诊断报告通过客户确认", "phase": "现状诊断"},
            {"name": "方案设计评审通过", "description": "方案通过客户管理层评审", "phase": "方案设计"},
            {"name": "方案终稿确认", "description": "客户签署方案确认书", "phase": "方案汇报"},
            {"name": "培训完成", "description": "客户方核心团队完成培训", "phase": "落地辅导"},
            {"name": "项目验收", "description": "客户签署项目验收报告", "phase": "项目收尾"},
        ],
        "risks": [
            {"name": "客户配合度不足", "category": "external", "probability": 0.6, "impact": 0.6},
            {"name": "调研数据不充分", "category": "resource", "probability": 0.4, "impact": 0.5},
            {"name": "方案落地阻力大", "category": "business", "probability": 0.5, "impact": 0.6},
        ],
    },
    # =========================================================================
    # 7. 数据迁移项目 - ETL+验证模板
    # =========================================================================
    {
        "name": "数据迁移与ETL实施",
        "description": "涵盖数据评估、ETL开发、迁移执行与数据验证的全流程数据迁移项目模板",
        "industry_type": "it_software",
        "phases": [
            {"name": "数据评估", "description": "源数据分析、数据质量评估、迁移策略制定", "order": 1},
            {"name": "架构设计", "description": "目标数据模型设计、ETL架构设计、映射规则定义", "order": 2},
            {"name": "ETL开发", "description": "抽取-转换-加载脚本开发、错误处理机制", "order": 3},
            {"name": "测试迁移", "description": "试迁移、数据比对、差异修复", "order": 4},
            {"name": "正式迁移", "description": "全量迁移、增量同步、切换上线", "order": 5},
            {"name": "验证与收尾", "description": "数据完整性验证、性能验证、文档归档", "order": 6},
        ],
        "tasks": [
            {"name": "源系统数据摸底", "estimated_hours": 24, "phase": "数据评估"},
            {"name": "数据质量评估报告", "estimated_hours": 16, "phase": "数据评估"},
            {"name": "迁移策略与方案制定", "estimated_hours": 16, "phase": "数据评估"},
            {"name": "目标数据模型设计", "estimated_hours": 32, "phase": "架构设计"},
            {"name": "ETL架构设计", "estimated_hours": 16, "phase": "架构设计"},
            {"name": "字段映射规则定义", "estimated_hours": 24, "phase": "架构设计"},
            {"name": "抽取脚本开发", "estimated_hours": 40, "phase": "ETL开发"},
            {"name": "数据清洗与转换开发", "estimated_hours": 60, "phase": "ETL开发"},
            {"name": "加载脚本开发", "estimated_hours": 32, "phase": "ETL开发"},
            {"name": "异常处理机制开发", "estimated_hours": 16, "phase": "ETL开发"},
            {"name": "试迁移执行", "estimated_hours": 24, "phase": "测试迁移"},
            {"name": "数据比对与差异分析", "estimated_hours": 32, "phase": "测试迁移"},
            {"name": "差异修复与脚本优化", "estimated_hours": 24, "phase": "测试迁移"},
            {"name": "全量迁移执行", "estimated_hours": 24, "phase": "正式迁移"},
            {"name": "增量数据同步", "estimated_hours": 16, "phase": "正式迁移"},
            {"name": "系统切换与上线", "estimated_hours": 8, "phase": "正式迁移"},
            {"name": "数据完整性验证", "estimated_hours": 24, "phase": "验证与收尾"},
            {"name": "性能与稳定性验证", "estimated_hours": 16, "phase": "验证与收尾"},
            {"name": "迁移文档与运维手册", "estimated_hours": 16, "phase": "验证与收尾"},
        ],
        "milestones": [
            {"name": "迁移方案评审通过", "description": "数据迁移方案获各方确认", "phase": "架构设计"},
            {"name": "ETL开发完成", "description": "所有ETL脚本开发与单元测试完成", "phase": "ETL开发"},
            {"name": "试迁移验证通过", "description": "试迁移数据比对一致率达到99.9%+", "phase": "测试迁移"},
            {"name": "正式迁移完成", "description": "全量数据成功迁移至目标系统", "phase": "正式迁移"},
            {"name": "数据验证通过", "description": "数据完整性与业务验证通过", "phase": "验证与收尾"},
        ],
        "risks": [
            {"name": "源数据质量差", "category": "quality", "probability": 0.7, "impact": 0.7},
            {"name": "迁移过程中数据丢失", "category": "technical", "probability": 0.3, "impact": 0.9},
            {"name": "业务系统停机窗口不足", "category": "schedule", "probability": 0.4, "impact": 0.6},
        ],
    },
    # =========================================================================
    # 8. 企业内部数字化 - OA/ERP实施模板
    # =========================================================================
    {
        "name": "企业数字化系统实施",
        "description": "适用于OA、ERP、CRM等企业级管理系统的实施交付项目模板",
        "industry_type": "service",
        "phases": [
            {"name": "项目规划", "description": "需求调研、系统选型、实施计划制定", "order": 1},
            {"name": "系统配置", "description": "系统参数配置、权限体系搭建、基础数据准备", "order": 2},
            {"name": "二次开发", "description": "定制功能开发、接口对接、报表开发", "order": 3},
            {"name": "系统测试", "description": "单元测试、集成测试、用户验收测试", "order": 4},
            {"name": "培训与上线", "description": "用户培训、数据迁移、系统切换上线", "order": 5},
            {"name": "运维支持", "description": "上线后支持、问题处理、持续优化", "order": 6},
        ],
        "tasks": [
            {"name": "需求调研与梳理", "estimated_hours": 40, "phase": "项目规划"},
            {"name": "系统选型评估", "estimated_hours": 24, "phase": "项目规划"},
            {"name": "项目实施计划制定", "estimated_hours": 16, "phase": "项目规划"},
            {"name": "系统环境搭建", "estimated_hours": 16, "phase": "系统配置"},
            {"name": "业务参数配置", "estimated_hours": 40, "phase": "系统配置"},
            {"name": "权限体系设计与配置", "estimated_hours": 24, "phase": "系统配置"},
            {"name": "基础数据导入", "estimated_hours": 32, "phase": "系统配置"},
            {"name": "定制功能开发", "estimated_hours": 80, "phase": "二次开发"},
            {"name": "第三方系统接口对接", "estimated_hours": 48, "phase": "二次开发"},
            {"name": "报表与仪表盘开发", "estimated_hours": 32, "phase": "二次开发"},
            {"name": "业务流程测试", "estimated_hours": 32, "phase": "系统测试"},
            {"name": "集成测试", "estimated_hours": 24, "phase": "系统测试"},
            {"name": "用户验收测试(UAT)", "estimated_hours": 24, "phase": "系统测试"},
            {"name": "用户操作培训", "estimated_hours": 24, "phase": "培训与上线"},
            {"name": "系统切换与上线", "estimated_hours": 16, "phase": "培训与上线"},
            {"name": "上线后问题处理", "estimated_hours": 40, "phase": "运维支持"},
            {"name": "系统性能优化", "estimated_hours": 16, "phase": "运维支持"},
            {"name": "项目验收文档提交", "estimated_hours": 16, "phase": "运维支持"},
        ],
        "milestones": [
            {"name": "需求确认", "description": "需求规格说明书经客户签字确认", "phase": "项目规划"},
            {"name": "系统配置完成", "description": "系统参数与权限配置完成", "phase": "系统配置"},
            {"name": "开发完成", "description": "所有定制功能开发完毕", "phase": "二次开发"},
            {"name": "UAT通过", "description": "用户验收测试签字通过", "phase": "系统测试"},
            {"name": "系统正式上线", "description": "系统切换完成，平稳运行", "phase": "培训与上线"},
        ],
        "risks": [
            {"name": "客户需求频繁变更", "category": "business", "probability": 0.7, "impact": 0.6},
            {"name": "历史数据迁移困难", "category": "technical", "probability": 0.5, "impact": 0.6},
            {"name": "用户接受度低", "category": "business", "probability": 0.5, "impact": 0.5},
        ],
    },
    # =========================================================================
    # 9. 培训与知识传递 - 课程开发+培训模板
    # =========================================================================
    {
        "name": "培训课程开发与交付",
        "description": "从培训需求分析、课程设计开发到培训交付与评估的全流程培训项目管理模板",
        "industry_type": "education",
        "phases": [
            {"name": "需求分析", "description": "培训需求调研、学员分析、培训目标确定", "order": 1},
            {"name": "课程设计", "description": "课程大纲设计、教学方案制定、评估体系设计", "order": 2},
            {"name": "课程开发", "description": "课件制作、教材编写、案例开发", "order": 3},
            {"name": "讲师培训", "description": "内部讲师选拔、TTT培训、试讲验收", "order": 4},
            {"name": "培训实施", "description": "培训排期、培训执行、学员管理", "order": 5},
            {"name": "效果评估", "description": "培训考核、效果评估、持续改进", "order": 6},
        ],
        "tasks": [
            {"name": "培训需求调研", "estimated_hours": 16, "phase": "需求分析"},
            {"name": "目标学员分析", "estimated_hours": 8, "phase": "需求分析"},
            {"name": "培训目标与标准确定", "estimated_hours": 8, "phase": "需求分析"},
            {"name": "课程大纲设计", "estimated_hours": 16, "phase": "课程设计"},
            {"name": "教学方案制定", "estimated_hours": 16, "phase": "课程设计"},
            {"name": "考核评估体系设计", "estimated_hours": 8, "phase": "课程设计"},
            {"name": "课件PPT制作", "estimated_hours": 40, "phase": "课程开发"},
            {"name": "学员教材编写", "estimated_hours": 32, "phase": "课程开发"},
            {"name": "案例与实训内容开发", "estimated_hours": 24, "phase": "课程开发"},
            {"name": "习题与考试题库建设", "estimated_hours": 16, "phase": "课程开发"},
            {"name": "内部讲师选拔", "estimated_hours": 8, "phase": "讲师培训"},
            {"name": "TTT讲师培训", "estimated_hours": 24, "phase": "讲师培训"},
            {"name": "试讲与课程验收", "estimated_hours": 8, "phase": "讲师培训"},
            {"name": "培训排期与通知", "estimated_hours": 8, "phase": "培训实施"},
            {"name": "培训现场实施", "estimated_hours": 40, "phase": "培训实施"},
            {"name": "学员签到与档案管理", "estimated_hours": 8, "phase": "培训实施"},
            {"name": "培训考核与成绩评定", "estimated_hours": 16, "phase": "效果评估"},
            {"name": "培训满意度调查", "estimated_hours": 8, "phase": "效果评估"},
            {"name": "培训效果评估报告", "estimated_hours": 16, "phase": "效果评估"},
            {"name": "课程迭代优化计划", "estimated_hours": 8, "phase": "效果评估"},
        ],
        "milestones": [
            {"name": "课程大纲评审通过", "description": "课程大纲通过教学委员会评审", "phase": "课程设计"},
            {"name": "课件开发完成", "description": "全部课件与教材定稿交付", "phase": "课程开发"},
            {"name": "讲师认证完成", "description": "内部讲师通过试讲及认证", "phase": "讲师培训"},
            {"name": "培训实施完成", "description": "全部培训批次执行完毕", "phase": "培训实施"},
            {"name": "评估报告交付", "description": "培训效果评估报告完成", "phase": "效果评估"},
        ],
        "risks": [
            {"name": "学员参与度不高", "category": "resource", "probability": 0.5, "impact": 0.5},
            {"name": "课程内容与实际脱节", "category": "quality", "probability": 0.4, "impact": 0.6},
            {"name": "讲师资源不足", "category": "resource", "probability": 0.4, "impact": 0.5},
        ],
    },
    # =========================================================================
    # 10. AI/ML项目 - 从数据采集到模型部署模板
    # =========================================================================
    {
        "name": "AI/ML模型开发与部署",
        "description": "涵盖数据采集、特征工程、模型训练、评估到生产部署的AI/ML项目全流程模板",
        "industry_type": "it_software",
        "phases": [
            {"name": "业务理解", "description": "业务问题定义、AI可行性评估、项目目标设定", "order": 1},
            {"name": "数据准备", "description": "数据采集、数据清洗、数据标注、特征工程", "order": 2},
            {"name": "模型开发", "description": "基线模型、模型训练、超参调优", "order": 3},
            {"name": "模型评估", "description": "离线评估、A/B测试、模型解释性分析", "order": 4},
            {"name": "模型部署", "description": "模型服务化、API开发、部署监控", "order": 5},
            {"name": "运维迭代", "description": "模型监控、数据漂移检测、模型重训", "order": 6},
        ],
        "tasks": [
            {"name": "业务问题定义与范围确认", "estimated_hours": 16, "phase": "业务理解"},
            {"name": "AI可行性评估", "estimated_hours": 24, "phase": "业务理解"},
            {"name": "项目KPI与成功标准定义", "estimated_hours": 8, "phase": "业务理解"},
            {"name": "数据源调研与采集", "estimated_hours": 40, "phase": "数据准备"},
            {"name": "数据清洗与预处理", "estimated_hours": 40, "phase": "数据准备"},
            {"name": "数据标注与质量检查", "estimated_hours": 60, "phase": "数据准备"},
            {"name": "特征工程与特征选择", "estimated_hours": 40, "phase": "数据准备"},
            {"name": "基线模型搭建与评估", "estimated_hours": 24, "phase": "模型开发"},
            {"name": "模型训练与调优", "estimated_hours": 80, "phase": "模型开发"},
            {"name": "超参数搜索与优化", "estimated_hours": 40, "phase": "模型开发"},
            {"name": "模型集成与融合", "estimated_hours": 24, "phase": "模型开发"},
            {"name": "离线评估指标计算", "estimated_hours": 16, "phase": "模型评估"},
            {"name": "A/B测试设计与执行", "estimated_hours": 32, "phase": "模型评估"},
            {"name": "模型解释性与公平性分析", "estimated_hours": 16, "phase": "模型评估"},
            {"name": "模型评估报告", "estimated_hours": 8, "phase": "模型评估"},
            {"name": "模型服务化接口开发", "estimated_hours": 32, "phase": "模型部署"},
            {"name": "模型容器化与部署", "estimated_hours": 16, "phase": "模型部署"},
            {"name": "推理性能优化", "estimated_hours": 24, "phase": "模型部署"},
            {"name": "模型监控体系搭建", "estimated_hours": 24, "phase": "运维迭代"},
            {"name": "数据漂移检测管道建设", "estimated_hours": 16, "phase": "运维迭代"},
            {"name": "模型自动重训流程", "estimated_hours": 16, "phase": "运维迭代"},
        ],
        "milestones": [
            {"name": "业务需求确认", "description": "AI项目目标和KPI获业务方确认", "phase": "业务理解"},
            {"name": "数据集准备完成", "description": "训练/验证/测试数据集准备就绪", "phase": "数据准备"},
            {"name": "基线模型达标", "description": "基线模型性能达到最低可接受标准", "phase": "模型开发"},
            {"name": "模型评估通过", "description": "模型通过离线评估与A/B测试", "phase": "模型评估"},
            {"name": "模型正式上线", "description": "模型部署至生产环境并稳定运行", "phase": "模型部署"},
        ],
        "risks": [
            {"name": "训练数据不足或质量差", "category": "quality", "probability": 0.6, "impact": 0.8},
            {"name": "模型性能不达标", "category": "technical", "probability": 0.5, "impact": 0.7},
            {"name": "数据隐私与合规问题", "category": "business", "probability": 0.3, "impact": 0.8},
            {"name": "线上推理延迟过高", "category": "technical", "probability": 0.4, "impact": 0.5},
        ],
    },
]


def get_template_by_industry(industry_type: str) -> list[Dict[str, Any]]:
    """按行业类型筛选模板"""
    return [t for t in PROJECT_TEMPLATES if t["industry_type"] == industry_type]


def get_template_by_name(name: str) -> Optional[Dict[str, Any]]:
    """按模板名称精确查找"""
    for t in PROJECT_TEMPLATES:
        if t["name"] == name:
            return t
    return None


def get_template_names() -> list[str]:
    """获取所有模板名称列表"""
    return [t["name"] for t in PROJECT_TEMPLATES]


def get_industry_types() -> list[str]:
    """获取所有模板覆盖的行业类型"""
    return list({t["industry_type"] for t in PROJECT_TEMPLATES})


def get_total_estimated_hours(template: Dict[str, Any]) -> float:
    """计算模板所有任务的总估算工时"""
    return sum(t["estimated_hours"] for t in template["tasks"])
