"""
PMI中国 AI-PM · 行业模板种子数据

覆盖 6 行业 × 2-3 场景 = 18 个标准模板
所有模板字段对齐 PMBOK 第6/7版标准命名

使用：
    cd backend
    python -m app.seed.industry_templates

或：
    python scripts/seed_industry_templates.py
"""
import asyncio
import sys
import os
from datetime import datetime

# Bootstrap path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db.session import async_session_maker, engine, Base
from app.models import TaskTemplate, User
from app.models.async_task import AsyncTask, AsyncTaskStatus
from sqlalchemy import select


# ============== 行业模板定义 ==============

INDUSTRY_TEMPLATES = [
    # ---------- 1. 制造业 ----------
    {
        "name": "新产品研发项目（NPI）",
        "description": "面向制造业新产品引入（NPI）的完整流程模板，覆盖市场调研→概念设计→样品试制→量产导入→上市全周期。对齐 PMBOK 第6版范围/时间/成本管理。",
        "category": "manufacturing",
        "fields": {
            "industry": "manufacturing",
            "scenario": "npi",
            "pmbok_alignment": ["5.范围管理", "6.时间管理", "7.成本管理", "11.风险管理"],
            "wbs_phases": [
                {"phase": "1. 立项", "tasks": ["市场调研报告", "竞品分析", "技术可行性评估", "立项决策评审"]},
                {"phase": "2. 概念设计", "tasks": ["产品概念草图", "技术规格书", "BOM 初版", "概念评审"]},
                {"phase": "3. 详细设计", "tasks": ["3D 建模", "2D 工程图", "DFM 分析", "设计评审"]},
                {"phase": "4. 样品试制", "tasks": ["EVT 样品", "DVT 测试", "PVT 验证", "样品评审"]},
                {"phase": "5. 量产导入", "tasks": ["工装夹具", "生产线布置", "SOP 编制", "试产", "量产评审"]},
                {"phase": "6. 上市", "tasks": ["市场资料", "销售培训", "客户试用", "正式发布"]}
            ],
            "default_milestones": ["立项批准", "概念冻结", "设计冻结", "EVT 通过", "DVT 通过", "PVT 通过", "量产批准", "上市日"],
            "risk_categories": ["技术风险", "供应链风险", "质量风险", "成本风险", "市场风险"],
            "budget_categories": ["材料费", "人工费", "设备折旧", "测试费", "外部服务", "差旅费"],
            "default_duration_weeks": 26
        },
        "is_global": True
    },
    {
        "name": "设备改造项目",
        "description": "工厂既有设备改造/升级项目模板，对齐 PMBOK 第7版「交付绩效域」与「开发方法」原则。",
        "category": "manufacturing",
        "fields": {
            "industry": "manufacturing",
            "scenario": "equipment_upgrade",
            "pmbok_alignment": ["PMBOK7-交付绩效域", "PMBOK7-开发方法"],
            "wbs_phases": [
                {"phase": "1. 现状评估", "tasks": ["设备健康诊断", "产能瓶颈分析", "改造需求确认"]},
                {"phase": "2. 方案设计", "tasks": ["改造方案设计", "投资估算", "ROI 测算", "方案评审"]},
                {"phase": "3. 停产准备", "tasks": ["备件采购", "施工队伍", "停产窗口确认", "应急预案"]},
                {"phase": "4. 施工执行", "tasks": ["设备拆除", "新设备安装", "管线改造", "调试"]},
                {"phase": "5. 验收投产", "tasks": ["单机试车", "联动试车", "产能验收", "投产"]}
            ],
            "default_milestones": ["方案批准", "停产开始", "安装完成", "调试通过", "投产"],
            "risk_categories": ["安全风险", "进度风险", "成本超支", "技术兼容"],
            "budget_categories": ["设备采购", "施工费", "备件", "调试费", "应急储备"],
            "default_duration_weeks": 12
        },
        "is_global": True
    },
    {
        "name": "工厂搬迁项目",
        "description": "工厂整体/部分搬迁项目模板，覆盖规划/拆除/运输/安装/调试/复产全周期。",
        "category": "manufacturing",
        "fields": {
            "industry": "manufacturing",
            "scenario": "factory_relocation",
            "pmbok_alignment": ["4.整合管理", "11.风险管理", "13.相关方管理"],
            "wbs_phases": [
                {"phase": "1. 选址规划", "tasks": ["选址评估", "政府审批", "厂房设计"]},
                {"phase": "2. 拆除打包", "tasks": ["设备清单", "拆除方案", "包装运输"]},
                {"phase": "3. 新厂安装", "tasks": ["基础施工", "设备就位", "管线接入"]},
                {"phase": "4. 调试复产", "tasks": ["单机调试", "联动调试", "试产", "正式投产"]}
            ],
            "default_milestones": ["选址确定", "拆除完成", "安装完成", "调试通过", "复产"],
            "risk_categories": ["运输损坏", "工期延误", "政府审批", "员工稳定"],
            "default_duration_weeks": 36
        },
        "is_global": True
    },

    # ---------- 2. IT/软件 ----------
    {
        "name": "软件研发项目（敏捷 Scrum）",
        "description": "标准 Scrum 敏捷开发项目模板，含 2 周 Sprint、Product Backlog、Sprint Review 等全套仪式。",
        "category": "it_software",
        "fields": {
            "industry": "it_software",
            "scenario": "scrum",
            "pmbok_alignment": ["PMBOK7-开发方法(敏捷)", "PMBOK8-AI原生"],
            "wbs_phases": [
                {"phase": "1. 启动", "tasks": ["产品愿景", "MVP 定义", "团队组建", "技术栈选型"]},
                {"phase": "2. 规划", "tasks": ["Product Backlog", "架构设计", "CI/CD 搭建"]},
                {"phase": "3. Sprint 循环", "tasks": ["Sprint Planning", "Daily Standup", "开发", "Sprint Review", "Sprint Retrospective"]}
            ],
            "default_milestones": ["MVP 发布", "Beta 上线", "GA 发布"],
            "sprint_length_weeks": 2,
            "ceremonies": ["Sprint Planning", "Daily Standup", "Sprint Review", "Retrospective", "Backlog Refinement"],
            "roles": ["Product Owner", "Scrum Master", "Development Team"],
            "risk_categories": ["需求变更", "技术债", "团队产能", "依赖阻塞"],
            "budget_categories": ["人力成本", "云资源", "第三方服务", "工具授权"]
        },
        "is_global": True
    },
    {
        "name": "系统迁移项目（上云）",
        "description": "企业系统迁移上云项目模板，含评估/规划/迁移/验证/切换全周期。",
        "category": "it_software",
        "fields": {
            "industry": "it_software",
            "scenario": "cloud_migration",
            "pmbok_alignment": ["4.整合管理", "11.风险管理"],
            "wbs_phases": [
                {"phase": "1. 现状评估", "tasks": ["系统盘点", "依赖梳理", "云厂商选型", "成本测算"]},
                {"phase": "2. 架构设计", "tasks": ["目标架构", "网络设计", "安全设计", "迁移策略"]},
                {"phase": "3. 试点迁移", "tasks": ["试点系统选择", "迁移执行", "性能验证", "回退演练"]},
                {"phase": "4. 批量迁移", "tasks": ["分批迁移", "数据同步", "切流验证"]},
                {"phase": "5. 收尾", "tasks": ["旧系统下线", "成本复盘", "知识转移"]}
            ],
            "default_milestones": ["评估完成", "架构批准", "试点通过", "批量迁移完成", "切换上线", "下线"],
            "risk_categories": ["数据丢失", "服务中断", "性能下降", "安全漏洞", "成本超支"],
            "default_duration_weeks": 24
        },
        "is_global": True
    },
    {
        "name": "IT 系统集成项目",
        "description": "企业 IT 系统集成/对接项目，含 API 设计/联调/测试/上线。",
        "category": "it_software",
        "fields": {
            "industry": "it_software",
            "scenario": "system_integration",
            "pmbok_alignment": ["5.范围管理", "10.沟通管理"],
            "wbs_phases": [
                {"phase": "1. 需求", "tasks": ["业务调研", "数据映射", "接口规格定义"]},
                {"phase": "2. 设计", "tasks": ["API 设计", "数据模型", "安全设计"]},
                {"phase": "3. 开发", "tasks": ["接口开发", "数据转换", "异常处理"]},
                {"phase": "4. 联调", "tasks": ["联调测试", "性能压测", "UAT"]},
                {"phase": "5. 上线", "tasks": ["灰度发布", "监控告警", "知识转移"]}
            ],
            "default_milestones": ["需求批准", "设计批准", "联调通过", "UAT 通过", "上线"],
            "default_duration_weeks": 16
        },
        "is_global": True
    },

    # ---------- 3. 建筑工程 ----------
    {
        "name": "施工总承包项目",
        "description": "建筑工程施工总承包项目模板，对齐 PMBOK 第6版成本管理（EVM 挣值管理核心场景）。",
        "category": "construction",
        "fields": {
            "industry": "construction",
            "scenario": "general_contractor",
            "pmbok_alignment": ["7.成本管理(EVM)", "6.时间管理", "8.质量管理", "11.风险管理"],
            "wbs_phases": [
                {"phase": "1. 施工准备", "tasks": ["施工组织设计", "临时设施", "报建审批", "图纸会审"]},
                {"phase": "2. 基础工程", "tasks": ["土方开挖", "基础施工", "防水", "回填"]},
                {"phase": "3. 主体结构", "tasks": ["钢筋", "模板", "混凝土", "砌体"]},
                {"phase": "4. 装饰装修", "tasks": ["外立面", "内装", "机电安装", "调试"]},
                {"phase": "5. 竣工验收", "tasks": ["初验", "整改", "终验", "备案"]}
            ],
            "default_milestones": ["开工令", "基础完成", "主体封顶", "外装完成", "机电调试", "竣工预验收", "竣工验收"],
            "risk_categories": ["安全事故", "工期延误", "质量缺陷", "成本超支", "材料涨价", "天气影响"],
            "budget_categories": ["人工费", "材料费", "机械费", "措施费", "管理费", "利润", "规费", "税金"],
            "evm_required": True,
            "default_duration_weeks": 78
        },
        "is_global": True
    },
    {
        "name": "装饰装修项目",
        "description": "室内装饰装修项目模板，含设计深化/材料/施工/验收。",
        "category": "construction",
        "fields": {
            "industry": "construction",
            "scenario": "interior_decoration",
            "pmbok_alignment": ["8.质量管理", "6.时间管理"],
            "wbs_phases": [
                {"phase": "1. 设计深化", "tasks": ["效果图确认", "施工图", "材料选型"]},
                {"phase": "2. 拆改", "tasks": ["拆除", "结构加固", "水电改造"]},
                {"phase": "3. 装饰", "tasks": ["墙面", "地面", "吊顶", "木作"]},
                {"phase": "4. 安装", "tasks": ["灯具", "洁具", "五金", "家具"]},
                {"phase": "5. 验收", "tasks": ["自检", "整改", "终验"]}
            ],
            "default_milestones": ["设计冻结", "拆改完成", "墙面完成", "安装完成", "验收"],
            "default_duration_weeks": 16
        },
        "is_global": True
    },

    # ---------- 4. 教育培训 ----------
    {
        "name": "课程开发项目",
        "description": "教育培训机构课程开发项目模板，含调研/设计/制作/试讲/上线。",
        "category": "education",
        "fields": {
            "industry": "education",
            "scenario": "course_development",
            "pmbok_alignment": ["5.范围管理", "8.质量管理"],
            "wbs_phases": [
                {"phase": "1. 调研", "tasks": ["学员画像", "竞品分析", "学习目标定义"]},
                {"phase": "2. 设计", "tasks": ["课程大纲", "教学策略", "评估方式"]},
                {"phase": "3. 制作", "tasks": ["讲义编写", "视频拍摄", "课件制作", "练习题"]},
                {"phase": "4. 试讲", "tasks": ["内部试讲", "学员试听", "反馈修订"]},
                {"phase": "5. 上线", "tasks": ["平台上线", "营销资料", "答疑支持"]}
            ],
            "default_milestones": ["大纲批准", "试讲通过", "正式上线"],
            "default_duration_weeks": 10
        },
        "is_global": True
    },
    {
        "name": "培训项目交付",
        "description": "面向企业的培训项目交付模板，含需求/方案/执行/评估。",
        "category": "education",
        "fields": {
            "industry": "education",
            "scenario": "training_delivery",
            "pmbok_alignment": ["13.相关方管理", "10.沟通管理"],
            "wbs_phases": [
                {"phase": "1. 需求", "tasks": ["培训目标", "学员层级", "企业痛点"]},
                {"phase": "2. 方案", "tasks": ["课程方案", "讲师匹配", "场地/平台"]},
                {"phase": "3. 执行", "tasks": ["课前预习", "面授/直播", "实操作业"]},
                {"phase": "4. 评估", "tasks": ["满意度", "知识测试", "行为转化", "ROI"]}
            ],
            "default_milestones": ["方案确认", "讲师确定", "首场交付", "评估完成"],
            "default_duration_weeks": 6
        },
        "is_global": True
    },

    # ---------- 5. 金融 ----------
    {
        "name": "合规审计项目",
        "description": "金融机构合规审计项目模板，对齐 PMBOK 第6版质量/风险/相关方管理。",
        "category": "finance",
        "fields": {
            "industry": "finance",
            "scenario": "compliance_audit",
            "pmbok_alignment": ["8.质量管理", "11.风险管理", "13.相关方管理"],
            "wbs_phases": [
                {"phase": "1. 启动", "tasks": ["审计目标", "范围确认", "团队组建"]},
                {"phase": "2. 计划", "tasks": ["审计计划", "数据请求", "样本设计"]},
                {"phase": "3. 执行", "tasks": ["现场审计", "抽样测试", "问题确认"]},
                {"phase": "4. 报告", "tasks": ["问题清单", "整改建议", "审计报告"]},
                {"phase": "5. 跟踪", "tasks": ["整改跟踪", "复核验证", "闭环"]}
            ],
            "default_milestones": ["启动会议", "计划批准", "现场结束", "报告发布", "整改完成"],
            "risk_categories": ["合规风险", "操作风险", "数据泄露", "审计独立性"],
            "default_duration_weeks": 14
        },
        "is_global": True
    },
    {
        "name": "金融系统升级项目",
        "description": "银行/保险核心系统升级项目，含需求/开发/测试/切换。",
        "category": "finance",
        "fields": {
            "industry": "finance",
            "scenario": "system_upgrade",
            "pmbok_alignment": ["4.整合管理", "11.风险管理", "8.质量管理"],
            "wbs_phases": [
                {"phase": "1. 需求", "tasks": ["业务需求", "监管要求", "技术评估"]},
                {"phase": "2. 设计", "tasks": ["架构设计", "数据库设计", "接口设计"]},
                {"phase": "3. 开发", "tasks": ["编码", "单元测试", "代码评审"]},
                {"phase": "4. 测试", "tasks": ["集成测试", "性能测试", "UAT", "安全测试"]},
                {"phase": "5. 上线", "tasks": ["切换方案", "数据迁移", "灰度", "全量切换"]},
                {"phase": "6. 运维", "tasks": ["监控", "应急", "复盘"]}
            ],
            "default_milestones": ["需求批准", "设计批准", "UAT通过", "切换批准", "上线"],
            "risk_categories": ["业务中断", "数据丢失", "监管处罚", "安全漏洞"],
            "default_duration_weeks": 40
        },
        "is_global": True
    },

    # ---------- 6. 政府 ----------
    {
        "name": "政务信息化建设项目",
        "description": "政府信息化建设项目模板，对齐 PMBOK + CPMAI 标准与等保三级要求。",
        "category": "government",
        "fields": {
            "industry": "government",
            "scenario": "govt_informatization",
            "pmbok_alignment": ["CPMAI-规划阶段", "CPMAI-实施阶段", "13.相关方管理"],
            "wbs_phases": [
                {"phase": "1. 立项", "tasks": ["需求调研", "可研报告", "专家评审", "发改立项"]},
                {"phase": "2. 招标", "tasks": ["招标文件", "发布公告", "评标", "中标公示"]},
                {"phase": "3. 设计", "tasks": ["初步设计", "施工图设计", "设计评审"]},
                {"phase": "4. 实施", "tasks": ["采购", "集成开发", "联调测试"]},
                {"phase": "5. 验收", "tasks": ["初验", "试运行", "终验", "审计"]}
            ],
            "default_milestones": ["立项批复", "招标完成", "设计批准", "初验通过", "终验通过", "审计完成"],
            "risk_categories": ["政策变化", "招标失败", "进度延误", "等保不过", "审计问题"],
            "compliance_required": True,
            "default_duration_weeks": 60
        },
        "is_global": True
    },
    {
        "name": "政府采购项目",
        "description": "政府采购项目标准模板，对齐《政府采购法》流程。",
        "category": "government",
        "fields": {
            "industry": "government",
            "scenario": "procurement",
            "pmbok_alignment": ["12.采购管理", "13.相关方管理"],
            "wbs_phases": [
                {"phase": "1. 采购需求", "tasks": ["需求论证", "预算申报", "采购计划"]},
                {"phase": "2. 采购执行", "tasks": ["采购文件", "公告", "评标"]},
                {"phase": "3. 合同", "tasks": ["合同起草", "法务审核", "签订"]},
                {"phase": "4. 履约", "tasks": ["到货验收", "付款", "售后"]}
            ],
            "default_milestones": ["需求确认", "公告发布", "中标公示", "合同签订", "验收"],
            "default_duration_weeks": 12
        },
        "is_global": True
    },

    # ---------- 通用模板 ----------
    {
        "name": "通用项目模板（PMBOK 标准）",
        "description": "对齐 PMBOK 第6版 5 大过程组的标准项目模板，适合任意行业入门。",
        "category": "general",
        "fields": {
            "industry": "general",
            "scenario": "pmbok_standard",
            "pmbok_alignment": ["启动", "规划", "执行", "监控", "收尾"],
            "wbs_phases": [
                {"phase": "1. 启动", "tasks": ["项目章程", "干系人识别"]},
                {"phase": "2. 规划", "tasks": ["范围说明书", "WBS", "进度计划", "预算", "质量计划", "风险登记册", "沟通计划"]},
                {"phase": "3. 执行", "tasks": ["资源调配", "质量保证", "团队管理", "沟通分发"]},
                {"phase": "4. 监控", "tasks": ["进度监控", "EVM 偏差分析", "风险监控", "变更控制"]},
                {"phase": "5. 收尾", "tasks": ["交付验收", "经验教训", "项目归档"]}
            ],
            "default_milestones": ["章程批准", "基线确立", "中期评审", "交付验收", "项目关闭"],
            "risk_categories": ["范围蔓延", "进度延误", "成本超支", "质量缺陷", "相关方冲突"],
            "evm_required": True,
            "default_duration_weeks": 20
        },
        "is_global": True
    },
    {
        "name": "敏捷转型项目",
        "description": "企业敏捷转型项目模板，覆盖现状评估→试点→规模化→持续优化。",
        "category": "general",
        "fields": {
            "industry": "general",
            "scenario": "agile_transformation",
            "pmbok_alignment": ["PMBOK7-开发方法", "PMBOK7-复杂性原则"],
            "wbs_phases": [
                {"phase": "1. 现状评估", "tasks": ["成熟度评估", "痛点识别", "转型目标"]},
                {"phase": "2. 试点", "tasks": ["试点团队", "敏捷教练", "Sprint 试点"]},
                {"phase": "3. 规模化", "tasks": ["SAFe/LeSS 选型", "多团队协同", "工具链"]},
                {"phase": "4. 持续优化", "tasks": ["度量", "持续改进", "文化沉淀"]}
            ],
            "default_milestones": ["评估完成", "试点通过", "规模化启动", "成熟度达成"],
            "default_duration_weeks": 32
        },
        "is_global": True
    }
]


