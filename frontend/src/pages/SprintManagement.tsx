import React, { useState, useEffect, useCallback } from "react";
import {
  Card, Typography, Row, Col, Tag, Button, Progress, Space, Empty, App,
  Statistic, Table, Select, Form, Input, DatePicker, InputNumber, Modal,
  Tooltip, Tabs, Divider, Spin, List, Popconfirm, Collapse, Badge, Switch,
} from "antd";
import {
  PlusOutlined, CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined,
  PlayCircleOutlined, DeleteOutlined, FireOutlined, LineChartOutlined,
  AimOutlined, FileTextOutlined, TeamOutlined, ThunderboltOutlined,
  EditOutlined, MinusCircleOutlined, ReloadOutlined,
} from "@ant-design/icons";
import { motion, AnimatePresence } from "framer-motion";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import { sprintApi, projectApi, taskApi } from "../api";

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SprintTaskSummary {
  task_id: string;
  title: string;
  status: string;
  priority?: string | number;
  completed: boolean;
}

interface SprintReport {
  sprint_id: string;
  total_tasks: number;
  completed_tasks: number;
  burndown_data: { date: string; remaining: number; ideal: number; actual: number }[];
  burnup_data: { date: string; total: number; completed: number; ideal: number }[];
  velocity: number;
  capacity: number;
  completion_rate: number;
  acceptance_plan: string | null;
  tasks_summary: SprintTaskSummary[];
}

interface Sprint {
  id: string;
  name: string;
  goal: string;
  startDate: string;
  endDate: string;
  status: string;
  velocity: number;
  capacity: number;
  projectId: string;
  acceptancePlan?: string;
}

const pct = (c: number, t: number) => (t > 0 ? Math.round((c / t) * 100) : 0);

const STATUS_MAP: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  planning: { color: "blue", icon: <ClockCircleOutlined />, label: "规划中" },
  active:   { color: "green", icon: <PlayCircleOutlined />, label: "进行中" },
  completed:{ color: "default", icon: <CheckCircleOutlined />, label: "已完成" },
  cancelled:{ color: "red", icon: <CloseCircleOutlined />, label: "已取消" },
};

const TASK_STATUS_MAP: Record<string, { color: string; label: string }> = {
  todo:      { color: "default", label: "待办" },
  active:    { color: "processing", label: "进行中" },
  done:      { color: "success", label: "完成" },
  blocked:   { color: "error", label: "阻塞" },
  review:    { color: "warning", label: "评审中" },
};

// ---------------------------------------------------------------------------
// Chart Components
// ---------------------------------------------------------------------------

