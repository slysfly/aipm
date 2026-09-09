import React, { useState, useEffect, useCallback } from "react";
import {
  Card, Typography, Tag, Button, Tabs, Space, Table, Modal, Form,
  Input, Select, DatePicker, Spin, Empty, Statistic, Row, Col, Progress,
  Popconfirm, Tooltip, Badge, message, Timeline as AntTimeline, Switch
} from "antd";
import {
  PlusOutlined, CheckCircleOutlined, ClockCircleOutlined, AimOutlined,
  RocketOutlined, ApiOutlined, FundOutlined, ThunderboltOutlined,
  DeleteOutlined, EditOutlined, EyeOutlined, ClusterOutlined
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import dayjs from "dayjs";
import { roadmapApi, projectApi } from "../api";

const { Title, Text, Paragraph } = Typography;

// ── Types ────────────────────────────────────────────────
interface RoadmapItem {
  id: string;
  title: string;
  description: string;
  desc?: string;
  status: string;
  priority: string;
  quarter: string;
  date: string;
  startDate: string;
  endDate: string;
  viewType: string;
  category: string;
  projectId: string;
  releaseId: string;
  techStack: string;
  maturityLevel: string;
  owner: string;
  progress: number;
  createdAt: string;
}

interface ProjectOption {
  id: string;
  name: string;
}

// ── Constants ─────────────────────────────────────────────
const VIEW_TYPES = [
  { key: "release", label: "发布管理", icon: <RocketOutlined />, color: "#7C3AED" },
  { key: "value_stream", label: "价值流图", icon: <FundOutlined />, color: "#059669" },
  { key: "tech_roadmap", label: "技术路线图", icon: <ApiOutlined />, color: "#2563EB" },
];

const STATUS_MAP: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  done: { color: "#10B981", label: "已完成", icon: <CheckCircleOutlined /> },
  in_progress: { color: "#3B82F6", label: "进行中", icon: <ClockCircleOutlined /> },
  planned: { color: "#94A3B8", label: "规划中", icon: <AimOutlined /> },
  cancelled: { color: "#EF4444", label: "已取消", icon: <AimOutlined /> },
};

const PRIORITY_MAP: Record<string, { color: string; label: string }> = {
  high: { color: "red", label: "高" },
  medium: { color: "orange", label: "中" },
  low: { color: "blue", label: "低" },
};

const MATURITY_OPTIONS = [
  { label: "研究阶段", value: "research" },
  { label: "原型验证", value: "prototype" },
  { label: "生产就绪", value: "production" },
  { label: "已废弃", value: "deprecated" },
];

const VALUE_STREAM_STAGES = [
  { key: "idea", label: "需求构思", color: "#818CF8" },
  { key: "design", label: "设计规划", color: "#34D399" },
  { key: "develop", label: "开发实现", color: "#60A5FA" },
  { key: "test", label: "测试验证", color: "#FBBF24" },
  { key: "deploy", label: "部署交付", color: "#F472B6" },
  { key: "operate", label: "运营反馈", color: "#A78BFA" },
];

