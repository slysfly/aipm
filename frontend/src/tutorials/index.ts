import type { TourProps } from "antd";

// 每一步教程：标题 + 说明（支持纯文本），target 为 CSS 选择器（优先 data-tour 标记）
export interface TutorialStep {
  title: string;
  description: string;
  target?: string;
  placement?: TourProps["steps"][number]["placement"];
}

export interface TutorialEntry {
  title: string;
  steps: TutorialStep[];
}

// 路由路径 -> 教程内容。未命中 target 的步骤会以居中卡片展示（同样为动画分步教程）。
export const tutorials: Record<string, TutorialEntry> = {
  // ===== 概览 =====
  "/": {
    title: "仪表盘 Dashboard",
    steps: [
      { title: "欢迎来到PMI中国 AI-PM", description: "仪表盘汇总你所在项目的关键指标：任务进度、风险、预算、资源负载等。左上角可切换不同项目查看对应数据。", target: "[data-tour='dash-kpi']" },
      { title: "关注异常指标", description: "红色/橙色数字代表需要关注的风险、超支或延期项，点击对应卡片可跳转到明细页面。", target: "[data-tour='dash-kpi']" },
      { title: "实时刷新", description: "数据通过实时通道自动更新；若长时间未动，页面也会定期轮询，无需手动刷新。" },
    ],
  },
  "/projects": {
    title: "项目管理",
    steps: [
      { title: "项目列表", description: "这里展示你有权限的所有项目。点击卡片进入项目详情，查看该项目的任务、风险、资源等全量数据。", target: "[data-tour='proj-list']" },
      { title: "新建项目", description: "点击右上角「新建项目」按钮，填写名称、负责人、周期即可创建。创建后系统会自动初始化看板与默认迭代。", target: "[data-tour='proj-new']" },
      { title: "搜索与筛选", description: "使用顶部搜索框按名称检索，或用状态筛选快速定位进行中/已结项项目。" },
    ],
  },
  ProjectDetail: {
    title: "项目详情",
    steps: [
      { title: "项目关键指标", description: "KPI 卡片一屏呈现进度、预算执行、风险分布等核心指标，所有数据都围绕当前项目联动，是向干系人汇报的入口。", target: "[data-tour='pd-tabs']" },
      { title: "项目概览", description: "概览页给出进度、预算执行、风险分布等一屏看板，是向干系人汇报的入口。" },
      { title: "关联数据", description: "在项目下创建的任务、风险、资源分配都会自动带上本项目 ID，互相关联、互不串档。" },
    ],
  },

  // ===== 规划 =====
  "/tasks": {
    title: "任务管理",
    steps: [
      { title: "新建任务", description: "点击「新建任务」填写标题、负责人、优先级、截止日期与所属迭代。任务创建后进入下方列表。", target: "[data-tour='tasks-new']" },
      { title: "筛选与检索", description: "用状态、负责人、优先级等条件筛选；搜索框可按关键字快速定位任务。", target: "[data-tour='tasks-filter']" },
      { title: "表格操作", description: "在表格中可编辑、改状态、设依赖、删除任务；双击行打开详情。进度会汇总到仪表盘与 EVM。", target: "[data-tour='tasks-table']" },
    ],
  },
  "/kanban": {
    title: "看板 Kanban",
    steps: [
      { title: "拖拽流转", description: "卡片按状态分列（待办/进行中/已完成）。直接拖拽卡片即可改变任务状态，变更实时保存。" },
      { title: "切换项目/迭代", description: "顶部可切换查看不同项目或迭代的看板视图。", target: "[data-tour='kanban-sel']" },
      { title: "快速建卡", description: "在某一列点击「+」可快速新建该状态的任务。", target: "[data-tour='kanban-add']" },
    ],
  },
  "/portfolio": {
    title: "项目组合",
    steps: [
      { title: "组合视图", description: "从组合视角对比多个项目的健康度、进度与资源占用，辅助优先级决策。", target: "[data-tour='portfolio-matrix']" },
      { title: "钻取明细", description: "点击某个项目卡片可下钻到其详情与关键指标。", target: "[data-tour='portfolio-matrix']" },
    ],
  },
  "/okrs": {
    title: "目标与关键结果 OKR",
    steps: [
      { title: "设定目标 O", description: "点击「新建目标」填写本周期目标（Objective），可绑定到具体项目。", target: "[data-tour='okr-new']" },
      { title: "拆解关键结果 KR", description: "为每个目标添加若干可量化的关键结果（Key Results），填写权重与目标值。", target: "[data-tour='okr-quarter']" },
      { title: "跟踪进度", description: "定期更新 KR 当前值，系统自动计算目标完成度并在仪表盘呈现。" },
    ],
  },
  "/calendar": {
    title: "日历",
    steps: [
      { title: "时间视图", description: "以月/周/日视图查看任务截止、里程碑与资源排期，支持拖拽调整时间。", target: "[data-tour='cal-view']" },
      { title: "筛选维度", description: "可按成员、项目过滤日历事件，聚焦自己或团队的关键节点。", target: "[data-tour='cal-card']" },
    ],
  },
  "/sprints": {
    title: "迭代管理 Sprint",
    steps: [
      { title: "创建迭代", description: "点击「新建迭代」设定周期与目标速度（velocity），将任务纳入本轮冲刺。", target: "[data-tour='sprints-new']" },
      { title: "迭代看板", description: "查看本迭代任务分布与燃尽情况，评估是否能在周期内完成。", target: "[data-tour='sprints-list']" },
      { title: "复盘", description: "迭代结束后可标记完成并查看达成率，为下一轮规划提供依据。" },
    ],
  },
  "/critical-path": {
    title: "关键路径",
    steps: [
      { title: "依赖网络", description: "基于任务依赖关系（前置/后置）自动绘制关键路径图，识别决定工期的要害任务。", target: "[data-tour='cp-path']" },
      { title: "识别瓶颈", description: "加粗路径上的任务不可延期；鼠标悬停可查看其前后置依赖与缓冲。", target: "[data-tour='cp-path']" },
    ],
  },
  "/reports": {
    title: "报表",
    steps: [
      { title: "多维度报表", description: "选择报表类型（进度、成本、风险、资源等）与统计区间，一键生成图表。", target: "[data-tour='reports-type']" },
      { title: "导出", description: "支持将报表导出为图片或数据文件，用于周报与汇报材料。", target: "[data-tour='reports-export']" },
    ],
  },

  // ===== 管控体系 =====
  "/evm": {
    title: "挣值管理 EVM",
    steps: [
      { title: "选择项目", description: "在顶部选择项目，系统基于任务进度与预算实时计算 PV/EV/AC 等挣值指标。", target: "[data-tour='evm-sel']" },
      { title: "解读指标", description: "CPI<1 表示成本超支、SPI<1 表示进度滞后；图表直观展示偏差趋势。", target: "[data-tour='evm-dash']" },
      { title: "预测", description: "基于当前绩效预测完工估算 EAC 与完工偏差 VAC，辅助决策是否需纠偏。" },
    ],
  },
  "/risk": {
    title: "风险登记册",
    steps: [
      { title: "登记风险", description: "点击「新建风险」记录风险名称、类别、概率与影响，并填写应对策略与责任人。", target: "[data-tour='risk-new']" },
      { title: "风险矩阵", description: "系统按概率×影响自动计算风险等级，高等级风险以红色高亮提示。", target: "[data-tour='risk-table']" },
      { title: "跟踪与闭环", description: "更新风险状态（识别中/监控中/已关闭），记录应对动作形成闭环。" },
    ],
  },
  "/changes": {
    title: "变更控制",
    steps: [
      { title: "提交变更", description: "点击「新建变更请求」说明变更内容、影响范围与紧急程度，提交后进入评审流。", target: "[data-tour='changes-new']" },
      { title: "变更与里程碑", description: "本页同时展示项目里程碑。点击里程碑可查看达成状态与关联交付物。", target: "[data-tour='changes-list']" },
      { title: "审批闭环", description: "审批通过后变更生效，相关任务/预算自动联动更新。" },
    ],
  },
  "/lessons": {
    title: "经验教训",
    steps: [
      { title: "沉淀经验", description: "项目结项或阶段结束时，记录踩过的坑与可复用做法，形成组织过程资产。", target: "[data-tour='lessons-new']" },
      { title: "检索复用", description: "按项目或标签检索历史经验，在新项目中提前规避同类问题。", target: "[data-tour='lessons-cat']" },
    ],
  },
  "/resources": {
    title: "资源管理",
    steps: [
      { title: "维护资源池", description: "点击「新建资源」登记人员/设备的技能、成本费率与可用容量。", target: "[data-tour='res-new']" },
      { title: "资源分配", description: "在「分配」中将资源指派到具体任务，系统按容量校验是否过载。", target: "[data-tour='res-alloc']" },
      { title: "负载视图", description: "通过资源日历/负载图查看每人排期冲突，及时平衡工作量。" },
    ],
  },

  // ===== 工具 =====
  "/automations": {
    title: "自动化",
    steps: [
      { title: "创建自动化", description: "设定触发条件（如任务状态变更）与执行动作（如通知、改字段），实现重复操作自动化。", target: "[data-tour='auto-new']" },
      { title: "启用/停用", description: "可随时启停规则，查看每次触发的执行记录。", target: "[data-tour='auto-list']" },
    ],
  },
  "/webhooks": {
    title: "Webhook",
    steps: [
      { title: "配置回调", description: "添加一个接收地址（URL），选择关注的事件类型（任务/评论/变更等）。", target: "[data-tour='webhook-new']" },
      { title: "事件投递", description: "系统在该类事件发生时向你的服务推送 JSON 消息，用于与外部系统打通。", target: "[data-tour='webhook-list']" },
    ],
  },
  "/whiteboard": {
    title: "白板",
    steps: [
      { title: "新建白板", description: "点击「新建白板」打开画布，自由绘制流程图、思维导图或草图。", target: "[data-tour='whiteboard-add']" },
      { title: "协作与保存", description: "内容自动保存；可导出为图片或分享给他人协同编辑。", target: "[data-tour='whiteboard-canvas']" },
    ],
  },
  KnowledgeBase: {
    title: "知识库",
    steps: [
      { title: "新建知识库", description: "点击「新建知识库」创建分类（如某项目的文档仓），设置可见范围。", target: "[data-tour='kb-new']" },
      { title: "上传文档", description: "进入知识库后点击「上传」按钮（需有写入权限），支持 PDF/Word/Excel/图片等，系统自动解析并建立可检索片段。" },
      { title: "检索与预览", description: "用搜索框全文检索，点击文档可在线预览结构化内容（PDF 逐页、Office 转 HTML）。" },
    ],
  },
  "/notifications": {
    title: "通知",
    steps: [
      { title: "消息中心", description: "这里汇聚@提及、任务指派、变更审批等所有通知，未读数显示在顶部铃铛角标。", target: "[data-tour='noti-list']" },
      { title: "已读/处理", description: "点击单条可跳转关联对象；批量标记已读清理收件箱。", target: "[data-tour='noti-read']" },
    ],
  },
  "/settings": {
    title: "系统设置",
    steps: [
      { title: "个人与偏好", description: "在此修改资料、密码、语言与主题（浅色/深色）等个人偏好。", target: "[data-tour='settings-user']" },
      { title: "组织与集成", description: "管理员可配置组织信息、成员、第三方集成与权限策略。" },
    ],
  },

  // ===== AI / 智能 =====
  "/agents": {
    title: "PMBOK 智能体",
    steps: [
      { title: "选择知识单元", description: "勾选需要的 PMBOK 知识单元/领域智能体，开启「选用」开关即纳入后续运行。", target: "[data-tour='agents-tabs']" },
      { title: "运行物料", description: "点击「运行」选择输入文件，系统按勾选的智能体生成结构化交付物（如章程、WBS、风险清单）。", target: "[data-tour='agents-sel']" },
    ],
  },
  "/workflow": {
    title: "智能体工作流",
    steps: [
      { title: "编排流程", description: "将多个智能体串联成工作流，定义输入输出与串行/并行关系。", target: "[data-tour='workflow-add']" },
      { title: "执行与观测", description: "运行工作流并实时查看每个节点的产出与状态。", target: "[data-tour='workflow-run']" },
    ],
  },
  "/ai/wbs": {
    title: "AI 生成 WBS",
    steps: [
      { title: "输入项目目标", description: "填写项目背景与范围，AI 自动拆解工作分解结构（WBS）与任务建议。", target: "[data-tour='wbs-input']" },
      { title: "采纳结果", description: "校验生成的层级与任务，一键导入到项目任务列表。", target: "[data-tour='wbs-gen']" },
    ],
  },
  "/ai-monitor": {
    title: "AI 监控",
    steps: [
      { title: "运行态势", description: "查看 AI 调用量、耗时、成功率与异常告警，保障智能体服务稳定。", target: "[data-tour='ai-mon-kpi']" },
      { title: "追溯", description: "点击异常条目查看调用链与详情，便于定位问题。", target: "[data-tour='ai-mon-calls']" },
    ],
  },

  // ===== 运营管理（管理员）=====
  "/admin/dashboard": {
    title: "运营总览",
    steps: [
      { title: "全局指标", description: "查看平台用户数、项目数、活跃度与资源消耗等运营大盘。", target: "[data-tour='admin-dash-card']" },
      { title: "异常预警", description: "关注异常波动与告警，及时介入处理。" },
    ],
  },
  "/admin/organizations": {
    title: "组织管理",
    steps: [
      { title: "组织树", description: "维护公司/部门层级，下级组织可继承上级成员。", target: "[data-tour='admin-org-tree']" },
      { title: "成员管理", description: "在组织下添加成员并分配角色，支持模糊搜索与批量操作。", target: "[data-tour='admin-org-new']" },
    ],
  },
  "/admin/users": {
    title: "用户管理",
    steps: [
      { title: "用户列表", description: "查看与检索全部用户，管理账号状态、角色与组织归属。", target: "[data-tour='admin-users-list']" },
      { title: "权限分配", description: "为用户授予系统管理员/组织管理员/普通成员等角色。", target: "[data-tour='admin-users-sel']" },
    ],
  },
  "/admin/plans": {
    title: "套餐管理",
    steps: [
      { title: "套餐配置", description: "定义可售卖的套餐档位、额度与功能开关。", target: "[data-tour='admin-plans-new']" },
      { title: "订阅查看", description: "查看各组织当前订阅套餐与到期时间。", target: "[data-tour='admin-plans-list']" },
    ],
  },
  "/admin/grants": {
    title: "功能授权",
    steps: [
      { title: "功能开关", description: "为特定组织/用户开启或关闭高级功能（如 RAG、智能体）。", target: "[data-tour='admin-grants-list']" },
    ],
  },
  "/admin/billing": {
    title: "计费账单",
    steps: [
      { title: "账单查询", description: "查看各组织消费明细、账单周期与支付状态。", target: "[data-tour='admin-billing-tabs']" },
      { title: "对账", description: "导出账单用于财务对账。", target: "[data-tour='admin-billing-list']" },
    ],
  },
  "/admin/levels": {
    title: "用户级别",
    steps: [
      { title: "级别体系", description: "配置用户成长级别与对应权益阈值。", target: "[data-tour='admin-levels-new']" },
      { title: "晋升规则", description: "设定升级所需的行为/消费条件。", target: "[data-tour='admin-levels-list']" },
    ],
  },

  // ===== 兜底 =====
  "/404": {
    title: "页面未找到",
    steps: [
      { title: "返回首页", description: "当前路径不存在，点击左侧导航或右上角 Logo 返回工作台。" },
    ],
  },
};

// 将当前路由解析为注册表 key
export function resolveTourKey(pathname: string): string {
  if (pathname.startsWith("/projects/") && pathname !== "/projects") return "ProjectDetail";
  if (pathname === "/knowledge" || pathname === "/documents") return "KnowledgeBase";
  return pathname;
}