const BurndownChart: React.FC<{ data: SprintReport }> = ({ data }) => {
  const dates = data.burndown_data.map(d => d.date);
  const actual = data.burndown_data.map(d => d.actual ?? d.remaining);
  const ideal = data.burndown_data.map(d => d.ideal);

  const option = {
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    legend: { data: ["实际剩余", "理想线"], bottom: 0 },
    grid: { top: 20, right: 30, bottom: 36, left: 50 },
    xAxis: { type: "category", data: dates, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: "value", name: "剩余任务数", minInterval: 1 },
    series: [
      {
        name: "实际剩余",
        type: "line",
        data: actual,
        smooth: true,
        lineStyle: { width: 3, color: "#4F46E5" },
        areaStyle: { color: "rgba(79,70,229,0.12)" },
        itemStyle: { color: "#4F46E5" },
        symbol: "circle",
        symbolSize: 6,
      },
      {
        name: "理想线",
        type: "line",
        data: ideal,
        lineStyle: { width: 2, color: "#94A3B8", type: "dashed" },
        itemStyle: { color: "#94A3B8" },
        symbol: "none",
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 280 }} notMerge lazyUpdate />;
};

const BurnupChart: React.FC<{ data: SprintReport }> = ({ data }) => {
  if (!data.burnup_data?.length) return <Empty description="暂无燃起图数据" />;

  const dates = data.burnup_data.map(d => d.date);
  const completed = data.burnup_data.map(d => d.completed);
  const total = data.burnup_data.map(d => d.total);
  const ideal = data.burnup_data.map(d => d.ideal);

  const option = {
    tooltip: { trigger: "axis" },
    legend: { data: ["累计完成", "总 Scope", "理想完成"], bottom: 0 },
    grid: { top: 20, right: 30, bottom: 36, left: 50 },
    xAxis: { type: "category", data: dates, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: "value", name: "任务数", minInterval: 1 },
    series: [
      {
        name: "累计完成",
        type: "line",
        data: completed,
        smooth: true,
        lineStyle: { width: 3, color: "#10B981" },
        areaStyle: { color: "rgba(16,185,129,0.12)" },
        itemStyle: { color: "#10B981" },
        symbolSize: 5,
      },
      {
        name: "总 Scope",
        type: "line",
        data: total,
        lineStyle: { width: 2, color: "#F59E0B" },
        step: "end",
        itemStyle: { color: "#F59E0B" },
        symbolSize: 4,
      },
      {
        name: "理想完成",
        type: "line",
        data: ideal,
        lineStyle: { width: 2, color: "#94A3B8", type: "dashed" },
        symbol: "none",
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 280 }} notMerge lazyUpdate />;
};

const VelocityChart: React.FC<{ sprints: Sprint[] }> = ({ sprints }) => {
  const finished = sprints.filter(s => s.status !== "planning");
  if (!finished.length) return <Empty description="暂无速度数据" />;

  const names = finished.map(s => s.name);
  const velocities = finished.map(s => s.velocity || 0);
  const capacities = finished.map(s => s.capacity || 0);

  const option = {
    tooltip: { trigger: "axis" },
    legend: { data: ["实际速度", "承诺产能"], bottom: 0 },
    grid: { top: 20, right: 30, bottom: 36, left: 50 },
    xAxis: { type: "category", data: names, axisLabel: { fontSize: 11, rotate: 15 } },
    yAxis: { type: "value", name: "故事点/任务数" },
    series: [
      {
        name: "实际速度",
        type: "bar",
        data: velocities,
        itemStyle: {
          color: (params: any) => velocities[params.dataIndex] >= capacities[params.dataIndex] * 0.8
            ? "#10B981" : velocities[params.dataIndex] >= capacities[params.dataIndex] * 0.5 ? "#F59E0B" : "#EF4444",
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 40,
      },
      {
        name: "承诺产能",
        type: "line",
        data: capacities,
        lineStyle: { width: 2, color: "#6366F1", type: "dashed" },
        itemStyle: { color: "#6366F1" },
        symbol: "circle",
        symbolSize: 7,
      },
    ],
  };
  return <ReactECharts option={option} style={{ height: 260 }} notMerge lazyUpdate />;
};

// ---------------------------------------------------------------------------
// Task Association Panel
// ---------------------------------------------------------------------------

const TaskAssociationPanel: React.FC<{
  sprintId: string;
  projectId: string;
  tasks: SprintTaskSummary[];
  onRefresh: () => void;
}> = ({ sprintId, projectId, tasks, onRefresh }) => {
  const { message } = App.useApp();
  const [adding, setAdding] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [availableTasks, setAvailableTasks] = useState<any[]>([]);
  const [loadingTasks, setLoadingTasks] = useState(false);

  // Load available tasks (not yet in this sprint)
  const loadAvailable = useCallback(async () => {
    setLoadingTasks(true);
    try {
      const r: any = await taskApi.list({ project_id: projectId, limit: 200 });
      const all: any[] = r?.items || [];
      const inSprint = new Set(tasks.map(t => t.task_id));
      let filtered = all.filter((t: any) => !inSprint.has(t.id));
      if (searchText) {
        const q = searchText.toLowerCase();
        filtered = filtered.filter((t: any) =>
          (t.title || "").toLowerCase().includes(q)
        );
      }
      setAvailableTasks(filtered.slice(0, 20));
    } catch { /* silent */ }
    finally { setLoadingTasks(false); }
  }, [projectId, tasks, searchText]);

  useEffect(() => { loadAvailable(); }, [loadAvailable]);

  const handleAdd = async (taskId: string) => {
    setAdding(true);
    try {
      await sprintApi.addTask(sprintId, { task_id: taskId });
      message.success("任务已添加到 Sprint");
      onRefresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "添加失败");
    } finally { setAdding(false); }
  };

  const handleRemove = async (taskId: string) => {
    try {
      await sprintApi.removeTask(sprintId, taskId);
      message.success("任务已移除");
      onRefresh();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "移除失败");
    }
  };

  const doneCount = tasks.filter(t => t.completed).length;

  return (
    <div>
      {/* Summary bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Space>
          <TeamOutlined style={{ color: "#6366F1" }} />
          <Text strong>关联任务</Text>
          <Badge count={doneCount} style={{ backgroundColor: "#10B981" }} />
          <Text type="secondary">/ {tasks.length} 已完成</Text>
        </Space>
        <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
      </div>

      {/* Current tasks */}
      <List
        size="small"
        dataSource={tasks}
        locale={{ emptyText: "暂无关联任务，请在下方添加" }}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Popconfirm title="从 Sprint 移除？" onConfirm={() => handleRemove(item.task_id)}>
                <Button size="small" type="text" danger icon={<MinusCircleOutlined />} />
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={
                <Tag color={TASK_STATUS_MAP[item.status]?.color || "default"} style={{ borderRadius: 4 }}>
                  {TASK_STATUS_MAP[item.status]?.label || item.status}
                </Tag>
              }
              title={<span style={{ fontSize: 13 }}>{item.title}</span>}
              description={
                <Space size={8}>
                  {item.priority && <Tag>{String(item.priority)}</Tag>}
                  {item.completed && <CheckCircleOutlined style={{ color: "#10B981" }} />}
                </Space>
              }
            />
          </List.Item>
        )}
        style={{ marginBottom: 12, maxHeight: 240, overflowY: "auto" }}
      />

      {/* Add task */}
      <Divider style={{ margin: "8px 0" }} />
      <Input.Search
        placeholder="搜索项目中的任务..."
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
        enterButton="搜索"
        allowClear
        size="small"
        style={{ marginBottom: 8 }}
      />
      <Spin spinning={loadingTasks}>
        <List
          size="small"
          dataSource={availableTasks}
          locale={{ emptyText: searchText ? "未匹配到任务" : "所有任务已在 Sprint 中" }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  size="small"
                  type="link"
                  icon={<PlusOutlined />}
                  loading={adding}
                  onClick={() => handleAdd(item.id)}
                >添加</Button>,
              ]}
            >
              <List.Item.Meta
                title={<span style={{ fontSize: 12 }}>{item.title}</span>}
                description={<Text type="secondary" style={{ fontSize: 11 }}>
                  {TASK_STATUS_MAP[item.status]?.label || item.status}
                  {item.priority && ` · P${item.priority}`}
                </Text>}
              />
            </List.Item>
          )}
          style={{ maxHeight: 200, overflowY: "auto" }}
        />
      </Spin>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Acceptance Plan Editor