// ── Main Component ───────────────────────────────────────
const ProductRoadmap: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("release");
  const [items, setItems] = useState<RoadmapItem[]>([]);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<RoadmapItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // View-specific data states
  const [valueStreamData, setValueStreamData] = useState<any>(null);
  const [techTimelineData, setTechTimelineData] = useState<any>(null);
  const [releaseBoardData, setReleaseBoardData] = useState<any>(null);
  [dashboardData, setDashboardData] = useState<any>(null);

  // ── Data Loading ───────────────────────────────────────
  const loadProjects = useCallback(async () => {
    try {
      const r: any = await projectApi.list({ page_size: 100 });
      setProjects((r?.items || r?.data?.items || []).map((p: any) => ({ id: p.id, name: p.name })));
    } catch { /* ignore */ }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 并行加载所有数据
      const [itemsRes, dashRes, vsRes, trRes, rbRes] = await Promise.allSettled([
        roadmapApi.list({ view_type: activeTab, project_id: selectedProject || undefined }),
        roadmapApi.dashboardSummary(selectedProject || undefined),
        roadmapApi.valueStreamMap(selectedProject || undefined),
        roadmapApi.techRoadmapTimeline(selectedProject || undefined),
        roadmapApi.releaseBoard(selectedProject || undefined),
      ]);

      if (itemsRes.status === "fulfilled") setItems(itemsRes.value?.items || []);
      if (dashRes.status === "fulfilled") setDashboardData(dashRes.value);
      if (vsRes.status === "fulfilled") setValueStreamData(vsRes.value);
      if (trRes.status === "fulfilled") setTechTimelineData(trRes.value);
      if (rbRes.status === "fulfilled") setReleaseBoardData(rbRes.value);
    } catch (e) {
      message.error("加载数据失败");
    } finally {
      setLoading(false);
    }
  }, [activeTab, selectedProject]);

  useEffect(() => { loadProjects(); }, []);
  useEffect(() => { loadData(); }, [loadData]);

  // ── CRUD ───────────────────────────────────────────────
  const openCreate = () => {
    setEditingItem(null);
    form.resetFields();
    form.setFieldValue("view_type", activeTab);
    form.setFieldValue("project_id", selectedProject);
    setModalOpen(true);
  };

  const openEdit = (item: RoadmapItem) => {
    setEditingItem(item);
    form.setFieldsValue({
      title: item.title,
      description: item.description || item.desc,
      status: item.status,
      priority: item.priority,
      quarter: item.quarter,
      date: item.date ? dayjs(item.date, "YYYY-MM") : null,
      start_date: item.startDate ? dayjs(item.startDate) : null,
      end_date: item.endDate ? dayjs(item.endDate) : null,
      view_type: item.viewType,
      category: item.category,
      project_id: item.projectId,
      tech_stack: item.techStack,
      maturity_level: item.maturityLevel,
      owner: item.owner,
      progress: item.progress,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: any) => {
    setSaving(true);
    try {
      const payload = {
        ...values,
        date: values.date ? dayjs(values.date).format("YYYY-MM") : "",
        start_date: values.start_date ? dayjs(values.start_date).format("YYYY-MM-DD") : "",
        end_date: values.end_date ? dayjs(values.end_date).format("YYYY-MM-DD") : "",
        description: values.description || "",
      };
      if (editingItem) {
        await roadmapApi.update(editingItem.id, payload);
        message.success("已更新");
      } else {
        await roadmapApi.create(payload);
        message.success("已创建");
      }
      setModalOpen(false);
      form.resetFields();
      loadData();
    } catch (e) {
      message.error(editingItem ? "更新失败" : "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await roadmapApi.remove(id);
      message.success("已删除");
      loadData();
    } catch { message.error("删除失败"); }
  };

  // ── Render Helpers ─────────────────────────────────────
  const currentViewConfig = VIEW_TYPES.find(v => v.key === activeTab) || VIEW_TYPES[0];

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            产品路线图 <Text type="secondary" style={{ fontSize: 14 }}>(Roadmap)</Text>
          </Title>
          <Text type="secondary">产品战略规划 · 价值流 · 技术演进 · 版本发布</Text>
        </div>
        <Space>
          <Select
            placeholder="筛选项目"
            allowClear
            style={{ width: 180 }}
            value={selectedProject || undefined}
            onChange={setSelectedProject}
            options={projects.map(p => ({ label: p.name, value: p.id }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增{currentViewConfig.label.replace(/管理|图$/, "")}
          </Button>
        </Space>
      </div>

      {/* Dashboard Summary Cards */}
      {dashboardData && (
        <Row gutter={[16, 16]} style={{ marginTop: 20 }}>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic title="总条目" value={dashboardData.total} prefix={<ClusterOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="发布管理"
                value={dashboardData.byView?.release || 0}
                valueStyle={{ color: "#7C3AED" }}
                prefix={<RocketOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="价值流"
                value={dashboardData.byView?.value_stream || 0}
                valueStyle={{ color: "#059669" }}
                prefix={<FundOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small">
              <Statistic
                title="技术路线"
                value={dashboardData.byView?.tech_roadmap || 0}
                valueStyle={{ color: "#2563EB" }}
                prefix={<ApiOutlined />}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* Main Content - Three Views */}
      <Spin spinning={loading}>
        <Card style={{ marginTop: 16, borderRadius: 16 }} bodyStyle={{ padding: 0 }}>
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key)}
            type="card"
            size="large"
            items={VIEW_TYPES.map(v => ({
              key: v.key,
              label: (
                <span>
                  {v.icon} {v.label}
                  {dashboardData?.byView?.[v.key] ? (
                    <Badge count={dashboardData.byView[v.key]} style={{ backgroundColor: v.color, marginLeft: 6 }} />
                  ) : null}
                </span>
              ),
              children: renderTabContent(v.key),
            }))}
          />
        </Card>
      </Spin>

      {/* Create/Edit Modal */}
      <Modal
        title={editingItem ? `编辑${currentViewConfig.label}` : `新增${currentViewConfig.label}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item label="标题" name="title" rules={[{ required: true }]}>
                <Input placeholder="输入里程碑/节点名称" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="状态" name="status" initialValue="planned">
                <Select options={[
                  { label: "规划中", value: "planned" },
                  { label: "进行中", value: "in_progress" },
                  { label: "已完成", value: "done" },
                  { label: "已取消", value: "cancelled" },
                ]} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="描述" name="description">
            <Input.TextArea rows={2} placeholder="详细说明..." />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="优先级" name="priority" initialValue="medium">
                <Select options={[
                  { label: "高", value: "high" },
                  { label: "中", value: "medium" },
                  { label: "低", value: "low" },
                ]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="视图类型" name="view_type">
                <Select options={VIEW_TYPES.map(v => ({ label: v.label, value: v.key }))} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="关联项目" name="project_id">
                <Select showSearch optionFilterProp="label" allowClear placeholder="选择项目"
                  options={projects.map(p => ({ label: p.name, value: p.id }))} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="季度" name="quarter">
                <Input placeholder="2026 Q3" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="开始日期" name="start_date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="结束日期" name="end_date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>

          {/* 视图特有字段 */}
          {(() => {
            // We'll read form values reactively via Form.Item shouldRender
            return (
              <>
                <Form.Item noStyle shouldUpdate={(prev, cur) => prev.view_type !== cur.view_type}>
                  {({ getFieldValue }) =>
                    getFieldValue("view_type") === "value_stream" ? (
                      <Form.Item label="价值阶段" name="category">
                        <Select options={VALUE_STREAM_STAGES.map(s => ({ label: s.label, value: s.key }))} placeholder="选择价值流阶段" />
                      </Form.Item>
                    ) : getFieldValue("view_type") === "tech_roadmap" ? (
                      <>
                        <Row gutter={16}>
                          <Col span={12}>
                            <Form.Item label="技术域" name="category">
                              <Input placeholder="如：前端 / 后端 / 基础设施 / AI" />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item label="成熟度" name="maturity_level">
                              <Select options={MATURITY_OPTIONS} placeholder="选择成熟度" />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item label="技术栈标签" name="tech_stack">
                          <Input placeholder="React, Python, K8s（逗号分隔）" />
                        </Form.Item>
                      </>
                    ) : getFieldValue("view_type") === "release" ? (
                      <Form.Item label="分类" name="category">
                        <Input placeholder="如：v2.0 / Hotfix / Feature" />
                      </Form.Item>
                    ) : null
                  }
                </Form.Item>
              </>
            );
          })()}

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="负责人" name="owner">
                <Input placeholder="负责人姓名" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="进度 %" name="progress">
                <Input type="number" min={0} max={100} placeholder="0-100" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={saving}>
              {editingItem ? "保存修改" : "创建"}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );

  // ── Tab Renderers ──────────────────────────────────────

  function renderTabContent(tabKey: string): React.ReactNode {
    switch (tabKey) {
      case "value_stream":   return renderValueStream();
      case "tech_roadmap":   return renderTechRoadmap();
      case "release":        return renderReleaseMgmt();
      default:               return <Empty />;
    }
  }

  // ── ① 价值流图 ────────────────────────────────────────

  function renderValueStream(): React.ReactNode {
    const data = valueStreamData;
    if (!data || data.stages.every((s: any) => s.itemCount === 0)) {
      return <Empty description="暂无价值流数据，点击右上角新增" style={{ padding: 80 }} />;
    }

    const stagesWithItems = data.stages.filter((s: any) => s.itemCount > 0);

    // ECharts 漏斗 + 流程图
    const funnelOption = {
      tooltip: { trigger: "item", formatter: "{b}: {c} 项 ({d}%)" },
      series: [{
        type: "funnel",
        left: "10%",
        top: 20,
        bottom: 20,
        width: "80%",
        sort: "ascending",
        gap: 3,
        label: { show: true, position: "inside", fontSize: 13, fontWeight: "bold" },
        data: stagesWithItems.map((s: any) => ({
          name: s.label,
          value: s.itemCount,
          itemStyle: { color: VALUE_STREAM_STAGES.find(vs => vs.key === s.key)?.color || "#94A3B8" },
        })),
      }],
    };

    // 进度横向条形图
    const progressOption = {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 120, right: 40, top: 20, bottom: 30 },
      xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      yAxis: {
        type: "category",
        data: stagesWithItems.map((s: any) => s.label),
        inverse: true,
        axisLabel: { fontSize: 13 },
      },
      series: [{
        type: "bar",
        data: stagesWithItems.map((s: any) => ({
          value: s.progress,
          itemStyle: {
            color: s.progress >= 80 ? "#10B981" : s.progress >= 40 ? "#F59E0B" : "#94A3B8",
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barWidth: 22,
        label: { show: true, position: "right", formatter: "{c}%", fontSize: 12 },
      }],
    };

    return (
      <div style={{ padding: 24 }}>
        <Row gutter={[24, 24]}>
          <Col xs={24} lg={10}>
            <Text strong style={{ fontSize: 15 }}>价值分布漏斗</Text>
            <ReactECharts option={funnelOption} style={{ height: 360 }} opts={{ renderer: "canvas" }} />
          </Col>
          <Col xs={24} lg={14}>
            <Text strong style={{ fontSize: 15 }}>各阶段完成进度</Text>
            <ReactECharts option={progressOption} style={{ height: 360 }} opts={{ renderer: "canvas" }} />
          </Col>
        </Row>

        {/* 阶段详情卡片 */}
        <Title level={5} style={{ marginTop: 24, marginBottom: 12 }}>阶段明细</Title>
        <Row gutter={[16, 16]}>
          {stagesWithItems.map((stage: any) => (
            <Col xs={24} md={12} xl={8} key={stage.key}>
              <Card
                size="small"
                title={
                  <Space>
                    <Tag color={VALUE_STREAM_STAGES.find(vs => vs.key === stage.key)?.color}>{stage.label}</Tag>
                    <Text type="secondary">{stage.doneCount}/{stage.itemCount}</Text>
                  </Space>
                }
                style={{ borderRadius: 12 }}
              >
                <Progress percent={stage.progress} size="small" strokeColor="#7C3AED" />
                <div style={{ marginTop: 10 }}>
                  {stage.items.slice(0, 3).map((it: any) => (
                    <div key={it.id} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: "6px 0", borderBottom: "1px solid #f0f0f0",
                    }}>
                      <Space size={4}>
                        <Tag color={STATUS_MAP[it.status]?.color || "default"}
                          style={{ margin: 0, fontSize: 11 }}>
                          {STATUS_MAP[it.status]?.label || it.status}
                        </Tag>
                        <Text ellipsis style={{ maxWidth: 160, fontSize: 13 }}>{it.title}</Text>
                      </Space>
                      <Space size={4}>
                        <Tooltip title="编辑"><Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(it)} /></Tooltip>
                        <Popconfirm title="确定删除？" onConfirm={() => handleDelete(it.id)}>
                          <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    </div>
                  ))}
                  {stage.items.length > 3 && (
                    <Text type="secondary" style={{ fontSize: 12, display: "block", textAlign: "center", paddingTop: 4 }}>
                      还有 {stage.items.length - 3} 项...
                    </Text>
                  )}
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    );
  }

  // ── ② 技术路线图 ─────────────────────────────────────

  function renderTechRoadmap(): React.ReactNode {
    const data = techTimelineData;
    if (!data || data.lanes.length === 0) {
      return <Empty description="暂无技术路线数据，点击右上角新增" style={{ padding: 80 }} />;
    }

    // 泳道甘特图
    const categories = data.lanes.map((l: any) => l.name);
    const ganttSeries = data.lanes.map((lane: any, idx: number) => ({
      name: lane.name,
      type: "custom",
      renderItem: (params: any, api: any) => {
        const start = api.value(0);
        const end = api.value(1);
        const progress = api.value(2);
        if (!start && !end) return undefined;

        const startX = api.coord([start, idx])[0];
        const endX = api.coord([end || start, idx])[0];
        const py = api.coord([0, idx])[1];
        const h = 28;

        // 背景条
        const bgRect = {
          type: "rect", shape: { x: startX, y: py - h / 2, width: Math.max(endX - startX, 2), height: h },
          style: { fill: "#EDE9FE", lineWidth: 1, stroke: "#C4B5FD" },
        };
        // 进度条
        const progW = (endX - startX) * (progress / 100);
        const progRect = {
          type: "rect", shape: { x: startX, y: py - h / 2, width: Math.max(progW, 2), height: h },
          style: { fill: "#7C3AED", opacity: 0.85 },
        };
        // 标签
        const label = {
          type: "text", style: {
            fill: "#333", x: startX + 4, y: py, text: api.value(3) || "", fontSize: 11,
          },
        };
        return { type: "group", children: [bgRect, progRect, label] };
      },
      encode: { x: [0, 1], y: 2 },
      data: lane.items.map((it: any) => [
        it.startDate || it.date || it.quarter || "",
        it.endDate || it.date || it.quarter || "",
        idx,
        it.title,
        it.progress || 0,
      ]),
      z: 10,
    }));

    const ganttOption = {
      tooltip: { trigger: "item" },
      grid: { left: 140, right: 40, top: 10, bottom: 30 },
      xAxis: { type: "time" },
      yAxis: { type: "category", data: categories, inverse: true },
      series: ganttSeries,
    };

    // 技术栈分布饼图
    const stackOption = data.stacks.length > 0 ? {
      tooltip: { trigger: "item" },
      series: [{
        type: "pie", radius: ["35%", "65%"], center: ["50%", "55%"],
        roseType: "area",
        label: { formatter: "{b}: {c}", fontSize: 11 },
        data: data.stacks.map((s: string, i: number) => ({
          name: s, value: 1,
          itemStyle: { color: ["#7C3AED", "#059669", "#2563EB", "#DC2626", "#D97706", "#0891B2"][i % 6] },
        })),
      }],
    } : null;

    // 成熟度统计
    const matData = data.maturitySummary || {};
    const maturityOption = {
      tooltip: { trigger: "axis" },
      grid: { left: 10, right: 10, top: 10, bottom: 25 },
      xAxis: { type: "category", data: ["研究", "原型", "生产", "废弃"] },
      yAxis: { type: "value" },
      series: [{
        type: "bar", data: [matData.research || 0, matData.prototype || 0, matData.production || 0, matData.deprecated || 0],
        itemStyle: {
          color: (params: any) => ["#94A3B8", "#3B82F6", "#10B981", "#EF4444"][params.dataIndex],
          borderRadius: [6, 6, 0, 0],
        },
        barWidth: 40,
      }],
    };

    return (
      <div style={{ padding: 24 }}>
        <Row gutter={[24, 24]}>
          <Col xs={24} lg={16}>
            <Text strong style={{ fontSize: 15 }}>技术演进时间线（泳道图）</Text>
            <ReactECharts option={ganttOption} style={{ height: Math.max(data.lanes.length * 60 + 60, 300) }} opts={{ renderer: "canvas" }} />
          </Col>
          <Col xs={24} lg={8}>
            {stackOption && (
              <>
                <Text strong style={{ fontSize: 15 }}>技术栈分布</Text>
                <ReactECharts option={stackOption} style={{ height: 220 }} opts={{ renderer: "canvas" }} />
              </>
            )}
            <Text strong style={{ fontSize: 15, display: "block", marginTop: 16 }}>成熟度分布</Text>
            <ReactECharts option={maturityOption} style={{ height: 200 }} opts={{ renderer: "canvas" }} />
          </Col>
        </Row>

        {/* 技术域卡片 */}
        <Title level={5} style={{ marginTop: 24, marginBottom: 12 }}>技术域详情</Title>
        <Row gutter={[16, 16]}>
          {data.lanes.map((lane: any) => (
            <Col xs={24} md={12} key={lane.name}>
              <Card
                size="small"
                title={
                  <Space>
                    <ThunderboltOutlined style={{ color: "#2563EB" }} />
                    <Text strong>{lane.name}</Text>
                    <Tag color="blue">{lane.doneCount}/{lane.itemCount}</Tag>
                  </Space>
                }
                style={{ borderRadius: 12 }}
              >
                <Progress percent={lane.progress} size="small" strokeColor="#2563EB" />
                <AntTimeline mode="left" style={{ marginTop: 12 }}>
                  {lane.items.slice(0, 4).map((it: any) => (
                    <AntTimeline.Item
                      key={it.id}
                      color={STATUS_MAP[it.status]?.color || "gray"}
                      label={it.quarter || it.startDate || ""}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <Text strong>{it.title}</Text>
                          {it.techStack && (
                            <div>{it.techStack.split(",").filter(Boolean).slice(0, 3).map((ts: string) => (
                              <Tag key={ts.trim()} style={{ fontSize: 10, marginLeft: 4 }}>{ts.trim()}</Tag>
                            ))}</div>
                          )}
                          {it.maturityLevel && (
                            <Tag color={{
                              research: "default", prototype: "blue", production: "green", deprecated: "red",
                            }[it.maturityLevel] || "default"} style={{ fontSize: 10, marginTop: 2 }}>
                              {MATURITY_OPTIONS.find(m => m.value === it.maturityLevel)?.label || it.maturityLevel}
                            </Tag>
                          )}
                        </div>
                        <Space>
                          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(it)} />
                          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(it.id)}>
                            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>
                        </Space>
                      </div>
                    </AntTimeline.Item>
                  ))}
                </AntTimeline>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    );
  }

  // ── ③ 发布管理 ───────────────────────────────────────

  function renderReleaseMgmt(): React.ReactNode {
    const data = releaseBoardData;
    const hasItems = items.length > 0 || (data && (data.releases?.length > 0 || data.milestones?.length > 0));

    if (!hasItems) {
      return <Empty description="暂无发布计划，点击右上角新增里程碑或版本" style={{ padding: 80 }} />;
    }

    // 发布甘特图
    const ganttData = data?.ganttData || [];
    const ganttOption = ganttData.length > 0 ? {
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params;
          const d = ganttData[p.dataIndex];
          return `${d.name}<br/>状态: ${d.status}<br/>进度: ${d.progress}%`;
        },
      },
      grid: { left: 180, right: 40, top: 10, bottom: 30 },
      xAxis: { type: "time" },
      yAxis: {
        type: "category",
        data: ganttData.map((d: any) => d.name),
        inverse: true,
        axisLabel: { fontSize: 11, width: 170, overflow: "truncate" },
      },
      series: [{
        type: "custom",
        renderItem: (params: any, api: any) => {
          const start = api.value(0);
          const end = api.value(1);
          const progress = api.value(2);
          const isRel = api.value(3);
          if (!start) return undefined;

          const startX = api.coord([start, params[0]])[0];
          const endX = api.coord([end || start, params[0]])[0];
          const py = api.coord([0, params[0]])[1];
          const h = 24;
          const w = Math.max(endX - startX, 2);

          return {
            type: "group",
            children: [
              { type: "rect", shape: { x: startX, y: py - h / 2, width: w, height: h },
                style: { fill: isRel ? "#DDD6FE" : "#E0E7FF", lineWidth: 1, stroke: isRel ? "#C4B5FD" : "#A5B4FC", radius: 4 } },
              { type: "rect", shape: { x: startX, y: py - h / 2, width: w * (progress / 100), height: h },
                style: { fill: isRel ? "#7C3AED" : "#4F46E5", opacity: 0.85, radius: 4 } },
            ],
          };
        },
        encode: { x: [0, 1], y: 2 },
        data: ganttData.map((d: any) => [
          d.start, d.end || d.start, d.progress || 0, d.type === "release" ? 1 : 0,
        ]),
      }],
    } : null;

    // 状态看板列定义
    const boardColumns = ["planning", "in_progress", "released", "archived"];
    const boardLabels: Record<string, string> = {
      planning: "📋 规划中", in_progress: "🚧 进行中", released: "✅ 已发布", archived: "📦 已归档",
    };

    return (
      <div style={{ padding: 24 }}>
        {/* 甘特图 */}
        {ganttOption && (
          <>
            <Text strong style={{ fontSize: 15 }}>发布时间线</Text>
            <ReactECharts option={ganttOption} style={{ height: Math.max(ganttData.length * 42 + 60, 280) }} opts={{ renderer: "canvas" }} />
          </>
        )}

        {/* 统计概览 */}
        {data?.summary && (
          <Row gutter={[16, 16]} style={{ marginTop: 20 }}>
            <Col span={6}>
              <Card size="small"><Statistic title="里程碑" value={data.summary.totalMilestones} suffix="项" /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title="版本总数" value={data.summary.totalReleases} suffix="个" /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title="已发布" value={data.summary.releasedCount} valueStyle={{ color: "#10B981" }} /></Card>
            </Col>
            <Col span={6}>
              <Card size="small"><Statistic title="规划/开发中" value={data.summary.planningCount} valueStyle={{ color: "#F59E0B" }} /></Card>
            </Col>
          </Row>
        )}

        {/* 看板视图 */}
        <Title level={5} style={{ marginTop: 24, marginBottom: 12 }}>发布看板</Title>
        <Row gutter={12}>
          {boardColumns.map(status => (
            <Col xs={24} sm={12} md={6} key={status}>
              <Card
                size="small"
                title={boardLabels[status]}
                style={{
                  borderRadius: 12, minHeight: 200,
                  borderLeft: `4px solid ${status === "released" ? "#10B981" : status === "in_progress" ? "#F59E0B" : status === "archived" ? "#94A3B8" : "#3B82F6"}`,
                }}
              >
                <Space direction="vertical" style={{ width: "100%" }} size={8}>
                  {/* 路线图里程碑 */}
                  {items.filter(it => it.status === status).map(it => (
                    <Card key={it.id} size="small" hoverable style={{ borderRadius: 8 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <Text strong style={{ fontSize: 13 }}>{it.title}</Text>
                          {it.quarter && <Tag color="purple" style={{ marginLeft: 6, fontSize: 10 }}>{it.quarter}</Tag>}
                          <br />
                          <Text type="secondary" style={{ fontSize: 11 }}>{it.description || it.desc || ""}</Text>
                          {it.projectId && projects.find(p => p.id === it.projectId) && (
                            <Tag color="geekblue" style={{ fontSize: 10, marginTop: 4 }}>
                              {projects.find(p => p.id === it.projectId)?.name}
                            </Tag>
                          )}
                        </div>
                        <Space size={2}>
                          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(it)} />
                          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(it.id)}>
                            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>
                        </Space>
                      </div>
                      {it.progress > 0 && <Progress percent={it.progress} size="small" style={{ marginTop: 6 }} />}
                    </Card>
                  ))}
                  {/* Release 表中的版本 */}
                  {(data?.releases || [])
                    .filter((r: any) => r.status === status)
                    .map((r: any) => (
                      <Card key={`rel-${r.id}`} size="small" hoverable style={{ borderRadius: 8, background: "#FAF5FF" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                          <div>
                            <Text strong style={{ fontSize: 13 }}>{r.name}</Text>
                            <Tag color="purple" style={{ marginLeft: 6 }}>v{r.version}</Tag>
                            <br />
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              任务 {r.completedTaskCount}/{r.taskCount}
                              {r.releaseDate && ` · ${r.releaseDate}`}
                            </Text>
                          </div>
                          <Badge
                            count={r.taskCount > 0 ? Math.round(r.completedTaskCount / r.taskCount * 100) : 0}
                            style={{ backgroundColor: r.completedTaskCount === r.taskCount && r.taskCount > 0 ? "#52c41a" : "#1890ff" }}
                            overflowCount={100}
                          />
                        </div>
                      </Card>
                    ))
                  }
                  {items.filter(it => it.status === status).length === 0 &&
                    (data?.releases || []).filter((r: any) => r.status === status).length === 0 && (
                    <Text type="secondary" style={{ fontSize: 12, textAlign: "center", display: "block", paddingTop: 20 }}>暂无</Text>
                  )}
                </Space>
              </Card>
            </Col>
          ))}
        </Row>

        {/* 表格视图 */}
        <Title level={5} style={{ marginTop: 24, marginBottom: 12 }}>全部条目</Title>
        <Table
          dataSource={items}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "标题", dataIndex: "title", ellipsis: true, render: (t: string) => <Text strong>{t}</Text> },
            {
              title: "状态", dataIndex: "status", width: 90,
              render: (s: string) => {
                const cfg = STATUS_MAP[s];
                return cfg ? <Tag color={cfg.color} icon={cfg.icon} style={{ borderRadius: 6 }}>{cfg.label}</Tag> : s;
              },
            },
            { title: "优先级", dataIndex: "priority", width: 70,
              render: (p: string) => <Tag color={PRIORITY_MAP[p]?.color}>{PRIORITY_MAP[p]?.label || p}</Tag>,
            },
            { title: "季度", dataIndex: "quarter", width: 90 },
            { title: "项目", dataIndex: "projectId", width: 120,
              render: (pid: string) => pid ? projects.find(p => p.id === pid)?.name || pid : "-",
            },
            { title: "分类", dataIndex: "category", width: 100, ellipsis: true },
            { title: "进度", dataIndex: "progress", width: 80,
              render: (p: number) => <Progress percent={p || 0} size="small" />,
            },
            {
              title: "操作", width: 100, fixed: "right" as const,
              render: (_: any, rec: RoadmapItem) => (
                <Space>
                  <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(rec)} />
                  <Popconfirm title="确定删除？" onConfirm={() => handleDelete(rec.id)}>
                    <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </div>
    );
  }
};

export default ProductRoadmap;
