import React, { useEffect, useMemo, useState } from "react";
import AIAssistButton from "../components/AIAssistButton";
import { Table, Button, Modal, Form, Input, InputNumber, Select, App, Space, Tag, Popconfirm, DatePicker, Typography, Row, Col, Card, Statistic, Progress, Empty } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined, BarChartOutlined, CheckCircleOutlined, ClockCircleOutlined, AlertOutlined, ProfileOutlined } from "@ant-design/icons";
import { useSearchParams, useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { taskApi, projectApi, sprintApi } from "../api";

const { Title, Text } = Typography;

const Tasks: React.FC = () => {
  const { t } = useTranslation("tasks");
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

  // \u72b6\u6001/\u4f18\u5148\u7ea7/\u8d1f\u8d23\u4eba\u9009\u9879\uff08i18n \u7248\u672c\uff0c\u5fc5\u987b\u653e\u5728\u7ec4\u4ef6\u5185\u4ee5\u4f7f\u7528 t()\uff09
  const STATUS_OPTIONS = useMemo(() => [
    { value: "backlog", label: t("statusOptions.backlog") },
    { value: "todo", label: t("statusOptions.todo") },
    { value: "in_progress", label: t("statusOptions.in_progress") },
    { value: "in_review", label: t("statusOptions.in_review") },
    { value: "testing", label: t("statusOptions.testing") },
    { value: "done", label: t("statusOptions.done") },
    { value: "cancelled", label: t("statusOptions.cancelled") },
  ], [t]);

  // Sprint \u72b6\u6001\u6620\u5c04\uff08\u4e0e SprintManagement \u4fdd\u6301\u4e00\u81f4\uff0ci18n\uff09
  const SPRINT_STATUS_LABEL: Record<string, string> = useMemo(() => ({
    planning: t("sprintStatusLabel.planning"),
    active: t("sprintStatusLabel.active"),
    completed: t("sprintStatusLabel.completed"),
  }), [t]);

  const statusLabel = (s?: string) => (s ? SPRINT_STATUS_LABEL[s] || s : "—");

  const load = async () => {
    setLoading(true);
    try {
      const res = await taskApi.list({ project_id: projectId || undefined, page_size: 200 });
      setData(res?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t("messages.loadError"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    projectApi.list({ page_size: 100 }).then((r) => setProjects(r?.items || [])).catch(() => {});
    load();
    // \u9884\u52a0\u8f7d Sprint \u5217\u8868\u4f9b\u8868\u683c Sprint \u5217\u5c55\u793a\u8de8\u9879\u76ee\u4efb\u52a1
    sprintApi.list({ page_size: 200 }).then((r: any) => setSprints(r?.items || [])).catch(() => {});
  }, [projectId]);

  // AI \u9879\u76ee\u7ecf\u7406\u300c\u76f4\u63a5\u64cd\u4f5c\u7cfb\u7edf\u300d\u6267\u884c\u6210\u529f\u540e\u81ea\u52a8\u5237\u65b0\u5217\u8868\uff08\u8de8\u7ec4\u4ef6 CustomEvent\uff0c\u4e0e\u7ec4\u7ec7\u7ba1\u7406\u9875\u540c\u4e00\u7ea6\u5b9a\uff09
  useEffect(() => {
    const onTasksChanged = () => { load(); };
    window.addEventListener("aipm:tasks-changed", onTasksChanged);
    return () => window.removeEventListener("aipm:tasks-changed", onTasksChanged);
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

  // \u52a0\u8f7d\u5f53\u524d\u9879\u76ee\u4e0b\u53ef\u9009\u7684 Sprint \u5217\u8868\uff1b\u82e5\u4f20 selectedId \u4e0d\u5728\u7ed3\u679c\u91cc\uff0c\u5219\u4e00\u5e76\u4fdd\u7559
  const loadSprints = async (pid: string | undefined, keepSelectedId?: string) => {
    if (!pid) { setSprints([]); return; }
    try {
      const r: any = await sprintApi.list({ project_id: pid, page_size: 200 });
      const items = r?.items || [];
      // \u7f16\u8f91\u65f6\u82e5\u540e\u7aef\u8fd4\u56de\u7684\u5217\u8868\u4e0d\u542b\u5df2\u9009 sprint\uff08\u53ef\u80fd\u8de8\u9879\u76ee\u6216\u5df2\u5220\u9664\uff09\uff0c\u4ecd\u4fdd\u7559\u4f5c\u53ef\u9009\u9879
      if (keepSelectedId && !items.some((s: any) => s.id === keepSelectedId)) {
        const cur: any = items.find((s: any) => s.id === keepSelectedId);
        if (!cur) items.unshift({ id: keepSelectedId, name: t("messages.keepSelectedHint", { id: keepSelectedId.slice(0, 8) }) });
      }
      setSprints(items);
    } catch {
      setSprints([]);
    }
  };

  const submit = async () => {
    try {
      const v = await form.validateFields();
      // sprint_id\uff1aundefined → null\uff0c\u786e\u4fdd\u540e\u7aef\u80fd\u8bc6\u522b\u6e05\u7a7a\u8bf7\u6c42
      const payload: any = {
        ...v,
        planned_start: v.planned_start ? v.planned_start.format("YYYY-MM-DD") : null,
        planned_end: v.planned_end ? v.planned_end.format("YYYY-MM-DD") : null,
        sprint_id: v.sprint_id ?? null,
      };
      if (editing) { await taskApi.update(editing.id, payload); } else { await taskApi.create(payload); }
      message.success(t("messages.saveSuccess"));
      setModalOpen(false);
      load();
    } catch (e: any) {
      if (e?.response) message.error(e.response.data?.detail || t("messages.saveError"));
    }
  };

  const changeStatus = async (id: string, status: string) => {
    try { await taskApi.update(id, { status }); message.success(t("messages.statusUpdated")); load(); } catch (e: any) { message.error(e?.response?.data?.detail || t("messages.saveError")); }
  };

  const remove = async (id: string) => {
    try { await taskApi.remove(id); message.success(t("messages.deleteSuccess")); load(); } catch (e: any) { message.error(e?.response?.data?.detail || t("messages.deleteError")); }
  };

  const filtered = data.filter(t => !search || t.name?.toLowerCase().includes(search.toLowerCase()) || t.wbs_code?.toLowerCase().includes(search.toLowerCase()));

  const projectMap = new Map(projects.map((p: any) => [p.id, p.name]));
  const sprintMap = new Map(sprints.map((s: any) => [s.id, s.name]));

  const doneTasks = data.filter(t => t.status === "done").length;
  const overdueTasks = data.filter(t => t.due_date && new Date(t.due_date) < new Date() && t.status !== "done").length;
  const progress = data.length > 0 ? Math.round((doneTasks / data.length) * 100) : 0;

  const columns = [
    { title: "WBS", dataIndex: "wbs_code", width: 80, render: (c: string) => <Tag style={{ fontFamily: "monospace", borderRadius: 4 }}>{c || "—"}</Tag> },
    { title: t("columns.name"), dataIndex: "name", width: 280, ellipsis: { showTitle: false }, render: (n: string) => <Text strong ellipsis={{ tooltip: n }} style={{ display: "block" }}>{n}</Text> },
    { title: t("columns.project"), dataIndex: "project_id", width: 180, ellipsis: { showTitle: false }, render: (pid: string) => {
      const name = projectMap.get(pid);
      return name
        ? <a onClick={() => navigate(`/projects/${pid}`)} style={{ color: "#4F46E5", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={name}>{name}</a>
        : <Tag>{pid || t("columns.unassociated")}</Tag>;
    } },
    { title: "Sprint", dataIndex: "sprint_id", width: 140, ellipsis: { showTitle: false }, render: (sid: string, r: any) => {
      if (!sid) return <Text type="secondary">—</Text>;
      // \u4f18\u5148\u7528\u672c\u9875\u9762\u7f13\u5b58\u7684 sprintMap\uff1b\u82e5\u4efb\u52a1\u8de8\u9879\u76ee\u5c55\u793a\uff0c\u518d\u7528 task \u7684 project_id \u4e34\u65f6\u67e5\u4e00\u6b21
      let name = sprintMap.get(sid);
      if (!name && r.project_id) {
        // \u540c\u6b65\u4ece\u7f13\u5b58\u67e5\u4e0d\u5230\uff0c\u5f02\u6b65\u8865\u4e00\u6b21
        sprintApi.get(sid).then((sp: any) => {
          if (sp?.name) setSprints(prev => prev.find(s => s.id === sid) ? prev : [...prev, { id: sid, name: sp.name }]);
        }).catch(() => {});
        return <Tag color="processing" style={{ borderRadius: 6 }}>{(sid || "").slice(0, 8)}…</Tag>;
      }
      return name
        ? <Tag color="cyan" style={{ borderRadius: 6, maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "inline-block" }} title={name}>{name}</Tag>
        : <Tag>{(sid || "").slice(0, 8)}…</Tag>;
    } },
    { title: t("columns.status"), dataIndex: "status", width: 130, render: (s: string, r: any) => (
      <Select size="small" value={s} options={STATUS_OPTIONS} style={{ width: 110 }} onChange={(v) => changeStatus(r.id, v)} />
    )},
    { title: t("columns.priority"), dataIndex: "priority", width: 70, render: (p: number) => <Tag color={p >= 4 ? "red" : p >= 3 ? "orange" : "blue"}>{p}</Tag> },
    { title: t("columns.assignee"), dataIndex: "assignee_id", width: 90, ellipsis: true, render: (v: string) => v || "—" },
    { title: t("columns.progress"), dataIndex: "progress", width: 110, render: (p: number) => <Progress percent={p || 0} size="small" style={{ width: 90 }} /> },
    { title: t("columns.dueDate"), dataIndex: "due_date", width: 110, render: (d: string) => d ? <Text style={{ color: new Date(d) < new Date() ? "#EF4444" : "inherit" }}>{d}</Text> : "—" },
    { title: t("columns.action"), width: 100, fixed: "right" as const, render: (_: any, r: any) => (
      <Space>
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)} />
        <Popconfirm title={t("popconfirm.deleteTitle")} onConfirm={() => remove(r.id)}><Button size="small" danger icon={<DeleteOutlined />} /></Popconfirm>
      </Space>
    )},
  ];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>{t("title")}</Title>
          <Text type="secondary">{t("subtitle")}</Text>
        </div>
        <Space wrap>
          <Input prefix={<SearchOutlined />} placeholder={t("searchPlaceholder")} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200, borderRadius: 10 }} allowClear />
          <Select data-tour="tasks-filter" placeholder={t("filterByProject")} allowClear style={{ width: 200 }} value={projectId || undefined} options={projects.map((p: any) => ({ value: p.id, label: p.name }))} onChange={(v) => setProjectId(v || "")} />
          <Button icon={<BarChartOutlined />} onClick={() => navigate("/kanban")}>{t("kanbanView")}</Button>
          <Button data-tour="tasks-new" type="primary" icon={<PlusOutlined />} onClick={openCreate}>{t("newTask")}</Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={8} sm={6} md={4}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>{t("statTotal")}</span>} value={data.length} prefix={<ProfileOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={8} sm={6} md={4}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>{t("statDone")}</span>} value={doneTasks} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={8} sm={6} md={4}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>{t("statOverdue")}</span>} value={overdueTasks} prefix={<AlertOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={6}>
          <Card className="card-hover" style={{ borderRadius: 12, background: "linear-gradient(135deg, #3B82F6 0%, #6366F1 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)", fontSize: 11 }}>{t("statRate")}</span>} value={`${progress}%`} prefix={<BarChartOutlined />} valueStyle={{ color: "#fff", fontSize: 20 }} />
          </Card>
        </Col>
      </Row>

      <Card className="enhanced-table" style={{ borderRadius: 16 }}>
        <Table data-tour="tasks-table" rowKey="id" loading={loading} columns={columns} dataSource={filtered} tableLayout="fixed" scroll={{ x: 1290 }} pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (tc: number) => t("modal.total", { count: tc }) }} locale={{ emptyText: <Empty description={t("messages.loadError")} /> }} />
      </Card>

      <Modal title={editing ? t("modal.edit") : t("modal.create")} open={modalOpen} onOk={submit} onCancel={() => setModalOpen(false)} destroyOnClose width={560}>
        <Form form={form} layout="vertical">
          <div style={{ marginBottom: 12 }}>
            <AIAssistButton
              formType="task"
              getValues={() => {
                const v = form.getFieldsValue(true);
                if (v.planned_start) v.planned_start = v.planned_start?.format?.("YYYY-MM-DD");
                if (v.planned_end) v.planned_end = v.planned_end?.format?.("YYYY-MM-DD");
                return v;
              }}
              onApply={(s) => form.setFieldsValue(s)}
              context={{ project_id: projectId }}
              dateFields={["planned_start", "planned_end"]}
            />
          </div>
          <Form.Item name="project_id" label={t("modal.form.project")} rules={[{ required: true, message: t("modal.form.projectRequired") }]}>
            <Select
              options={projects.map((p: any) => ({ value: p.id, label: p.name }))}
              placeholder={t("modal.form.projectRequired")}
              onChange={(v: string) => {
                // \u5207\u6362\u9879\u76ee\u65f6\u6e05\u7a7a\u5df2\u9009 Sprint \u5e76\u6309\u65b0\u9879\u76ee\u91cd\u8f7d
                form.setFieldsValue({ sprint_id: undefined });
                loadSprints(v);
              }}
            />
          </Form.Item>
          <Form.Item name="sprint_id" label={t("modal.form.sprint")} tooltip={t("modal.form.sprintTooltip")}>
            <Select
              allowClear
              disabled={!sprints.length}
              options={sprints.map((s: any) => ({ value: s.id, label: `${s.name}${s.status ? `\uff08${statusLabel(s.status)}\uff09` : ""}` }))}
              placeholder={sprints.length ? t("modal.form.sprintPlaceholder") : t("modal.form.sprintPlaceholderNoProject")}
            />
          </Form.Item>
          <Form.Item name="name" label={t("modal.form.name")} rules={[{ required: true, message: t("modal.form.nameRequired") }]}>
            <Input placeholder={t("modal.form.namePlaceholder")} />
          </Form.Item>
          <Form.Item name="description" label={t("modal.form.description")}>
            <Input.TextArea rows={2} placeholder={t("modal.form.descriptionPlaceholder")} />
          </Form.Item>
          <Space size="large" style={{ width: "100%" }}>
            <Form.Item name="status" label={t("columns.status")} rules={[{ required: true }]}>
              <Select options={STATUS_OPTIONS} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="priority" label={t("columns.priority")} initialValue={3}>
              <InputNumber min={1} max={5} style={{ width: 100 }} />
            </Form.Item>
            <Form.Item name="assignee_id" label={t("columns.assignee")}>
              <Input style={{ width: 120 }} placeholder={t("modal.form.assigneePlaceholder")} />
            </Form.Item>
          </Space>
          <Space size="large" style={{ width: "100%" }}>
            <Form.Item name="planned_start" label={t("modal.form.plannedStart")}>
              <DatePicker style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="planned_end" label={t("modal.form.plannedEnd")}>
              <DatePicker style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="estimated_hours" label={t("modal.form.estimatedHours")}>
              <InputNumber min={0} style={{ width: 100 }} placeholder={t("modal.form.estimatedHoursPlaceholder")} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default Tasks;