// ---------------------------------------------------------------------------

const AcceptancePlanEditor: React.FC<{
  value: string | null;
  onChange: (v: string) => void;
  readonly?: boolean;
}> = ({ value, onChange, readonly }) => {
  if (readonly) {
    if (!value) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无验收计划" />;
    return (
      <div style={{
        background: "#ECFDF5", borderRadius: 10, padding: 16, border: "1px solid #A7F3D0",
      }}>
        <Title level={5} style={{ color: "#059669", marginTop: 0, marginBottom: 8 }}>
          <FileTextOutlined /> 验收计划 / Definition of Done
        </Title>
        <Paragraph style={{ color: "#047857", whiteSpace: "pre-wrap", marginBottom: 0 }}>
          {value}
        </Paragraph>
      </div>
    );
  }

  return (
    <div>
        <Input.TextArea
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
        placeholder={"输入验收计划（Definition of Done），例如：\n\n1. 所有 Story Points 的任务均标记为 Done\n2. 代码通过 Code Review\n3. 自动化测试通过率 ≥ 95%\n4. 部署到 Staging 环境并验证\n5. 产品负责人验收通过"}
        rows={6}
        style={{ borderRadius: 8 }}
      />
      <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: "block" }}>
        验收计划定义了 Sprint 完成的标准，帮助团队对齐"完成"的含义。
      </Text>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

