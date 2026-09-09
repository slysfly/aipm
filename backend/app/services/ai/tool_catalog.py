"""
PMBOK工具技术目录 - 定义所有PMBOK过程中使用的工具技术及其输出模板
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

class ToolCategory(str, Enum):
    GATHERING = "收集数据"
    ANALYSIS = "分析数据"
    DECISION = "决策"
    COMMUNICATION = "沟通"
    MODELLING = "建模"
    ESTIMATING = "估算"
    SCHEDULING = "进度管理"
    COST = "成本估算"
    MONITORING = "监控"
    EXPERT = "专家判断"

@dataclass
class ToolResultTemplate:
    format: str
    title: str
    description: str
    fields: List[Dict[str, str]]
    example: str

@dataclass
class ToolDefinition:
    id: str
    name: str
    name_en: str
    category: ToolCategory
    description: str
    input_types: List[str]
    output_formats: List[str]
    results_template: ToolResultTemplate
    processes: List[str] = field(default_factory=list)
    usage_notes: str = ""

TOOL_CATALOG: Dict[str, ToolDefinition] = {}
PROCESS_TOOLS: Dict[str, List[str]] = {}

def _register_tool(tool: ToolDefinition):
    TOOL_CATALOG[tool.id] = tool
    for proc_id in tool.processes:
        if proc_id not in PROCESS_TOOLS:
            PROCESS_TOOLS[proc_id] = []
        PROCESS_TOOLS[proc_id].append(tool.id)

def list_tools() -> List[ToolDefinition]:
    return list(TOOL_CATALOG.values())

def get_tool(tool_id: str) -> Optional[ToolDefinition]:
    return TOOL_CATALOG.get(tool_id)

def get_tools_for_process(process_id: str) -> List[ToolDefinition]:
    tool_ids = PROCESS_TOOLS.get(process_id, [])
    return [TOOL_CATALOG[tid] for tid in tool_ids if tid in TOOL_CATALOG]

def generate_tool_output(tool_id: str, data: Dict[str, Any]) -> str:
    tool = get_tool(tool_id)
    if not tool:
        return f"工具 {tool_id} 不存在"
    template = tool.results_template
    lines = []
    lines.append(f"# {template.title}")
    lines.append("")
    lines.append(f"**工具**: {tool.name} ({tool.name_en})")
    lines.append("")
    lines.append(f"**描述**: {template.description}")
    lines.append("")
    if data:
        lines.append("## 输入数据")
        lines.append("")
        for k, v in data.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    lines.append("## 输出模板")
    lines.append("")
    lines.append(template.example)
    return "\n".join(lines)

# ============================================================
# 收集数据类工具
# ============================================================

_register_tool(ToolDefinition(
    id="interview",
    name="访谈",
    name_en="Interview",
    category=ToolCategory.GATHERING,
    description="与利益相关方进行结构化或半结构化对话，收集需求、期望和信息。",
    input_types=["stakeholder_list", "questions", "meeting_notes"],
    output_formats=["text", "table"],
    results_template=ToolResultTemplate(
        format="table",
        title="访谈记录表",
        description="记录访谈对象、时间、地点、讨论要点和关键结论",
        fields=[
            {"name": "interviewee", "label": "访谈对象", "type": "str"},
            {"name": "role", "label": "角色", "type": "str"},
            {"name": "date", "label": "日期", "type": "date"},
            {"name": "topic", "label": "讨论主题", "type": "str"},
            {"name": "key_points", "label": "关键要点", "type": "str"},
            {"name": "action_items", "label": "行动项", "type": "str"}
        ],
        example="""| 访谈对象 | 角色 | 日期 | 讨论主题 | 关键要点 | 行动项 |
|---------|------|------|---------|---------|--------|
| 张三 | 项目发起人 | 2026-08-28 | 项目目标 | 希望6个月内上线MVP版本 | 准备项目章程初稿 |
| 李四 | 技术负责人 | 2026-08-28 | 技术方案 | 建议采用微服务架构 | 评估技术可行性 |"""
    ),
    processes=["1.2 Identify Stakeholders", "4.1 Plan Project Management", "5.2 Collect Requirements"],
    usage_notes="访谈前需准备访谈大纲，明确访谈目的和问题清单。访谈后及时整理记录，提炼关键信息。"
))

_register_tool(ToolDefinition(
    id="focus_group",
    name="焦点小组",
    name_en="Focus Group",
    category=ToolCategory.GATHERING,
    description="召集预先选定的利益相关方，由专业引导师主持，进行互动式讨论以收集需求。",
    input_types=["participant_list", "discussion_guide", "facilitator_notes"],
    output_formats=["text", "list"],
    results_template=ToolResultTemplate(
        format="list",
        title="焦点小组讨论记录",
        description="记录讨论主题、参与者观点、共识点和分歧点",
        fields=[
            {"name": "topic", "label": "讨论主题", "type": "str"},
            {"name": "participants", "label": "参与人员", "type": "list"},
            {"name": "viewpoints", "label": "主要观点", "type": "list"},
            {"name": "consensus", "label": "达成共识", "type": "list"},
            {"name": "disagreements", "label": "分歧点", "type": "list"}
        ],
        example="""## 焦点小组讨论记录

