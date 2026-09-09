import React, { useEffect, useState } from "react";
import AIAssistButton from "../components/AIAssistButton";
import { Table, Button, Modal, Form, Input, InputNumber, Select, App, Space, Tag, Popconfirm, DatePicker, Typography, Row, Col, Card, Statistic, Progress, Empty } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, BarChartOutlined, CheckCircleOutlined, ClockCircleOutlined, AlertOutlined, ProfileOutlined } from "@ant-design/icons";
import { useSearchParams, useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import { motion } from "framer-motion";
import { taskApi, projectApi, sprintApi } from "../api";

const { Title, Text } = Typography;

const STATUS_OPTIONS = [
  { value: "backlog", label: "待办" },
  { value: "todo", label: "待开始" },
  { value: "in_progress", label: "进行中" },
  { value: "in_review", label: "评审中" },
  { value: "testing", label: "测试中" },
  { value: "done", label: "已完成" },
  { value: "cancelled", label: "已取消" },
];

// Sprint 状态映射（与 SprintManagement 保持一致）
const SPRINT_STATUS_LABEL: Record<string, string> = {
  planning: "规划中",
  active: "进行中",
  completed: "已完成",
};
const statusLabel = (s?: string) => (s ? SPRINT_STATUS_LABEL[s] || s : "—");

const Tasks: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [projectId, setProjectId] = useState<string>(params.get("projectId") || "");
  const [projects, setProjects] = useState<any[]>([]);
  const [sprints, setSprints] = useState<any[]>([]);
  const [form] = Form.useForm();
  const [search, setSearch] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const res = await taskApi.list({ project_id: projectId || undefined, page_size: 200 });
      setData(res?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    projectApi.list({ page_size: 100 }).then((r) => setProjects(r?.items || [])).catch(() => {});
    load();
    // 预加载 Sprint 列表供表格 Sprint 列展示跨项目任务
    sprintApi.list({ page_size: 200 }).then((r: any) => setSprints(r?.items || [])).catch(() => {});
  }, [projectId]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ project_id: projectId || undefined, status: "todo", priority: 3 });
    loadSprints(projectId || undefined);
    setModalOpen(true);
  };

  const openEdit = (row: any) => {
    setEditing(row);
    form.setFieldsValue({ ...row, planned_start: row.planned_start ? dayjs(row.planned_start) : null, planned_end: row.planned_end ? dayjs(row.planned_end) : null });
    loadSprints(row.project_id || projectId || undefined, row.sprint_id);
    setModalOpen(true);
  };

  // 加载当前项目下可选的 Sprint 列表；若传 selectedId 不在结果里，则一并保留
  const loadSprints = async (pid: string | undefined, keepSelectedId?: string) => {
    if (!pid) { setSprints([]); return; }
    try {
      const r: any = await sprintApi.list({ project_id: pid, page_size: 200 });
      const items = r?.items || [];
      // 编辑时若后端返回的列表不含已选 sprint（可能跨项目或已删除），仍保留作可选项
      if (keepSelectedId && !items.some((s: any) => s.id === keepSelectedId)) {
        const cur: any = items.find((s: any) => s.id === keepSelectedId);
        if (!cur) items.unshift({ id: keepSelectedId, name: `(已不在该项目) ${keepSelectedId.slice(0, 8)}…` });
      }
      setSprints(items);
    } catch {
      setSprints([]);
    }
  };

  const submit = async () => {
    try {
      const v = await form.validateFields();
      // sprint_id：undefined → null，确保后端能识别清空请求
      const payload: any = {
        ...v,
        planned_start: v.planned_start ? v.planned_start.format("YYYY-MM-DD") : null,
        planned_end: v.planned_end ? v.planned_end.format("YYYY-MM-DD") : null,
        sprint_id: v.sprint_id ?? null,
      };
      if (editing) { await taskApi.update(editing.id, payload); } else { await taskApi.create(payload); }
      message.success("保存成功");
      setModalOpen(false);
      load();
    } catch (e: any) {
      if (e?.response) message.error(e.response.data?.detail || "保存失败");
    }
  };

  const changeStatus = async (id: string, status: string) => {
    try { await taskApi.update(id, { status }); message.success("状态已更新"); load(); } catch (e: any) { message.error(e?.response?.data?.detail || "更新失败"); }
  };

  const remove = async (id: string) => {
    try { await taskApi.remove(id); message.success("删除成功"); load(); } catch (e: any) { message.error(e?.response?.data?.detail || "删除失败"); }
  };

  const filtered = data.filter(t => !search || t.name?.toLowerCase().includes(search.toLowerCase()) || t.wbs_code?.toLowerCase().includes(search.toLowerCase()));

  const projectMap = new Map(projects.map((p: any) => [p.id, p.name]));
  const sprintMap = new Map(sprints.map((s: any) => [s.id, s.name]));

  const doneTasks = data.filter(t => t.status === "done").length;
  const overdueTasks = data.filter(t => t.due_date && new Date(t.due_date) < new Date() && t.status !== "done").length;
  const progress = data.length > 0 ? Math.round((doneTasks / data.length) * 100) : 0;

  const columns = [
    { title: "WBS", dataIndex: "wbs_code", width: 80, render: (c: string) => <Tag style={{ fontFamily: "monospace", borderRadius: 4 }}>{c || "—"}</Tag> },
    { title: "任务", dataIndex: "name", width: 280, ellipsis: { showTitle: false }, render: (n: string) => <Text strong ellipsis={{ tooltip: n }} style={{ display: "block" }}>{n}</Text> },
    { title: "所属项目", dataIndex: "project_id", width: 180, ellipsis: { showTitle: false }, render: (pid: string) => {
      const name = projectMap.get(pid);
      return name
        ? <a onClick={() => navigate(`/projects/${pid}`)} style={{ color: "#4F46E5", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={name}>{name}</a>
        : <Tag>{pid || "未关联"}</Tag>;
    } },
    { title: "Sprint", dataIndex: "sprint_id", width: 140, ellipsis: { showTitle: false }, render: (sid: string, r: any) => {
      if (!sid) return <Text type="secondary">—</Text>;
      // 优先用本页面缓存的 sprintMap；若任务跨项目展示，再用 task 的 project_id 临时查一次
      let name = sprintMap.get(sid);
      if (!name && r.project_id) {
        // 同步从缓存查不到，异步补一次
        sprintApi.get(sid).then((sp: any) => {
          if (sp?.name) setSprints(prev => prev.find(s => s.id === sid) ? prev : [...prev, { id: sid, name: sp.name }]);
        }).catch(() => {});
        return <Tag color="processing" style={{ borderRadius: 6 }}>{(sid || "").slice(0, 8)}…</Tag>;
      }
      return name
        ? <Tag color="cyan" style={{ borderRadius: 6, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "inline-block" }} title={name}>{name}</Tag>
        : <Tag>{(sid || "").slice(0, 8)}…</Tag>;
    } },
    { title: "状态", dataIndex: "status", width: 130, render: (s: string, r: any) => (
      <Select size="small" value={s} options={STATUS_OPTIONS} style={{ width: 110 }} onChange={(v) => changeStatus(r.id, v)} />
    )},
    { title: "优先级", dataIndex: "priority", width: 70, render: (p: number) => <Tag color={p >= 4 ? "red" : p >= 3 ? "orange" : "blue"}>{p}</Tag> },
    { title: "负责人", dataIndex: "assignee_id", width: 90, ellipsis: true, render: (v: string) => v || "—" },
    { title: "进度", dataIndex: "progress", width: 110, render: (p: number) => <Progress percent={p || 0} size="small" style={{ width: 90 }} /> },
    { title: "截止", dataIndex: "due_date", width: 110, render: (d: string) => d ? <Text style={{ color: new Date(d) < new Date() ? "#EF4444" : "inherit" }}>{d}</Text> : "—" },
    { title: "操作", width: 100, fixed: "right", render: (_: any, r: any) => (
      <Space>
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
        <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)}><Button size="small" danger icon={<DeleteOutlined />} /></Popconfirm>
      </Space>
    )},
  ];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>任务管理</Title>
          <Text type="secondary">全局任务视图，支持多项目筛选和状态批量更新</Text>
        </div>
        <Space wrap>
          <Input prefix={<SearchOutlined />} placeholder="搜索任务..." value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200, borderRadius: 10 }} allowClear />
          <Select data-tour="tasks-filter" placeholder="按项目筛选" allowClear style={{ width: 200 }} value={projectId || undefined} options={projects.map((p: any) => ({ value: p.id, label: p.name }))} onChange={(v) => setProjectId(v || "")} />
          <Button icon={<BarChartOutlined />} onClick={() => navigate("/kanban")}>看板视图</Button>
          <Button data-tour="tasks-new" type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建任务</Button>
        </Space>
      </div>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={8} sm={6} md={4}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>总任务</span>} value={data.length} prefix={<ProfileOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={8} sm={6} md={4}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>已完成</span>} value={doneTasks} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={8} sm={6} md={4}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>逾期</span>} value={overdueTasks} prefix={<AlertOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={6}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #3B82F6 0%, #6366F1 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>完成率</span>} value={`${progress}%`} prefix={<BarChartOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
      </Row>

      <Card className="enhanced-table" style={{ borderRadius: 16 }}>
        <Table data-tour="tasks-table" rowKey="id" loading={loading} columns={columns} dataSource={filtered} tableLayout="fixed" scroll={{ x: 1290 }} pagination={{ pageSize: 15, showSizeChanger: true, showTotal: t => `共 ${t} 条` }} locale={{ emptyText: <Empty description="暂无任务" /> }} />
      </Card>

      <Modal title={editing ? "编辑任务" : "新建任务"} open={modalOpen} onOk={submit} onCancel={() => setModalOpen(false)} destroyOnClose width={560}>
        <Form form={form} layout="vertical">
          <div style={{ marginBottom: 12 }}>
            <AIAssistButton
              formType="task"
              getValues={() => form.getFieldsValue(true)}
              onApply={(s) => form.setFieldsValue(s)}
              context={{ project_id: projectId }}
            />
          </div>
          <Form.Item name="project_id" label="所属项目" rules={[{ required: true, message: "请选择项目" }]}>
            <Select
              options={projects.map((p: any) => ({ value: p.id, label: p.name }))}
              placeholder="选择项目"
              onChange={(v: string) => {
                // 切换项目时清空已选 Sprint 并按新项目重载
                form.setFieldsValue({ sprint_id: undefined });
                loadSprints(v);
              }}
            />
          </Form.Item>
          <Form.Item name="sprint_id" label="所属 Sprint" tooltip="任务归属的迭代；仅显示当前选中项目下的 Sprint，可留空表示暂未分配">
            <Select
              allowClear
              disabled={!sprints.length}
              options={sprints.map((s: any) => ({ value: s.id, label: `${s.name}${s.status ? `（${statusLabel(s.status)}）` : ""}` }))}
              placeholder={sprints.length ? "选择 Sprint（可留空）" : "请先选择所属项目"}
            />
          </Form.Item>
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: "请输入任务名称" }]}>
            <Input placeholder="例如：完成登录模块开发" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="例如：实现用户名/密码登录，含表单校验与错误提示" />
          </Form.Item>
          <Space size="large" style={{ width: "100%" }}>
            <Form.Item name="status" label="状态" rules={[{ required: true }]}>
              <Select options={STATUS_OPTIONS} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="priority" label="优先级" initialValue={3}>
              <InputNumber min={1} max={5} style={{ width: 100 }} />
            </Form.Item>
            <Form.Item name="assignee_id" label="负责人ID">
              <Input style={{ width: 120 }} placeholder="例如：u_1001" />
            </Form.Item>
          </Space>
          <Space size="large" style={{ width: "100%" }}>
            <Form.Item name="planned_start" label="计划开始">
              <DatePicker style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="planned_end" label="计划结束">
              <DatePicker style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="estimated_hours" label="预估工时(h)">
              <InputNumber min={0} style={{ width: 100 }} placeholder="例如：8" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default Tasks;
