import { get, post, put, del, downloadBlob, uploadForm } from "./http";

/* ---------------- 认证 ---------------- */
export const authApi = {
  login: (username: string, password: string) =>
    post<any>("/auth/login", { username, password }),
  register: (payload: any) => post<any>("/auth/register", payload),
  me: () => get<any>("/auth/me", undefined, undefined, true),  // 未登录时返回401是正常的，加 silent 避免控制台报错
  logout: () => post<any>("/auth/logout", {}),
};

/* ---------------- 项目 ---------------- */
export const projectApi = {
  list: (params?: any) => get<any>("/projects", params),
  get: (id: string) => get<any>(`/projects/${id}`),
  create: (payload: any) => post<any>("/projects", payload),
  update: (id: string, payload: any) => put<any>(`/projects/${id}`, payload),
  remove: (id: string) => del<any>(`/projects/${id}`),
  statistics: (id: string) => get<any>(`/projects/${id}/statistics`),
  criticalPath: (id: string) => get<any>(`/projects/${id}/critical-path`),
  networkDiagram: (id: string) => get<any>(`/projects/${id}/network-diagram`),
  // 异步触发：创建后台任务，立即返回 task_id，进度经 WebSocket 实时推送
  summarizeLessons: (id: string) => asyncTaskApi.create("summarize_lessons", { project_id: id }),
};

/* ---------------- 任务 ---------------- */
export const taskApi = {
  list: (params?: any) => get<any>("/tasks", params),
  get: (id: string) => get<any>(`/tasks/${id}`),
  create: (payload: any) => post<any>("/tasks", payload),
  update: (id: string, payload: any) => put<any>(`/tasks/${id}`, payload),
  remove: (id: string) => del<any>(`/tasks/${id}`),
  subtasks: (id: string) => get<any>(`/tasks/${id}/subtasks`),
  addDependency: (taskId: string, payload: { predecessor_id: string; successor_id: string; dependency_type?: string; lag_time?: number }) =>
    post<any>(`/tasks/${taskId}/dependencies`, payload),
  removeDependency: (taskId: string, depId: string) =>
    del<any>(`/tasks/${taskId}/dependencies/${depId}`),
};

/* ---------------- 异步任务 ---------------- */
// 统一异步任务入口：创建后台任务 -> 立即拿 task_id -> 前端经 WebSocket 订阅进度/结果。
// 任意大模型能力都走这里，避免前端阻塞等待（大模型推理通常 20~90s）。
export const asyncTaskApi = {
  create: (task_type: string, params: any) =>
    post<any>("/async-tasks", { task_type, params }),
  get: (task_id: string) => get<any>(`/async-tasks/${task_id}`),
};

/* ---------------- AI ---------------- */
// AI 生成类接口统一改为「异步触发」：端点仅创建后台任务并返回 task_id，
// 真正的推理在后台完成，进度经 WebSocket 实时推送（见 realtime/socket.ts）。
export const aiApi = {
  // 生成 WBS：payload 需含 project_name / project_description / industry_type / project_id / save_to_tasks
  generateWbs: (payload: any) => asyncTaskApi.create("generate_wbs", payload),
  chat: (payload: any) => post<any>("/ai/chat", payload, false, 180000),
  analyzeProject: (id: string) => asyncTaskApi.create("analyze_project", { project_id: id }),
  predictRisk: (id: string) => asyncTaskApi.create("predict_risk", { project_id: id }),
};

/* ---------------- 报表 ---------------- */
export const reportApi = {
  daily: (date?: string) => get<any>("/reports/daily", date ? { date } : undefined),
  weekly: (start?: string, end?: string) =>
    get<any>("/reports/weekly", { start, end }),
  projectStatus: (projectId: string, start?: string, end?: string) =>
    get<any>(`/reports/projects/${projectId}/status`, { start, end }),
  sendDaily: (payload: any) => post<any>("/reports/daily/send", payload),
  exportReport: (params: any) => downloadBlob("/reports/export", params),
  exportProjectPdf: (projectId: string) =>
    downloadBlob(`/exports/projects/${projectId}/report/pdf`),
  exportTasksExcel: (projectId: string, params?: any) =>
    downloadBlob(`/exports/projects/${projectId}/tasks/excel`, params),
  exportTasksCsv: (projectId: string, params?: any) =>
    downloadBlob(`/exports/projects/${projectId}/tasks/csv`, params),
};