讨论主题：产品功能优先级
参与人员：产品经理、技术代表、用户代表（共8人）

主要观点：
1. 用户代表：搜索功能最重要
2. 技术代表：系统稳定性优先
3. 产品经理：需要快速迭代验证

达成共识：
- MVP版本包含核心搜索功能
- 系统稳定性作为基础要求

分歧点：
- 个性化推荐功能的优先级"""
    ),
    processes=["5.2 Collect Requirements"],
    usage_notes="焦点小组通常需要专业引导师，人数控制在6-10人，讨论时间1-2小时。"
))

_register_tool(ToolDefinition(
    id="questionnaire",
    name="问卷调查",
    name_en="Questionnaire/Survey",
    category=ToolCategory.GATHERING,
    description="设计结构化问卷，向大量利益相关方收集意见和需求。",
    input_types=["question_list", "target_audience", "distribution_channel"],
    output_formats=["table", "chart"],
    results_template=ToolResultTemplate(
        format="table",
        title="问卷统计结果",
        description="汇总问卷回复数据，展示关键统计指标",
        fields=[
            {"name": "question", "label": "问题", "type": "str"},
            {"name": "option_a", "label": "选项A(%)", "type": "num"},
            {"name": "option_b", "label": "选项B(%)", "type": "num"},
            {"name": "option_c", "label": "选项C(%)", "type": "num"},
            {"name": "total_responses", "label": "总回复数", "type": "num"}
        ],
        example="""| 问题 | 选项A(%) | 选项B(%) | 选项C(%) | 总回复数 |
|------|----------|----------|----------|----------|
| 项目优先级 | 高(45%) | 中(35%) | 低(20%) | 120 |
| 预算容忍度 | 可追加(30%) | 固定(50%) | 看情况(20%) | 120 |
| 延期接受度 | 不接受(60%) | 最多1月(30%) | 可协商(10%) | 120 |"""
    ),
    processes=["5.2 Collect Requirements", "10.1 Plan Communications"],
    usage_notes="问卷设计要避免引导性提问，样本量应满足统计显著性要求。"
))

# ============================================================
# 分析数据类工具
# ============================================================

_register_tool(ToolDefinition(
    id="root_cause_analysis",
    name="根本原因分析",
    name_en="Root Cause Analysis",
    category=ToolCategory.ANALYSIS,
    description="通过系统方法识别问题的根本原因，常用工具包括鱼骨图、5Why分析法。",
    input_types=["problem_statement", "issue_list", "cause_categories"],
    output_formats=["tree", "text"],
    results_template=ToolResultTemplate(
        format="tree",
        title="根本原因分析树",
        description="展示问题与根本原因之间的层级关系",
        fields=[
            {"name": "problem", "label": "问题描述", "type": "str"},
            {"name": "cause_1", "label": "主要原因1", "type": "str"},
            {"name": "cause_2", "label": "主要原因2", "type": "str"},
            {"name": "root_cause", "label": "根本原因", "type": "str"}
        ],
        example="""问题：项目进度延期

├── 原因1：需求变更频繁
│   └── 根本原因：需求收集不充分，干系人参与不足
│
├── 原因2：资源不足
│   └── 根本原因：资源规划时未考虑人员流动
│
└── 原因3：技术难度低估
    └── 根本原因：缺乏技术预研和POC验证"""
    ),
    processes=["7.1 Plan Quality", "11.2 Manage Risks", "12.3 Control Risks"],
    usage_notes="根本原因分析要深入到底层原因，不要停留在表面现象。建议使用5Why方法连续追问。"
))

_register_tool(ToolDefinition(
    id="swot_analysis",
    name="SWOT分析",
    name_en="SWOT Analysis",
    category=ToolCategory.ANALYSIS,
    description="分析项目的优势(Strengths)、劣势(Weaknesses)、机会(Opportunities)和威胁(Threats)。",
    input_types=["project_context", "internal_factors", "external_factors"],
    output_formats=["matrix"],
    results_template=ToolResultTemplate(
        format="matrix",
        title="SWOT分析矩阵",
        description="四维矩阵展示项目的内外部环境因素",
        fields=[
            {"name": "strengths", "label": "优势", "type": "list"},
            {"name": "weaknesses", "label": "劣势", "type": "list"},
            {"name": "opportunities", "label": "机会", "type": "list"},
            {"name": "threats", "label": "威胁", "type": "list"}
        ],
        example="""┌─────────────┬─────────────┐
