"""
PMI中国AI项目管理社区 - API路由模块
"""

from fastapi import APIRouter
from app.api.v1 import auth, projects, tasks, custom_fields, automations, comments, notifications, attachments, webhooks, roles, members, reports, messages, ws, integrations, wiki, search, monitoring, compliance, exports, budgets, recurring_tasks, app_market, llm_configs, mcp, scheduled_jobs, zapier, forms, knowledge_base, okrs, documents, whiteboards, risk, resources, resource_allocations, system_llm_config, openclaw, api_keys, external, lessons, change_control, sprints, epics, releases, task_templates, predictions, brand_settings, ucm, dashboard_advice, kb_sharing, project_types, approvals, roadmap, profile
from app.api.v1 import top_aliases
from app.api.v1 import workflow_orchestrator
from app.api.v1 import events_ws, async_tasks
from app.api import tool_routes
from app.api import skill_routes
from app.api.v1.ai_routes import chat_router, agent_router, nlp_router, assist_router, monitor_router, pmbok_v3_router

# 加载异步 LLM handler 注册中心（导入即注册 5 类大模型异步任务）
import app.services.async_llm_handlers  # noqa: F401

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(projects.router, prefix="/projects", tags=["项目管理"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务管理"])
api_router.include_router(chat_router, tags=["AI功能"])
api_router.include_router(agent_router, tags=["AI Agent"])
api_router.include_router(nlp_router, tags=["NLP"])
api_router.include_router(assist_router, tags=["AI辅助填写"])
api_router.include_router(custom_fields.router, prefix="/custom-fields", tags=["自定义字段"])
api_router.include_router(automations.router, prefix="/automations", tags=["自动化规则"])
api_router.include_router(comments.router, prefix="", tags=["评论管理"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["通知管理"])
api_router.include_router(attachments.router, prefix="/attachments", tags=["附件管理"])
api_router.include_router(webhooks.router, tags=["Webhook管理"])
api_router.include_router(roles.router, tags=["角色管理"])
api_router.include_router(members.router, tags=["项目成员管理"])
api_router.include_router(reports.router, tags=["报表管理"])
api_router.include_router(messages.router, prefix="", tags=["消息管理"])
api_router.include_router(ws.router, prefix="", tags=["WebSocket"])
api_router.include_router(integrations.router, tags=["集成管理"])
api_router.include_router(wiki.router, prefix="/wiki", tags=["Wiki知识库"])
api_router.include_router(search.router, tags=["搜索"])
api_router.include_router(monitoring.router, tags=["监控"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["合规管理"])
api_router.include_router(budgets.router, tags=["预算管理"])
api_router.include_router(recurring_tasks.router, prefix="/recurring-tasks", tags=["重复任务"])
api_router.include_router(exports.export_router, prefix="/exports", tags=["数据导出"])
api_router.include_router(exports.import_router, prefix="/imports", tags=["数据导入"])
api_router.include_router(app_market.router, prefix="/app-market", tags=["应用市场"])
api_router.include_router(llm_configs.router, prefix="/llm-configs", tags=["LLM配置"])
api_router.include_router(mcp.router, tags=["MCP协议"])
api_router.include_router(scheduled_jobs.router, prefix="/scheduled-jobs", tags=["定时任务"])
api_router.include_router(forms.router, prefix="/forms", tags=["表单管理"])
api_router.include_router(zapier.router, tags=["Zapier集成"])
api_router.include_router(okrs.router, tags=["OKR目标管理"])
api_router.include_router(documents.router, tags=["文档管理"])
api_router.include_router(knowledge_base.router, tags=["知识库"])
api_router.include_router(kb_sharing.router, tags=["知识库分享"])
api_router.include_router(whiteboards.router, tags=["白板管理"])
api_router.include_router(risk.router, tags=["风险登记册"])
api_router.include_router(resources.router, tags=["资源管理"])
api_router.include_router(resource_allocations.router, tags=["资源排程"])
api_router.include_router(lessons.router, tags=["经验教训"])
api_router.include_router(change_control.router, tags=["变更控制"])
api_router.include_router(sprints.router, prefix="/sprints", tags=["Sprint管理"])
api_router.include_router(epics.router, prefix="/epics", tags=["Epic管理"])
api_router.include_router(releases.router, prefix="/releases", tags=["Release管理"])
api_router.include_router(task_templates.router, prefix="/task-templates", tags=["任务模板"])
api_router.include_router(predictions.router, tags=["AI预测分析"])
api_router.include_router(brand_settings.router, prefix="/system", tags=["系统设置-品牌"])
api_router.include_router(system_llm_config.router, prefix="/system", tags=["系统设置-大模型"])
api_router.include_router(api_keys.router, prefix="/system", tags=["系统设置-对外API"])
api_router.include_router(openclaw.router, prefix="/openclaw", tags=["OpenClaw集成"])
api_router.include_router(external.router, prefix="/external", tags=["对外统一API"])
api_router.include_router(monitor_router, prefix="", tags=["AI监控"])
api_router.include_router(dashboard_advice.router, tags=["仪表盘"])
api_router.include_router(workflow_orchestrator.router, tags=["工作流编排"])
api_router.include_router(pmbok_v3_router, tags=["pmbok-v3"])
api_router.include_router(tool_routes.router, tags=["工具技术"])
api_router.include_router(ucm.router, prefix="/ucm", tags=["用户管理"])
api_router.include_router(events_ws.router, prefix="", tags=["WebSocket-Events"])
api_router.include_router(async_tasks.router, prefix="", tags=["异步任务"])
# 顶层资源列表别名（GET /comments /budgets /stakeholders /deliverables）
api_router.include_router(top_aliases.router, tags=["顶层资源别名"])
api_router.include_router(project_types.router, prefix="/project-types", tags=["项目类型"])


# PMI中国版独有：审批流与路线图（2026-08-08 升级保留）
api_router.include_router(approvals.router, prefix="/approvals", tags=["审批流程"])
api_router.include_router(roadmap.router, tags=["产品路线图"])

from app.api import skill_routes
api_router.include_router(skill_routes.router, prefix="/skills", tags=["Skills管理"])