async def seed_templates():
    """初始化行业模板"""
    async with async_session_maker() as db:
        # 找一个超级管理员作为创建者
        result = await db.execute(select(User).where(User.is_superuser == True).limit(1))
        admin = result.scalar_one_or_none()
        if not admin:
            result = await db.execute(select(User).limit(1))
            admin = result.scalar_one_or_none()
        if not admin:
            print("ERROR: 系统无任何用户，无法初始化模板")
            return

        print(f"使用管理员: {admin.email or admin.id}")

        created_count = 0
        skipped_count = 0
        for tpl_data in INDUSTRY_TEMPLATES:
            # 检查是否已存在（按 name 去重）
            existing = await db.execute(
                select(TaskTemplate).where(TaskTemplate.name == tpl_data["name"])
            )
            if existing.scalar_one_or_none():
                print(f"  SKIP: {tpl_data['name']} 已存在")
                skipped_count += 1
                continue

            tpl = TaskTemplate(
                name=tpl_data["name"],
                description=tpl_data["description"],
                category=tpl_data["category"],
                fields=tpl_data["fields"],
                is_global=tpl_data.get("is_global", True),
                project_id=None,
                created_by=admin.id,
            )
            db.add(tpl)
            await db.commit()
            await db.refresh(tpl)
            print(f"  OK: {tpl_data['name']} (id={tpl.id})")
            created_count += 1

        print(f"\n创建: {created_count} 个，跳过: {skipped_count} 个，总计: {len(INDUSTRY_TEMPLATES)} 个")


async def main():
    print("=" * 60)
    print("PMI中国 AI-PM · 行业模板种子初始化")
    print("=" * 60)
    print(f"准备初始化 {len(INDUSTRY_TEMPLATES)} 个行业模板\n")
    await seed_templates()
    print("\n完成。前端可通过 GET /api/v1/task-templates/ 查看。")


if __name__ == "__main__":
    asyncio.run(main())