│   内部      │   外部      │
│  (可控)     │  (不可控)   │
├─────────────┼─────────────┤
│ 优势(S)     │ 机会(O)     │
│ • 团队资深  │ • 政策支持  │
│ • 技术成熟  │ • 市场增长  │
├─────────────┼─────────────┤
│ 劣势(W)     │ 威胁(T)     │
│ • 预算有限  │ • 竞争激烈  │
│ • 时间紧张  │ • 技术迭代  │
└─────────────┴─────────────┘"""
    ),
    processes=["4.1 Plan Project Management", "11.1 Identify Risks"],
    usage_notes="SWOT分析应结合定量数据，避免主观臆断。每个维度至少列出3-5项。"
))

_register_tool(ToolDefinition(
    id="stakeholder_analysis",
    name="利益相关方分析",
    name_en="Stakeholder Analysis",
    category=ToolCategory.ANALYSIS,
    description="评估利益相关方的影响力、利益度和态度，制定相应的管理策略。",
    input_types=["stakeholder_list", "power_interest_grid"],
    output_formats=["matrix", "table"],
    results_template=ToolResultTemplate(
        format="matrix",
        title="利益相关方权力利益矩阵",
        description="根据权力(影响力)和利益两个维度对利益相关方进行分类",
        fields=[
            {"name": "stakeholder", "label": "利益相关方", "type": "str"},
            {"name": "power", "label": "权力/影响力", "type": "enum"},
            {"name": "interest", "label": "利益/关注", "type": "enum"},
            {"name": "attitude", "label": "态度", "type": "enum"},
            {"name": "strategy", "label": "管理策略", "type": "str"}
        ],
        example="""┌──────────────┬───────┬───────┬────────┬─────────────────────┐
│ 利益相关方   │ 权力  │ 利益  │ 态度   │ 管理策略            │
├──────────────┼───────┼───────┼────────┼─────────────────────┤
│ 项目发起人   │ 高    │ 高    │ 支持   │ 重点管理，密切沟通  │
│ 客户代表     │ 高    │ 高    │ 中立   │ 重点管理，引导支持  │
│ 技术负责人   │ 中    │ 高    │ 支持   │ 保持沟通，充分参与  │
│ 最终用户     │ 低    │ 高    │ 中立   │ Keeping informed    │
│ 竞争对手     │ 低    │ 低    │ 反对   │ 最少努力监督        │
└──────────────┴───────┴───────┴────────┴─────────────────────┘"""
    ),
    processes=["1.2 Identify Stakeholders"],
    usage_notes="利益相关方分析是动态的，项目不同阶段需要重新评估。重点关注权力高、利益高的干系人。"
))

# ============================================================
# 决策类工具
# ============================================================

_register_tool(ToolDefinition(
    id="multicriteria_decision",
    name="多标准决策分析",
    name_en="Multicriteria Decision Analysis",
    category=ToolCategory.DECISION,
    description="使用决策矩阵，基于多个标准对选项进行系统性评估和选择。",
    input_types=["alternatives", "criteria", "weights", "scores"],
    output_formats=["table", "chart"],
    results_template=ToolResultTemplate(
        format="table",
        title="多标准决策分析矩阵",
        description="展示各备选方案在不同评价标准下的得分及加权总分",
        fields=[
            {"name": "alternative", "label": "备选方案", "type": "str"},
            {"name": "criteria_list", "label": "评价标准", "type": "list"},
            {"name": "weighted_score", "label": "加权总分", "type": "num"}
        ],
        example="""| 备选方案 | 成本(30%) | 技术(40%) | 风险(20%) | 时间(10%) | 加权总分 |
|---------|-----------|-----------|-----------|-----------|----------|
| 方案A   | 8×0.3=2.4 | 9×0.4=3.6 | 7×0.2=1.4 | 8×0.1=0.8 | **8.2**  |
| 方案B   | 9×0.3=2.7 | 7×0.4=2.8 | 8×0.2=1.6 | 6×0.1=0.6 | **7.7**  |
| 方案C   | 6×0.3=1.8 | 8×0.4=3.2 | 9×0.2=1.8 | 7×0.1=0.7 | **7.5**  |

推荐：方案A（加权总分最高）"""
    ),
    processes=["4.1 Plan Project Management", "6.2 Define Activities", "8.1 Plan Resource"],
    usage_notes="权重设置应基于项目目标和组织战略，可邀请关键干系人参与权重打分。"
))

_register_tool(ToolDefinition(
    id="voting",
    name="投票",
    name_en="Voting",
    category=ToolCategory.DECISION,
    description="通过多数决、相对多数决或众数法等投票技术做出集体决策。",
    input_types=["options", "voters", "vote_method"],
    output_formats=["table", "chart"],
    results_template=ToolResultTemplate(
        format="table",
        title="投票结果",
        description="记录投票选项、票数及最终结果",
        fields=[
            {"name": "option", "label": "选项", "type": "str"},
            {"name": "votes", "label": "票数", "type": "num"},
            {"name": "percentage", "label": "占比", "type": "str"},
            {"name": "result", "label": "结果", "type": "enum"}
        ],
        example="""| 选项 | 票数 | 占比 | 结果 |
|------|------|------|------|
| 敏捷开发 | 12票 | 60% | ✅ 通过 |
| 瀑布模式 | 6票 | 30% | ❌ 未通过 |
| 混合模式 | 2票 | 10% | ❌ 未通过 |

