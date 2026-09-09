import React, { lazy, Suspense, useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import { Spin } from "antd";
import { useAuth } from "./store/AuthContext";
import MainLayout from "./layout/MainLayout";
import GlobalAssistant from "./components/GlobalAssistant";
import LoadingSkeleton from "./components/LoadingSkeleton";
import { connectRealtime } from "./realtime/socket";

// 路由懒加载 — 每个页面独立 chunk，按需加载
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Projects = lazy(() => import("./pages/Projects"));
const ProjectDetail = lazy(() => import("./pages/ProjectDetail"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Kanban = lazy(() => import("./pages/Kanban"));
const AIWBS = lazy(() => import("./pages/AIWBS"));
const OKRs = lazy(() => import("./pages/OKRs"));
const Calendar = lazy(() => import("./pages/Calendar"));
const Reports = lazy(() => import("./pages/Reports"));
const Automations = lazy(() => import("./pages/Automations"));
const Webhooks = lazy(() => import("./pages/Webhooks"));
const Whiteboard = lazy(() => import("./pages/Whiteboard"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Settings = lazy(() => import("./pages/Settings"));
const Portfolio = lazy(() => import("./pages/Portfolio"));
const RiskRegister = lazy(() => import("./pages/RiskRegister"));
const LessonsLearned = lazy(() => import("./pages/LessonsLearned"));
const ChangeControl = lazy(() => import("./pages/ChangeControl"));
const EVM = lazy(() => import("./pages/EVM"));
const SprintManagement = lazy(() => import("./pages/SprintManagement"));
const CriticalPathRoadmap = lazy(() => import("./pages/CriticalPathRoadmap"));
const ResourceManagement = lazy(() => import("./pages/ResourceManagement"));
const AgentPanel = lazy(() => import("./pages/AgentPanel"));
const KnowledgeBase = lazy(() => import("./pages/KnowledgeBase"));
const AgentWorkflow = lazy(() => import("./pages/AgentWorkflow"));
const PmbokAgents = lazy(() => import("./pages/PmbokAgents"));
const AIMonitor = lazy(() => import("./pages/AIMonitor"));
const PmbokSkills = lazy(() => import("./pages/PmbokSkills"));
const WorkflowAugmented = lazy(() => import("./pages/WorkflowAugmented/WorkflowAugmented"));
const ProductRoadmap = lazy(() => import("./pages/ProductRoadmap"));
const ApprovalFlow = lazy(() => import("./pages/ApprovalFlow"));
const NotFound = lazy(() => import("./pages/NotFound"));

// 用户管理子系统 (UCM) 页面
const AdminDashboard = lazy(() => import("./pages/admin/OperationDashboard"));
const OrganizationManagement = lazy(() => import("./pages/admin/OrganizationManagement"));
const UserManagement = lazy(() => import("./pages/admin/UserManagement"));
const PlanManagement = lazy(() => import("./pages/admin/PlanManagement"));
const FeatureGrants = lazy(() => import("./pages/admin/FeatureGrants"));
const BillingManagement = lazy(() => import("./pages/admin/BillingManagement"));
const LevelManagement = lazy(() => import("./pages/admin/LevelManagement"));

const App: React.FC = () => {
  const { token, user, loading } = useAuth();
  const location = useLocation();

  // 登录后建立全局实时通道（后台任务进度 / 数据变更 / 通知实时推送）
  useEffect(() => {
    if (token) connectRealtime();
  }, [token]);

  // 路由守卫：运营管理 /admin/* 至少需要 is_superuser 或 is_org_admin
  const isAdminPath = location.pathname.startsWith("/admin");
  const hasAdminAccess = !!user && (!!user.is_superuser || !!user.is_org_admin);
  const guardedRedirect = isAdminPath && !hasAdminAccess;

  if (loading) {
    return (
        <div style={{
          display: "flex", justifyContent: "center", alignItems: "center",
          height: "100vh", background: "var(--content-bg, #F8FAFC)",
        }}>
          <div style={{ textAlign: "center" }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, color: "#64748B", fontSize: 14 }}>PMI中国 项目管理 加载中...</div>
          </div>
        </div>
    );
  }

  if (!token) {
    return (
      <Suspense fallback={<LoadingSkeleton type="form" rows={1} columns={1} header={false} />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/roadmap" element={<ProductRoadmap />} />
        <Route path="/approvals" element={<ApprovalFlow />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <>
    <MainLayout>
      <ErrorBoundary key={location.pathname} resetKey={location.pathname}>
      <Suspense fallback={<LoadingSkeleton />}>
      <Routes>
        {guardedRedirect ? (
          <Route path="*" element={<Navigate to="/" replace />} />
        ) : (
          <>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/kanban" element={<Kanban />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/risk" element={<RiskRegister />} />
        <Route path="/changes" element={<ChangeControl />} />
        <Route path="/lessons" element={<LessonsLearned />} />
        <Route path="/evm" element={<EVM />} />
        <Route path="/sprints" element={<SprintManagement />} />
        <Route path="/critical-path" element={<CriticalPathRoadmap />} />
        <Route path="/resources" element={<ResourceManagement />} />
        <Route path="/agents" element={<PmbokAgents />} />
        <Route path="/pmbok-skills" element={<PmbokSkills />} />
        <Route path="/workflow" element={<AgentWorkflow />} />
        <Route path="/workflow-augmented" element={<WorkflowAugmented />} />
        <Route path="/ai/wbs" element={<AIWBS />} />
        <Route path="/okrs" element={<OKRs />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/automations" element={<Automations />} />
        <Route path="/webhooks" element={<Webhooks />} />
        <Route path="/whiteboard" element={<Whiteboard />} />
        <Route path="/documents" element={<KnowledgeBase />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/knowledge" element={<KnowledgeBase />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/admin/dashboard" element={<AdminDashboard />} />
        <Route path="/admin/organizations" element={<OrganizationManagement />} />
        <Route path="/admin/users" element={<UserManagement />} />
        <Route path="/admin/plans" element={<PlanManagement />} />
        <Route path="/admin/grants" element={<FeatureGrants />} />
        <Route path="/admin/billing" element={<BillingManagement />} />
        <Route path="/admin/levels" element={<LevelManagement />} />
        <Route path="/ai-monitor" element={<AIMonitor />} />
        <Route path="/404" element={<NotFound />} />
        <Route path="*" element={<NotFound />} />
          </>
        )}
      </Routes>
      </Suspense>
      </ErrorBoundary>
    </MainLayout>
    <GlobalAssistant />
    </>
  );
};

export default App;