/* ---------------- 自动化 ---------------- */
export const automationApi = {
  list: (params?: any) => get<any>("/automations", params),
  create: (payload: any) => post<any>("/automations", payload),
  update: (id: string, payload: any) => put<any>(`/automations/${id}`, payload),
  remove: (id: string) => del<any>(`/automations/${id}`),
  toggle: (id: string, isActive: boolean) =>
    put<any>(`/automations/${id}/toggle`, { is_active: isActive }),
  test: (id: string, payload: any) =>
    post<any>(`/automations/${id}/test`, payload),
};

/* ---------------- Webhook ---------------- */
export const webhookApi = {
  list: (params?: any) => get<any>("/webhooks", params),
  create: (payload: any) => post<any>("/webhooks", payload),
  update: (id: string, payload: any) => put<any>(`/webhooks/${id}`, payload),
  remove: (id: string) => del<any>(`/webhooks/${id}`),
  test: (id: string, payload?: any) =>
    post<any>(`/webhooks/${id}/test`, payload || {}),
  deliveries: (id: string, params?: any) =>
    get<any>(`/webhooks/${id}/deliveries`, params),
};


/* ---------------- 通知 ---------------- */
export const notificationApi = {
  list: (params?: any) => get<any>("/notifications", params),
  unreadCount: () => get<any>("/notifications/unread-count"),
  read: (id: string) => put<any>(`/notifications/${id}/read`),
  readAll: () => put<any>("/notifications/read-all"),
  remove: (id: string) => del<any>(`/notifications/${id}`),
};

/* ---------------- OKR 目标 ---------------- */
export const okrApi = {
  list: (params?: any) => get<any>("/okrs", params),
  get: (id: string) => get<any>(`/okrs/${id}`),
  create: (payload: any) => post<any>("/okrs", payload),
  update: (id: string, payload: any) => put<any>(`/okrs/${id}`, payload),
  remove: (id: string) => del<any>(`/okrs/${id}`),
  aiGenerateKrs: (okrId: string, payload?: any) => post<any>(`/okrs/${okrId}/ai-generate-krs`, payload || { count: 4 }),
};

/* ---------------- 可自定义项目类型 ---------------- */
export const projectTypeApi = {
  list: () => get<any>("/project-types"),
  create: (payload: any) => post<any>("/project-types", payload),
  update: (id: string, payload: any) => put<any>(`/project-types/${id}`, payload),
  remove: (id: string) => del<any>(`/project-types/${id}`),
};

/* ---------------- 文档 ---------------- */
export const docApi = {
  list: (params?: any) => get<any>("/documents", params),
  get: (id: string) => get<any>(`/documents/${id}`),
  create: (payload: any) => post<any>("/documents", payload),
  update: (id: string, payload: any) => put<any>(`/documents/${id}`, payload),
  remove: (id: string) => del<any>(`/documents/${id}`),
};

/* ---------------- 白板 ---------------- */
export const boardApi = {
  list: () => get<any>("/whiteboards"),
  get: (id: string) => get<any>(`/whiteboards/${id}`),
  save: (id: string, payload: any) => put<any>(`/whiteboards/${id}`, payload),
  create: (payload: any) => post<any>("/whiteboards", payload),
};