决策方法：相对多数决（Plurality）
参与人数：20人
投票结果：敏捷开发方案以60%支持率通过"""
    ),
    processes=["4.1 Plan Project Management", "5.2 Collect Requirements"],
    usage_notes="投票适用于意见分歧较大、需要快速决策的场景。重要决策建议采用德尔菲技术替代。"
))

# ============================================================
# 估算类工具
# ============================================================

_register_tool(ToolDefinition(
    id="three_point_estimating",
    name="三点估算",
    name_en="Three-Point Estimating",
    category=ToolCategory.ESTIMATING,
    description="使用最乐观(O)、最可能(M)、最悲观(P)三个estimate计算期望值，降低估算风险。",
    input_types=["optimistic", "most_likely", "pessimistic", "distribution_type"],
    output_formats=["table", "text"],
    results_template=ToolResultTemplate(
        format="table",
        title="三点估算结果",
        description="展示各活动的三点估算值及期望工期",
        fields=[
            {"name": "activity", "label": "活动", "type": "str"},
            {"name": "optimistic", "label": "最乐观(O)", "type": "num"},
            {"name": "most_likely", "label": "最可能(M)", "type": "num"},
            {"name": "pessimistic", "label": "最悲观(P)", "type": "num"},
            {"name": "expected", "label": "期望值", "type": "num"},
            {"name": "range", "label": "估算范围", "type": "str"}
        ],
        example="""| 活动 | 最乐观 | 最可能 | 最悲观 | 期望值(β) | 范围 |
|------|--------|--------|--------|-----------|------|
| 需求分析 | 5天 | 7天 | 15天 | 8天 | [5,15] |
| 系统设计 | 7天 | 10天 | 20天 | 12天 | [7,20] |
| 编码实现 | 10天 | 15天 | 25天 | 16.7天 | [10,25] |
| 测试 | 5天 | 8天 | 14天 | 8.5天 | [5,14] |

公式：期望值 = (O + 4M + P) / 6
分布类型：Beta分布（PERT）"""
    ),
    processes=["6.4 Estimate Activity Durations", "7.1 Estimate Costs"],
    usage_notes="三点估算需要历史数据支撑，若缺乏历史数据可采用类比估算补充。"
))

_register_tool(ToolDefinition(
    id="analogous_estimating",
    name="类比估算",
    name_en="Analogous Estimating",
    category=ToolCategory.ESTIMATING,
    description="基于相似项目的历史数据进行参数或非参数估算，速度快但精度较低。",
    input_types=["historical_data", "project_parameters", "adjustment_factors"],
    output_formats=["table", "text"],
    results_template=ToolResultTemplate(
        format="table",
        title="类比估算参考表",
        description="展示历史项目数据与当前项目的对比参数",
        fields=[
            {"name": "reference_project", "label": "参考项目", "type": "str"},
            {"name": "duration", "label": "工期(天)", "type": "num"},
            {"name": "budget", "label": "预算(万元)", "type": "num"},
            {"name": "team_size", "label": "团队规模", "type": "num"},
            {"name": "adjustment", "label": "调整系数", "type": "num"},
            {"name": "estimate", "label": "估算值", "type": "num"}
        ],
        example="""| 参考项目 | 工期 | 预算 | 团队规模 | 调整系数 | 估算值 |
|---------|------|------|---------|---------|--------|
| 项目A(相似) | 120天 | 200万 | 15人 | 1.0 | 120天/200万 |
| 项目B(类似) | 90天 | 150万 | 12人 | 0.9 | 108天/180万 |
| 项目C(参考) | 150天 | 300万 | 20人 | 1.2 | 180天/360万 |

最终估算：取加权平均值
工期：约136天，预算：约247万
置信区间：±20%"""
    ),
    processes=["6.4 Estimate Activity Durations", "7.1 Estimate Costs"],
    usage_notes="类比估算适用于项目早期阶段，随着项目信息逐步明确，应切换到更精确的估算方法。"
))

# ============================================================
# 进度管理类工具
# ============================================================

_register_tool(ToolDefinition(
    id="predecessor_diagramming",
    name="紧前关系绘图法",
    name_en="Precedence Diagramming Method (PDM)",
    category=ToolCategory.SCHEDULING,
    description="使用节点表示活动、箭头表示依赖关系的网络图绘制技术，支持四种依赖关系。",
    input_types=["activity_list", "dependencies", "logic_rules"],
    output_formats=["tree", "text"],
    results_template=ToolResultTemplate(
        format="tree",
        title="项目网络图(PDM)",
        description="展示活动间的依赖关系和关键路径",
        fields=[
            {"name": "activity_id", "label": "活动ID", "type": "str"},
            {"name": "activity_name", "label": "活动名称", "type": "str"},
            {"name": "predecessors", "label": "紧前活动", "type": "list"},
            {"name": "duration", "label": "工期", "type": "num"},
            {"name": "early_start", "label": "最早开始", "type": "num"},
            {"name": "early_finish", "label": "最早完成", "type": "num"},
            {"name": "late_start", "label": "最晚开始", "type": "num"},
            {"name": "late_finish", "label": "最晚完成", "type": "num"},
            {"name": "float", "label": "浮动时间", "type": "num"},
            {"name": "critical", "label": "是否关键", "type": "bool"}
        ],
        example="""活动网络图：

    A(5天) ──→ C(8天) ──→ E(6天) ──→ G(4天)
      │                                      │
      └──→ B(3天) ──→ D(7天) ──→ F(5天) ──→┘
                                    │
                                    └──→ H(2天)