const SprintManagement: React.FC = () => {
  const { message } = App.useApp();
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [form] = Form.useForm();
  const [createOpen, setCreateOpen] = useState(false);

  // Expanded sprint detail
  const [expandedSprintId, setExpandedSprintId] = useState<string | null>(null);
  const [reportData, setReportData] = useState<SprintReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  // Editing acceptance plan
  const [editingAcceptance, setEditingAcceptance] = useState<string | null>(null);

  // ---- Data loading ----

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await sprintApi.list(projectId ? { project_id: projectId } : {});
      const items: any[] = r?.items || r || [];
      setSprints(
        items.map((s: any) => ({
          id: s.id,
          name: s.name,
          goal: s.goal || "",
          startDate: (s.start_date || "").toString(),
          endDate: (s.end_date || "").toString(),
          status: s.status,
          velocity: s.velocity || 0,
          capacity: s.capacity || 0,
          projectId: s.project_id || "",
          acceptancePlan: s.acceptance_plan || undefined,
        }))
      );
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载 Sprint 失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [projectId]);
  useEffect(() => {
    projectApi.list({ limit: 200 }).then((r: any) => setProjects(r?.items || r?.data || [])).catch(() => {});
  }, []);

  // ---- Report loading ----

  const loadReport = async (sprintId: string) => {
    setReportLoading(true);
    try {
      const r: any = await sprintApi.report(sprintId);
      setReportData(r as SprintReport);
    } catch (e: any) {
      message.error("加载报告失败");
      setReportData(null);
    } finally {
      setReportLoading(false);
    }
  };

  useEffect(() => {
    if (expandedSprintId) {
      loadReport(expandedSprintId);
    } else {
      setReportData(null);
    }
  }, [expandedSprintId]);

  // ---- Actions ----

  const getStatusTag = (status: string) => {
    const m = STATUS_MAP[status];
    return <Tag color={m?.color} icon={m?.icon as any} style={{ borderRadius: 6 }}>{m?.label || status}</Tag>;
  };

  const onStart = async (id: string) => {
    try { await sprintApi.start(id); message.success("已启动 Sprint"); load(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "操作失败"); }
  };
  const onComplete = async (id: string) => {
    try { await sprintApi.complete(id); message.success("Sprint 已完成"); load(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "操作失败"); }
  };

  const openCreate = () => {
    form.resetFields();
    form.setFieldValue("acceptance_plan", "");
    setCreateOpen(true);
  };
  const onSubmit = async () => {
    const v = await form.validateFields();
    const payload: any = {
      name: v.name,
      project_id: v.project_id,
      goal: v.goal || "",
      start_date: v.start_date ? v.start_date.format("YYYY-MM-DD") : undefined,
      end_date: v.end_date ? v.end_date.format("YYYY-MM-DD") : undefined,
      capacity: v.capacity ?? 0,
      velocity: v.velocity ?? 0,
      status: "planning",
      acceptance_plan: v.acceptance_plan || null,
    };
    try {
      await sprintApi.create(payload);
      message.success("Sprint 创建成功");
      setCreateOpen(false);
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const handleSaveAcceptance = async (sprintId: string, plan: string) => {
    try {
      await sprintApi.update(sprintId, { acceptance_plan: plan });
      message.success("验收计划已保存");
      setEditingAcceptance(null);
      if (expandedSprintId === sprintId) loadReport(expandedSprintId);
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    }
  };

  // ---- Render helpers ----

  const getProjectName = (pid: string) => {
    const p = projects.find(x => x.id === pid);
    return p?.name || pid;
  };

  // Active sprint card
  const activeSprint = sprints.find(s => s.status === "active");

  return (
    <div>
      {/* ===== Header ===== */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Sprint 敏捷管理</Title>
          <Text type="secondary">Scrum 迭代管理 · 关联任务 · 验收计划 · 燃尽图 / 燃起图</Text>
        </div>
        <Space wrap>
          <Select
            allowClear placeholder="全部项目"
            data-tour="sprints-sel"
            style={{ width: 180 }}
            value={projectId || undefined}
            onChange={(v) => setProjectId(v || "")}
            options={projects.map(p => ({ label: p.name, value: p.id }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-tour="sprints-new">创建 Sprint</Button>
        </Space>
      </div>

      {loading && sprints.length === 0 && <Empty description="加载中..." style={{ marginTop: 40 }} />}

      {/* ===== Active Sprint Hero Card ===== */}
      {activeSprint && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <Card
            className="gradient-bg"
            style={{ borderRadius: 20, marginBottom: 24, border: "none", cursor: "pointer" }}
            bodyStyle={{ padding: "24px 28px" }}
            onClick={() => setExpandedSprintId(expandedSprintId === activeSprint.id ? null : activeSprint.id)}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", color: "#fff", flexWrap: "wrap", gap: 12 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                  <Title level={4} style={{ color: "#fff", margin: 0 }}>{activeSprint.name}</Title>
                  {getStatusTag(activeSprint.status)}
                  <Tag style={{ background: "rgba(255,255,255,0.15)", color: "#fff", border: "none", borderRadius: 6 }}>
                    {getProjectName(activeSprint.projectId)}
                  </Tag>
                </div>
                <Text style={{ color: "rgba(255,255,255,0.8)" }}>目标: {activeSprint.goal || "—"}</Text>
                <div style={{ marginTop: 8 }}>
                  <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>
                    {activeSprint.startDate} → {activeSprint.endDate}
                    {activeSprint.acceptancePlan && " · 有验收计划"}
                  </Text>
                </div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 32, fontWeight: 800 }}>{pct(activeSprint.velocity, activeSprint.capacity)}%</div>
                <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>产能完成率</Text>
              </div>
            </div>
            <Progress percent={pct(activeSprint.velocity, activeSprint.capacity)} strokeColor="#06B6D4" trailColor="rgba(255,255,255,0.15)" showInfo={false} style={{ marginTop: 12 }} />
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={6}><Statistic title={<span style={{ color: "rgba(255,255,255,0.7)", fontSize: 12 }}>承诺产能</span>} value={activeSprint.capacity} valueStyle={{ color: "#fff", fontSize: 20 }} /></Col>
              <Col span={6}><Statistic title={<span style={{ color: "rgba(255,255,255,0.7)", fontSize: 12 }}>实际速度</span>} value={activeSprint.velocity} valueStyle={{ color: "#06B6D4", fontSize: 20 }} /></Col>
              <Col span={6}><Statistic title={<span style={{ color: "rgba(255,255,255,0.7)", fontSize: 12 }}>缺口</span>} value={Math.max(0, activeSprint.capacity - activeSprint.velocity)} valueStyle={{ color: "#F59E0B", fontSize: 20 }} /></Col>
              <Col span={6}><Statistic title={<span style={{ color: "rgba(255,255,255,0.7)", fontSize: 12 }}>目标达成</span>} value={`${pct(activeSprint.velocity, activeSprint.capacity)}%`} valueStyle={{ color: "#10B981", fontSize: 20 }} /></Col>
            </Row>
          </Card>
        </motion.div>
      )}

      {/* ===== Expanded Sprint Detail (with charts & tasks) ===== */}
      <AnimatePresence>
        {expandedSprintId && reportData && (
          <motion.div
            key={`detail-${expandedSprintId}`}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
          >
            <Card
              style={{ borderRadius: 16, marginBottom: 24, borderTop: "3px solid #6366F1" }}
              className="card-hover"
            >
              <Tabs
                defaultActiveKey="burndown"
                items={[
                  {
                    key: "burndown",
                    label: (
                      <span><FireOutlined /> 燃尽图 Burndown</span>
                    ),
                    children: (
                      <div>
                        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                          <Col span={6}><Card size="small"><Statistic title="总任务" value={reportData.total_tasks} /></Card></Col>
                          <Col span={6}><Card size="small"><Statistic title="已完成" value={reportData.completed_tasks} valueStyle={{ color: "#10B981" }} /></Card></Col>
                          <Col span={6}><Card size="small"><Statistic title="完成率" value={reportData.completion_rate} suffix="%" valueStyle={{ color: reportData.completion_rate >= 80 ? "#10B981" : "#F59E0B" }} /></Card></Col>
                          <Col span={6}><Card size="small"><Statistic title="速度/产能" value={`${reportData.velocity}/${reportData.capacity}`} /></Card></Col>
                        </Row>
                        <BurndownChart data={reportData} />
                      </div>
                    ),
                  },
                  {
                    key: "burnup",
                    label: (
                      <span><LineChartOutlined /> 燃起图 Burnup</span>
                    ),
                    children: <BurnupChart data={reportData} />,
                  },
                  {
                    key: "tasks",
                    label: (
                      <span><TeamOutlined /> 关联任务 ({reportData.tasks_summary.length})</span>
                    ),
                    children: (
                      <TaskAssociationPanel
                        sprintId={expandedSprintId}
                        projectId={sprints.find(s => s.id === expandedSprintId)?.projectId || ""}
                        tasks={reportData.tasks_summary}
                        onRefresh={() => loadReport(expandedSprintId)}
                      />
                    ),
                  },
                  {
                    key: "acceptance",
                    label: (
                      <span><AimOutlined /> 验收计划 DoD</span>
                    ),
                    children: editingAcceptance === expandedSprintId ? (
                      <div>
                        <AcceptancePlanEditor
                          value={reportData.acceptance_plan}
                          onChange={(v) => {
                            /* optimistic update */
                            setReportData(prev => prev ? { ...prev, acceptance_plan: v } : null);
                          }}
                        />
                        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                          <Button type="primary" size="small" onClick={() => handleSaveAcceptance(expandedSprintId, reportData?.acceptance_plan || "")}>保存</Button>
                          <Button size="small" onClick={() => setEditingAcceptance(null)}>取消</Button>
                        </div>
                      </div>
                    ) : (
                      <div>
                        <AcceptancePlanEditor value={reportData.acceptance_plan} readonly />
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          style={{ marginTop: 12 }}
                          onClick={() => setEditingAcceptance(expandedSprintId)}
                        >编辑验收计划</Button>
                      </div>
                    ),
                  },
                ]}
              />
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ===== Sprint List Table ===== */}
      <Card title="Sprint 迭代列表" style={{ borderRadius: 16 }} className="card-hover" data-tour="sprints-list">
        <Table
          dataSource={sprints} rowKey="id" loading={loading} pagination={false} className="enhanced-table"
          columns={[
            { title: "Sprint", dataIndex: "name", key: "name", render: (n: string) => <Text strong>{n}</Text> },
            { title: "目标", dataIndex: "goal", key: "goal", render: (g: string) => <Text ellipsis style={{ maxWidth: 200 }}>{g || "—"}</Text> },
            { title: "状态", dataIndex: "status", key: "status", render: (s: string) => getStatusTag(s) },
            { title: "时间", key: "date", render: (_: any, r: Sprint) => <Text style={{ fontSize: 12 }}>{r.startDate} → {r.endDate}</Text> },
            { title: "产能完成率", key: "rate", render: (_: any, r: Sprint) => (
              <Progress percent={pct(r.velocity, r.capacity)} size="small" strokeColor={{ from: "#4F46E5", to: "#7C3AED" }} format={() => `${r.velocity}/${r.capacity}`} />
            )},
            { title: "验收", key: "acc", render: (_: any, r: Sprint) =>
              r.acceptancePlan ? <Tag color="green" icon={<AimOutlined />}>有</Tag> : <Tag color="default">无</Tag>
            },
            { title: "操作", key: "action", width: 180, render: (_: any, r: Sprint) => (
              <Space>
                <Button size="small" type="link" onClick={() => setExpandedSprintId(expandedSprintId === r.id ? null : r.id)}>
                  详情
                </Button>
                {r.status === "planning" && <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => onStart(r.id)}>开始</Button>}
                {r.status === "active" && <Button size="small" icon={<CheckCircleOutlined />} onClick={() => onComplete(r.id)}>完成</Button>}
              </Space>
            )},
          ]}
        />
      </Card>

      {/* ===== Velocity Trend (real chart) ===== */}
      <Card
        title={<span><ThunderboltOutlined /> 速度趋势 (Velocity Trend)</span>}
        style={{ borderRadius: 16, marginTop: 16 }}
        className="card-hover"
      >
        <VelocityChart sprints={sprints} />
      </Card>

      {/* ===== Create Modal ===== */}
      <Modal
        title="创建 Sprint"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={onSubmit}
        okText="创建"
        destroyOnClose
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="所属项目" name="project_id" rules={[{ required: true, message: "请选择项目" }]}>
            <Select placeholder="选择项目" showSearch optionFilterProp="children" options={projects.map(p => ({ label: p.name, value: p.id }))} />
          </Form.Item>
          <Form.Item label="Sprint 名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="例如：Sprint 1 — 用户认证模块" />
          </Form.Item>
          <Form.Item label="迭代目标" name="goal">
            <Input.TextArea rows={2} placeholder="本迭代要达成的目标（如：完成用户认证全流程开发）" />
          </Form.Item>
          <Form.Item
            label={<span><AimOutlined /> 验收计划 (DoD)</span>}
            name="acceptance_plan"
            extra="定义本 Sprint「完成」的标准，如代码审查通过、测试覆盖率 ≥ 80% 等"
          >
            <Input.TextArea
              rows={4}
              placeholder={"示例：\n1. 所有分配的任务均标记为 Done\n2. 代码通过 Peer Review\n3. 单元测试覆盖率 ≥ 80%\n4. 部署至 Staging 并通过产品验收"}
            />
          </Form.Item>
          <Space size={12} wrap>
            <Form.Item label="开始日期" name="start_date"><DatePicker style={{ width: 160 }} /></Form.Item>
            <Form.Item label="结束日期" name="end_date"><DatePicker style={{ width: 160 }} /></Form.Item>
            <Form.Item label="承诺产能" name="capacity"><InputNumber min={0} placeholder="故事点" style={{ width: 120 }} /></Form.Item>
            <Form.Item label="初始速度" name="velocity"><InputNumber min={0} placeholder="0" style={{ width: 100 }} /></Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default SprintManagement;