/* ---------------- 知识库 ---------------- */
export const knowledgeApi = {
  // 集合路由与后端保持一致带尾斜杠，避免依赖 307 跳转（否则反代/axios 不跟随时会 404/405）
  listBases: (scope?: string, extraParams?: { project_id?: string }) => {
    const params: any = {};
    if (scope) params.scope = scope;
    if (extraParams?.project_id) params.project_id = extraParams.project_id;
    const qs = new URLSearchParams(params).toString();
    return get<any>(`/knowledge-bases/${qs ? `?${qs}` : ""}`);
  },
  createBase: (payload: any) => post<any>("/knowledge-bases/", payload),
  deleteBase: (id: string) => del<any>(`/knowledge-bases/${id}`),
  listDocs: (kbId: string) => get<any>(`/knowledge-bases/${kbId}/documents`),
  getDoc: (kbId: string, docId: string) => get<any>(`/knowledge-bases/${kbId}/documents/${docId}`),
  addDoc: (kbId: string, payload: any) =>
    post<any>(`/knowledge-bases/${kbId}/documents`, payload),
  updateDoc: (kbId: string, docId: string, payload: any) =>
    put<any>(`/knowledge-bases/${kbId}/documents/${docId}`, payload),
  deleteDoc: (docId: string) => del<any>(`/knowledge-bases/documents/${docId}`),
  search: (kbId: string, payload: any) =>
    post<any>(`/knowledge-bases/${kbId}/search`, payload),
  qa: (kbId: string, payload: any) =>
    post<any>(`/knowledge-bases/${kbId}/qa`, payload),
  // 用户 / 用户组 / 分享 / 批量上传
  listUsers: (q?: string) => get<any>(`/kb-users${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  listGroups: () => get<any>("/user-groups"),
  createGroup: (payload: any) => post<any>("/user-groups", payload),
  getGroup: (gid: string) => get<any>(`/user-groups/${gid}`),
  addGroupMember: (gid: string, userId: string) =>
    post<any>(`/user-groups/${gid}/members`, { user_id: userId }),
  removeGroupMember: (gid: string, userId: string) =>
    del<any>(`/user-groups/${gid}/members/${userId}`),
  deleteGroup: (gid: string) => del<any>(`/user-groups/${gid}`),
  listShares: (kbId: string) => get<any>(`/knowledge-bases/${kbId}/shares`),
  addShare: (kbId: string, payload: any) =>
    post<any>(`/knowledge-bases/${kbId}/shares`, payload),
  removeShare: (kbId: string, shareId: string) =>
    del<any>(`/knowledge-bases/${kbId}/shares/${shareId}`),
  // 统一文件/文件夹上传：走 axios 实例（Bearer 兜底 + withCredentials Cookie 主通道 + 401 拦截），
  // 刷新后内存令牌为空也能凭 httpOnly Cookie 正常鉴权，文件随即进入 RAG 分块入库。
  // folder 传"完整相对目录"（如 mydocs/sub1），后端拼成 mydocs/sub1/file.txt 保留层级。
  uploadBatch: (kbId: string, files: File[], folder?: string) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (folder) form.append("folder", folder);
    return uploadForm<any>(`/knowledge-bases/${kbId}/documents/upload-batch`, form);
  },
  // AI 生成可用的知识库（公开库全系统可见 + 本人私密库）：单 scope 二选一
  listAiSelectable: () => get<any>("/knowledge-bases/ai-selectable"),
};

/* ---------------- Sprint ---------------- */
export const sprintApi = {
  list: (params?: any) => get<any>("/sprints", params),
  get: (id: string) => get<any>(`/sprints/${id}`),
  create: (payload: any) => post<any>("/sprints", payload),
  update: (id: string, payload: any) => put<any>(`/sprints/${id}`, payload),
  remove: (id: string) => del<any>(`/sprints/${id}`),
  start: (id: string) => post<any>(`/sprints/${id}/start`),
  complete: (id: string) => post<any>(`/sprints/${id}/complete`),
  addTask: (id: string, payload: any) => post<any>(`/sprints/${id}/tasks`, payload),
  removeTask: (id: string, taskId: string) => del<any>(`/sprints/${id}/tasks/${taskId}`),
  report: (id: string) => get<any>(`/sprints/${id}/report`),
  listTasks: (id: string) => get<any>(`/sprints/${id}/tasks`),
};

/* ---------------- 报表 / 分析 ---------------- */
export const analysisApi = {
  evm: (projectId: string, params?: any) =>
    get<any>("/reports/evm", { project_id: projectId, ...(params || {}) }),
  resourceUtilization: (projectId: string, params?: any) =>
    get<any>("/reports/resource-utilization", { project_id: projectId, ...(params || {}) }),
  riskTrend: (projectId: string, params?: any) =>
    get<any>("/reports/risk-trend", { project_id: projectId, ...(params || {}) }),
};

/* ---------------- 风险登记册 ---------------- */
export const riskApi = {
  list: (params?: any) => get<any>("/risks", params),
  get: (id: string) => get<any>(`/risks/${id}`),
  create: (payload: any) => post<any>("/risks", payload),
  update: (id: string, payload: any) => put<any>(`/risks/${id}`, payload),
  remove: (id: string) => del<any>(`/risks/${id}`),
};

/* ---------------- 资源管理 ---------------- */
export const resourceApi = {
  list: (params?: any) => get<any>("/resources", params),
  create: (payload: any) => post<any>("/resources", payload),
  update: (id: string, payload: any) => put<any>(`/resources/${id}`, payload),
  remove: (id: string) => del<any>(`/resources/${id}`),
  calendar: (params?: any) => get<any>("/resources/calendar", params),
};

/* ---------------- 资源排程（资源日历明细：用户提供基础信息 + AI 优化） ---------------- */
export const resourceAllocationApi = {
  list: (params?: any) => get<any>("/resource-allocations", params),
  create: (payload: any) => post<any>("/resource-allocations", payload),
  update: (id: string, payload: any) => put<any>(`/resource-allocations/${id}`, payload),
  remove: (id: string) => del<any>(`/resource-allocations/${id}`),
  /** 纯分析：返回建议列表，不修改任何数据。start_date/end_date 走 query。 */
  optimize: (payload: { project_id?: string; start_date: string; end_date: string }) =>
    post<any>(
      `/resource-allocations/optimize?start_date=${encodeURIComponent(payload.start_date)}&end_date=${encodeURIComponent(payload.end_date)}${payload.project_id ? `&project_id=${encodeURIComponent(payload.project_id)}` : ""}`,
      {},
      false,
      60000,
    ),
  /** 一次性应用一批建议：传完整建议对象（带 toStart/toEnd），或传 "all" 走批量简化模式 */
  applyOptimization: (payload: {
    suggestions?: any[];      // 来自 /optimize 的建议原样
    suggestion_ids?: string[] | "all";
    project_id?: string;
  }) => post<any>("/resource-allocations/optimize/apply", payload, false, 60000),
  undoAiMove: (id: string) => post<any>(`/resource-allocations/${id}/undo`, {}),
};

/* ---------------- 经验教训 ---------------- */
export const lessonApi = {
  list: (params?: any) => get<any>("/lessons", params),
  create: (payload: any) => post<any>("/lessons", payload),
  update: (id: string, payload: any) => put<any>(`/lessons/${id}`, payload),
  remove: (id: string) => del<any>(`/lessons/${id}`),
  archive: (id: string) => post<any>(`/lessons/${id}/archive`),
  archiveAll: () => post<any>("/lessons/archive-all"),
  generate: (payload: { topic: string; category?: string; kb_scope?: string; context_hint?: string }) =>
    post<any>("/lessons/generate", payload),
};

/* ---------------- 变更控制 ---------------- */
export const changeApi = {
  list: (params?: any) => get<any>("/change-requests", params),
  create: (payload: any) => post<any>("/change-requests", payload),
  update: (id: string, payload: any) => put<any>(`/change-requests/${id}`, payload),
  remove: (id: string) => del<any>(`/change-requests/${id}`),
  whitelist: () => get<any>("/change-requests/whitelist"),
  entities: (projectId: string) => get<any>(`/change-requests/entities/${projectId}`),
};

/* ---------------- AI Agent 能力目录 + 开箱 Agent ---------------- */
export const agentApi = {
  list: () => get<any>("/agents"),
  registry: () => get<any>("/agents/registry"),
  run: (payload: any) => post<any>("/agents/run", payload, false, 180000),
  runs: (params?: any) => get<any>("/agents/runs", params),
  getOverride: (id: string) => get<any>(`/agents/${encodeURIComponent(id)}/override`),
  putOverride: (id: string, payload: any) => put<any>(`/agents/${encodeURIComponent(id)}/override`, payload),
  deleteOverride: (id: string) => del<any>(`/agents/${encodeURIComponent(id)}/override`),
  // 物料驱动运行管线（结构化 ITTO：准备 → 生成模板 → 执行 → 产出文件）
  prepare: (id: string, payload: { project_id?: string }) =>
    post<any>(`/agents/${encodeURIComponent(id)}/prepare`, payload, false, 60000),
  generateTemplate: (id: string, payload: {
    project_id?: string; input_key: string; input_label: string;
    basic_info?: string; file_content?: string; file_name?: string;
  }) => post<any>(`/agents/${encodeURIComponent(id)}/generate-template`, payload, false, 120000),
  runMaterial: (id: string, payload: {
    project_id?: string; input_refs?: Record<string, string>;
    selected_tools?: string[]; user_input?: string;
  }) => post<any>(`/agents/${encodeURIComponent(id)}/run-material`, payload, false, 180000),
  listMaterials: (projectId?: string) =>
    get<any>(`/agents/materials${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),
  downloadMaterial: (ref: string, projectId?: string) =>
    downloadBlob(`/agents/materials/${encodeURIComponent(ref)}/download`, projectId ? { project_id: projectId } : undefined),
};

/* ---------------- 工作流可视编排（多租户） ---------------- */
export const workflowApi = {
  list: (params?: any) => get<any>("/workflows", params),
  get: (id: string) => get<any>(`/workflows/${id}`),
  create: (payload: any) => post<any>("/workflows", payload),
  update: (id: string, payload: any) => put<any>(`/workflows/${id}`, payload),
  remove: (id: string) => del<any>(`/workflows/${id}`),
  bind: (id: string, payload: any) => post<any>(`/workflows/${id}/bind`, payload),
  byProject: (projectId: string) => get<any>(`/workflows/project/${projectId}`),
  execute: (payload: any) => post<any>("/workflows/execute", payload, true, 600000),
  getRunStatus: (runId: string) => get<any>(`/workflows/runs/${runId}`),
  getRuns: (wfId: string) => get<any>(`/workflows/${wfId}/runs`),
  validate: (payload: any) => post<any>("/workflows/validate", payload, true, 60000),
  saveTemplate: (payload: any) => post<any>("/workflows/templates", payload),
  listTemplates: () => get<any>("/workflows/templates"),
};

/* ---------------- PMBOK 过程 Agent 目录 ---------------- */
export const pmbokApi = {
  catalog: () => get<any>("/agents/pmbok-catalog"),
};

/* ---------------- PMBOK 三件套（V3 数据驱动：Skill / Agent / Workflow / Principle） ----------------
 * 数据来源：后端 /api/v1/pmbok/* （见 backend/app/api/v1/ai_routes/pmbok_v3.py）
 * 与旧 pmbokApi（读硬编码 pmbok-catalog）并存，三件套新页面统一使用本模块。
 */
export const pmbokV3Api = {
  // 统计汇总：三件套数字 + 过程组完成度 + 知识领域覆盖
  stats: () => get<any>("/pmbok/stats"),
  // Skill 层（原子工具技术）：支持 process_group / knowledge_area / category / source_system / search 过滤
  skills: (params?: any) => get<any>("/pmbok/skills", params),
  skill: (id: string) => get<any>(`/pmbok/skills/${encodeURIComponent(id)}`),
  // Agent 层（角色/过程）：支持 process_group / knowledge_area / system / search 过滤
  agents: (params?: any) => get<any>("/pmbok/agents", params),
  agent: (id: string) => get<any>(`/pmbok/agents/${encodeURIComponent(id)}`),
  // Workflow 层（编排）
  workflows: () => get<any>("/pmbok/workflows"),
  workflow: (id: string) => get<any>(`/pmbok/workflows/${encodeURIComponent(id)}`),
  // Agent 槽位（ITTO 结构化）
  slots: (id: string) => get<any>(`/pmbok/slots/${encodeURIComponent(id)}`),
  // 原则层（v8 六原则 + 元原则）
  principles: () => get<any>("/pmbok/principles"),
};

/* ---------------- 仪表盘 · AI 下一步建议 ---------------- */
export const dashboardApi = {
  nextSteps: (payload?: { project_id?: string }) =>
    post<any>("/dashboard/next-steps", payload || {}, false, 180000),
};

export const approvalApi = {
  listFlows: (params?: any) => get<any>("/approvals/flows", params),
  createFlow: (payload: any) => post<any>("/approvals/flows", payload),
  updateFlow: (id: string, payload: any) => put<any>(`/approvals/flows/${id}`, payload),
  removeFlow: (id: string) => del<any>(`/approvals/flows/${id}`),
  activateFlow: (id: string) => post<any>(`/approvals/flows/${id}/activate`),
  deactivateFlow: (id: string) => post<any>(`/approvals/flows/${id}/deactivate`),
  listRequests: (params?: any) => get<any>("/approvals/requests", params),
  createRequest: (payload: any) => post<any>("/approvals/requests", payload),
  listPending: () => get<any>("/approvals/pending"),
  listProcessed: () => get<any>("/approvals/processed"),
  dashboard: () => get<any>("/approvals/dashboard"),
  approveStep: (stepId: string, payload: any) => post<any>(`/approvals/steps/${stepId}/approve`, payload),
  rejectStep: (stepId: string, payload: any) => post<any>(`/approvals/steps/${stepId}/reject`, payload),
};

/* ---------------- 报表 / 分析 ---------------- */

export const roadmapApi = {
  list: (params?: Record<string, string>) => get<any>("/roadmap", params),
  create: (payload: any) => post<any>("/roadmap", payload),
  update: (id: string, payload: any) => put<any>(`/roadmap/${id}`, payload),
  remove: (id: string) => del<any>(`/roadmap/${id}`),
  // 三视图专用
  dashboardSummary: (params?: Record<string, string>) => get<any>("/roadmap/dashboard/summary", params),
  valueStreamMap: (params?: Record<string, string>) => get<any>("/roadmap/value-stream/map", params),
  techRoadmapTimeline: (params?: Record<string, string>) => get<any>("/roadmap/tech-roadmap/timeline", params),
  releaseBoard: (params?: Record<string, string>) => get<any>("/roadmap/release/board", params),
};

/* ---------------- AI Agent 能力目录 + 开箱 Agent ---------------- */