关键路径：A → C → E → G = 23天
浮动时间：
• A: 0 (关键)
• B: 3天浮动
• C: 0 (关键)
• D: 1天浮动
• E: 0 (关键)
• F: 2天浮动
• G: 0 (关键)
• H: 5天浮动"""
    ),
    processes=["6.3 Sequence Activities"],
    usage_notes="PDM支持四种依赖关系：FS(完成-开始)、FF(完成-完成)、SS(开始-开始)、SF(开始-完成)，其中FS最常用。"
))

_register_tool(ToolDefinition(
    id="critical_path_method",
    name="关键路径法",
    name_en="Critical Path Method (CPM)",
    category=ToolCategory.SCHEDULING,
    description="识别项目中工期最长的路径（关键路径），确定项目最短工期和关键活动。",
    input_types=["network_diagram", "activity_durations", "dependencies"],
    output_formats=["text", "table"],
    results_template=ToolResultTemplate(
        format="table",
        title="关键路径分析表",
        description="计算关键路径、浮动时间和各活动的时间参数",
        fields=[
            {"name": "activity", "label": "活动", "type": "str"},
            {"name": "duration", "label": "工期", "type": "num"},
            {"name": "ES", "label": "最早开始", "type": "num"},
            {"name": "EF", "label": "最早完成", "type": "num"},
            {"name": "LS", "label": "最晚开始", "type": "num"},
            {"name": "LF", "label": "最晚完成", "type": "num"},
            {"name": "float", "label": "总浮动", "type": "num"},
            {"name": "status", "label": "状态", "type": "enum"}
        ],
        example="""| 活动 | 工期 | ES | EF | LS | LF | 浮动 | 状态 |
|------|------|-----|-----|-----|-----|------|------|
| A    | 5天  | 0   | 5   | 0   | 5   | 0    | 🔴关键 |
| B    | 3天  | 0   | 3   | 2   | 5   | 2    | ⚪非关键 |
| C    | 8天  | 5   | 13  | 5   | 13  | 0    | 🔴关键 |
| D    | 7天  | 3   | 10  | 6   | 13  | 3    | ⚪非关键 |
| E    | 6天  | 13  | 19  | 13  | 19  | 0    | 🔴关键 |
| F    | 5天  | 10  | 15  | 14  | 19  | 4    | ⚪非关键 |
| G    | 4天  | 19  | 23  | 19  | 23  | 0    | 🔴关键 |

关键路径：A → C → E → G = 23天
项目工期：23天
可用于赶工的关键活动：A, C, E, G"""
    ),
    processes=["6.4 Develop Schedule"],
    usage_notes="关键路径上的活动延迟会导致整个项目延迟。资源优化时应优先保障关键路径活动。"
))

# ============================================================
# 挣值管理类工具
# ============================================================

_register_tool(ToolDefinition(
    id="earned_value_analysis",
    name="挣值分析",
    name_en="Earned Value Analysis (EVA)",
    category=ToolCategory.MONITORING,
    description="通过PV、EV、AC三个基本参数计算CV、SV、CPI、SPI等指标，综合评估项目绩效。",
    input_types=["pv", "ev", "ac", "bac"],
    output_formats=["table", "chart", "text"],
    results_template=ToolResultTemplate(
        format="chart",
        title="挣值分析绩效报告",
        description="展示项目进度和成本的绩效指标及趋势预测",
        fields=[
            {"name": "metric", "label": "指标", "type": "str"},
            {"name": "value", "label": "值", "type": "num"},
            {"name": "interpretation", "label": "解读", "type": "str"},
            {"name": "status", "label": "状态", "type": "enum"}
        ],
        example="""┌─────────────────────────────────────────────────────┐
│                   挣值分析绩效报告                    │
├─────────────────────────────────────────────────────┤
│ 基本参数：                                          │
│   PV(计划价值) = ¥100,000                           │
│   EV(挣值)     = ¥85,000                           │
│   AC(实际成本) = ¥95,000                           │
│   BAC(完工预算) = ¥500,000                         │
├─────────────────────────────────────────────────────┤
│ 绩效指标：                                          │
│   CV(成本偏差)   = EV - AC = -¥10,000  ⚠️超支      │
│   SV(进度偏差)   = EV - PV = -¥15,000  ⚠️落后      │
│   CPI(成本绩效)  = EV/AC = 0.89       ⚠️<1异常    │
│   SPI(进度绩效)  = EV/PV = 0.85       ⚠️<1异常    │
├─────────────────────────────────────────────────────┤
│ 预测指标：                                          │
│   EAC(完工估算)  = BAC/CPI = ¥561,798             │
│   ETC(完工尚需)  = EAC - AC = ¥466,798            │
│   VAC(完工偏差)  = BAC - EAC = -¥61,798           │
└─────────────────────────────────────────────────────┘"""
    ),
    processes=["7.3 Control Costs", "7.4 Estimate Costs", "11.3 Monitor Risks"],
    usage_notes="挣值分析需要准确的EV数据，建议按里程碑或时间周期收集。CPI和SPI同时小于1时需引起高度重视。"
))

_register_tool(ToolDefinition(
    id="trend_analysis",
    name="趋势分析",
    name_en="Trend Analysis",
    category=ToolCategory.MONITORING,
    description="分析历史数据的变化趋势，预测项目未来的绩效走向。",
    input_types=["historical_data", "metrics_series", "forecast_periods"],
    output_formats=["chart", "text"],
    results_template=ToolResultTemplate(
        format="text",
        title="趋势分析报告",
        description="展示关键指标的历史走势和未来预测",
        fields=[
            {"name": "metric", "label": "指标", "type": "str"},
            {"name": "history", "label": "历史数据", "type": "list"},
            {"name": "trend", "label": "趋势方向", "type": "enum"},
            {"name": "forecast", "label": "预测值", "type": "num"}
        ],
        example="""趋势分析：CPI (成本绩效指数)

历史数据（近6个月）：
月份  CPI
01月  1.05
02月  1.02
03月  0.98
04月  0.95
05月  0.91
06月  0.88

趋势方向：下降 ↘️
预测结论：按当前趋势，预计下月CPI降至0.85以下
建议措施：立即审查成本超支原因，采取纠偏措施"""
    ),
    processes=["7.3 Control Costs", "7.4 Estimate Costs", "11.3 Monitor Risks"],
    usage_notes="趋势分析需要至少3-6个月的历史数据才能得出可靠结论。应结合多种指标综合判断。"
))

# ============================================================
# 其他常用工具
# ============================================================

_register_tool(ToolDefinition(
    id="expert_judgment",
    name="专家判断",
    name_en="Expert Judgment",
    category=ToolCategory.EXPERT,
    description="征询具备专业知识或受过专门培训的专家的意见，用于估算、决策和质量标准制定。",
    input_types=["expertise_area", "questions", "evaluation_criteria"],
    output_formats=["text", "table"],
    results_template=ToolResultTemplate(
        format="text",
        title="专家判断记录",
        description="记录专家意见、判断依据和建议措施",
        fields=[
            {"name": "expert", "label": "专家姓名", "type": "str"},
            {"name": "expertise", "label": "专业领域", "type": "str"},
            {"name": "question", "label": "咨询问题", "type": "str"},
            {"name": "judgment", "label": "判断意见", "type": "str"},
            {"name": "basis", "label": "判断依据", "type": "str"},
            {"name": "recommendation", "label": "建议措施", "type": "str"}
        ],
        example="""专家判断记录：

专家：王工（资深架构师，15年经验）
专业领域：系统架构、技术选型

咨询问题：推荐微服务还是单体架构？

判断意见：建议采用微服务架构

判断依据：
1. 系统规模大，预计3年后用户量翻倍
2. 团队有Kubernetes运维经验
3. 业务模块耦合度低，适合拆分

建议措施：
1. 首期搭建服务治理框架
2. 按领域驱动设计划分微服务边界
3. 建立CI/CD流水线支持独立部署"""
    ),
    processes=["4.1 Plan Project Management", "6.4 Estimate Activity Durations", "7.1 Estimate Costs", "8.1 Plan Resources"],
    usage_notes="专家判断应记录判断依据，避免主观武断。建议征询多位专家意见并对比分析。"
))

_register_tool(ToolDefinition(
    id="brainstorming",
    name="头脑风暴",
    name_en="Brainstorming",
    category=ToolCategory.GATHERING,
    description="召集团队成员自由发散思维，产生大量创意和解决方案，不急于评判。",
    input_types=["topic", "participants", "time_limit"],
    output_formats=["list", "text"],
    results_template=ToolResultTemplate(
        format="list",
        title="头脑风暴成果汇总",
        description="记录产生的所有创意想法，按类别整理",
        fields=[
            {"name": "idea", "label": "创意想法", "type": "str"},
            {"name": "category", "label": "类别", "type": "str"},
            {"name": "feasibility", "label": "可行性", "type": "enum"},
            {"name": "novelty", "label": "创新性", "type": "enum"}
        ],
        example="""头脑风暴成果：主题「如何提高用户留存率」

【产品功能类】
1. 引入成就系统 - 可行性：高 - 创新性：中
2. 社交互动功能 - 可行性：高 - 创新性：中
3. 个性化推荐 - 可行性：中 - 创新性：高

【运营策略类】
4. 新用户奖励计划 - 可行性：高 - 创新性：低
5. 推送提醒机制 - 可行性：高 - 创新性：低
6. 会员等级体系 - 可行性：中 - 创新性：中

【技术创新类】
7. AR互动体验 - 可行性：低 - 创新性：高
8. AI智能助手 - 可行性：中 - 创新性：高

下一步：对可行性高的想法进行详细评估"""
    ),
    processes=["5.2 Collect Requirements", "11.1 Identify Risks", "12.1 Plan Risk Responses"],
    usage_notes="头脑风暴应遵循'暂缓评判'原则，鼓励大胆设想。建议后续用亲和图整理分类。"
))

_register_tool(ToolDefinition(
    id="decomposition",
    name="分解",
    name_en="Decomposition",
    category=ToolCategory.MODELLING,
    description="将项目可交付成果逐级分解为更小的、更易管理的组成部分。",
    input_types=["deliverable", "hierarchy_rules", "work_packages"],
    output_formats=["tree", "text"],
    results_template=ToolResultTemplate(
        format="tree",
        title="工作分解结构(WBS)",
        description="树状展示项目范围的层级分解",
        fields=[
            {"name": "level", "label": "层级", "type": "num"},
            {"name": "code", "label": "编码", "type": "str"},
            {"name": "name", "label": "名称", "type": "str"},
            {"name": "description", "label": "描述", "type": "str"},
            {"name": "owner", "label": "负责人", "type": "str"}
        ],
        example="""工作分解结构（WBS）

1.0 项目
├── 1.1 启动阶段
│   ├── 1.1.1 项目章程
│   └── 1.1.2 启动会议
├── 1.2 规划阶段
│   ├── 1.2.1 项目管理计划
│   ├── 1.2.2 需求规格说明书
│   └── 1.2.3 设计文档
├── 1.3 执行阶段
│   ├── 1.3.1 前端开发
│   │   ├── 1.3.1.1 UI组件库
│   │   └── 1.3.1.2 页面开发
│   └── 1.3.2 后端开发
│       ├── 1.3.2.1 API接口
│       └── 1.3.2.2 数据库设计
└── 1.4 收尾阶段
    ├── 1.4.1 验收测试
    └── 1.4.2 项目总结"""
    ),
    processes=["4.1 Plan Project Management", "5.1 Define Scope", "6.2 Define Activities"],
    usage_notes="WBS分解应遵循100%规则，确保下层之和等于上层。建议分解到工作包级别（80小时以内）。"
))

_register_tool(ToolDefinition(
    id="alternatives_analysis",
    name="备选方案分析",
    name_en="Alternatives Analysis",
    category=ToolCategory.ANALYSIS,
    description="识别和评估多个备选方案，选择最优解决方案。",
    input_types=["problem_statement", "constraints", "criteria"],
    output_formats=["table", "text"],
    results_template=ToolResultTemplate(
        format="table",
        title="备选方案对比表",
        description="多维度对比各备选方案的优劣",
        fields=[
            {"name": "alternative", "label": "备选方案", "type": "str"},
            {"name": "advantages", "label": "优点", "type": "str"},
            {"name": "disadvantages", "label": "缺点", "type": "str"},
            {"name": "cost", "label": "成本", "type": "num"},
            {"name": "risk", "label": "风险等级", "type": "enum"}
        ],
        example="""| 备选方案 | 优点 | 缺点 | 成本 | 风险 |
|---------|------|------|------|------|
| 自建团队 | 自主可控、知识沉淀 | 招聘周期长、管理成本高 | 高 | 中 |
| 外包开发 | 快速启动、专业能力强 | 沟通成本高、知识流失 | 中 | 高 |
| 采购产品 | 开箱即用、实施快 | 定制受限、依赖供应商 | 低 | 低 |

推荐：采购产品（风险最低、成本可控）"""
    ),
    processes=["4.1 Plan Project Management", "6.2 Define Activities"],
    usage_notes="备选方案分析应客观全面，避免确认偏误。建议邀请多方利益相关方参与评审。"
))

_register_tool(ToolDefinition(
    id="reserve_analysis",
    name="应急储备分析",
    name_en="Reserve Analysis",
    category=ToolCategory.COST,
    description="确定应急储备和管理储备的数额，应对不确定性和未知风险。",
    input_types=["risk_register", "contingency_factors", "management_reserve_rate"],
    output_formats=["table", "text"],
    results_template=ToolResultTemplate(
        format="table",
        title="储备分析表",
        description="计算应急储备和管理储备金额",
        fields=[
            {"name": "item", "label": "项目", "type": "str"},
            {"name": "base_estimate", "label": "基础估算", "type": "num"},
            {"name": "contingency", "label": "应急储备", "type": "num"},
            {"name": "management_reserve", "label": "管理储备", "type": "num"},
            {"name": "total", "label": "总计", "type": "num"}
        ],
        example="""| 项目 | 基础估算 | 应急储备(10%) | 管理储备(5%) | 总计 |
|------|----------|---------------|--------------|------|
| 硬件采购 | ¥100,000 | ¥10,000 | ¥5,000 | ¥115,000 |
| 软件开发 | ¥200,000 | ¥20,000 | ¥10,000 | ¥230,000 |
| 培训实施 | ¥50,000 | ¥5,000 | ¥2,500 | ¥57,500 |
| 合计 | ¥350,000 | ¥35,000 | ¥17,500 | ¥402,500 |

应急储备：纳入成本基准，由项目经理审批使用
管理储备：不包含在成本基准，需高层审批"""
    ),
    processes=["7.1 Estimate Costs", "7.2 Determine Budget"],
    usage_notes="应急储备基于已知风险计算，管理储备应对未知风险。两者审批权限不同。"
))

_register_tool(ToolDefinition(
    id="data_analysis",
    name="数据分析",
    name_en="Data Analysis",
    category=ToolCategory.ANALYSIS,
    description="运用统计分析方法处理项目数据，发现规律、识别问题、支持决策。",
    input_types=["dataset", "analysis_type", "statistical_methods"],
    output_formats=["table", "chart", "text"],
    results_template=ToolResultTemplate(
        format="table",
        title="数据分析结果",
        description="展示统计分析的关键发现和洞察",
        fields=[
            {"name": "analysis_item", "label": "分析项", "type": "str"},
            {"name": "method", "label": "分析方法", "type": "str"},
            {"name": "result", "label": "分析结果", "type": "str"},
            {"name": "insight", "label": "洞察结论", "type": "str"}
        ],
        example="""| 分析项 | 分析方法 | 分析结果 | 洞察结论 |
|--------|----------|----------|----------|
| 进度偏差 | 回归分析 | R²=0.85 | 工期与人员数量强相关 |
| 成本超支 | 帕累托分析 | 前20%原因导致80%超支 | 重点管控供应商变更 |
| 质量缺陷 | 控制图 | 超出控制限 | 过程不稳定，需改进 |
| 风险排序 | 敏感性分析 | 技术风险影响最大 | 优先制定应对策略 |"""
    ),
    processes=["7.3 Control Costs", "11.3 Monitor Risks", "8.2 Estimate Activities"],
    usage_notes="数据分析应选择适合的方法，确保样本量充足。结果应与业务判断相结合。"
))

_register_tool(ToolDefinition(
    id="meetings",
    name="会议",
    name_en="Meetings",
    category=ToolCategory.COMMUNICATION,
    description="通过正式或非正式会议促进沟通、协调和决策。",
    input_types=["meeting_type", "agenda", "participants", "objectives"],
    output_formats=["text", "table"],
    results_template=ToolResultTemplate(
        format="table",
        title="会议纪要",
        description="记录会议基本信息、讨论内容和决议事项",
        fields=[
            {"name": "meeting_info", "label": "会议信息", "type": "str"},
            {"name": "attendees", "label": "参会人员", "type": "list"},
            {"name": "topics", "label": "讨论议题", "type": "list"},
            {"name": "decisions", "label": "决议事项", "type": "list"},
            {"name": "action_items", "label": "待办事项", "type": "list"}
        ],
        example="""会议纪要

会议主题：项目周例会
时间：2026-08-28 14:00-15:00
地点：会议室A / 线上会议
参会人：项目经理、技术负责人、产品负责人、测试负责人

讨论议题：
1. 本周进度汇报
2. 技术风险讨论
3. 下周计划安排

决议事项：
1. 同意采用微服务架构方案
2. 增加2名后端开发人员
3. 下周进行安全扫描

待办事项：
• 技术负责人：周三前完成架构设计文档
• 产品经理：周五前确认需求优先级
• 项目经理：更新项目计划"""
    ),
    processes=["4.1 Plan Project Management", "10.1 Plan Communications", "10.2 Manage Communications"],
    usage_notes="会议应有明确议程和时间控制，会后及时发出纪要并跟踪待办事项。"
))

# 初始化统计
print(f"PMBOK工具目录已加载，共 {len(TOOL_CATALOG)} 个工具定义")
print(f"涉及过程数：{len(PROCESS_TOOLS)} 个")

# ============================================================
# PMBOK 128工具扩展注册
# 数据来源: pmbok_tools_full.json
# 创建时间: 2026-08-28
# ============================================================

# 由于文件较大，这里采用动态加载方式
# 实际生产环境请在后端启动时加载 pmbok_tools_full.json

import json
import os

def load_pmbok_tools_from_json():
    """从JSON文件加载PMBOK工具"""
    json_path = "/opt/AI-PM/backend/data/tool_library/pmbok_tools_full.json"
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('tools', [])
    return []

def register_extended_tools():
    """注册扩展工具到catalog"""
    tools = load_pmbok_tools_from_json()
    registered = 0
    for tool_data in tools:
        tool_id = tool_data.get('id')
        if tool_id and tool_id not in TOOL_CATALOG:
            # 创建简化版ToolDefinition
            tool = ToolDefinition(
                id=tool_id,
                name=tool_data.get('name', ''),
                name_en=tool_data.get('name_en', ''),
                category=getattr(ToolCategory, tool_data.get('category', 'ANALYSIS'), ToolCategory.ANALYSIS),
                description=tool_data.get('description', ''),
                input_types=[],
                output_formats=['markdown', 'text'],
                results_template=ToolResultTemplate(
                    format='markdown',
                    title=tool_data.get('name', ''),
                    description=tool_data.get('description', ''),
                    fields=[],
                    example=f"""## {tool_data.get('name', '')} ({tool_data.get('name_en', '')})

**类别**: {tool_data.get('category', 'ANALYSIS')}

**描述**: {tool_data.get('description', '')}

**适用过程**: {', '.join(tool_data.get('processes', []))}"""
                ),
                processes=tool_data.get('processes', []),
                usage_notes=""
            )
            _register_tool(tool)
            registered += 1
    return registered

# 启动时自动加载
_loaded_count = register_extended_tools()
print(f"PMBOK扩展工具已加载: {_loaded_count} 个")
