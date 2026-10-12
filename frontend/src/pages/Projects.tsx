import React, { useEffect, useState } from "react";
import { Card, Typography, Tag, Button, Space, Modal, Form, Input, Select, DatePicker, App, Spin, Row, Col, Progress, InputNumber, Empty, Popconfirm } from "antd";
import AIAssistButton from "../components/AIAssistButton";
import { PlusOutlined, SearchOutlined, DeleteOutlined, EditOutlined, FundProjectionScreenOutlined, FilterOutlined, ClearOutlined } from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { projectApi, projectTypeApi } from "../api";
import dayjs from "dayjs";

const { Title, Text } = Typography;

const Projects: React.FC = () => {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<any[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<any>(null);
  const [form] = Form.useForm();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("");
  const [types, setTypes] = useState<any[]>([]);

  const loadTypes = async () => {
    try {
      const data = await projectTypeApi.list();
      setTypes(Array.isArray(data) ? data : []);
    } catch { /* ignore: fall back to code when type is missing */ }
  };

  useEffect(() => { loadTypes(); }, []);

  const typeMap: Record<string, any> = {};
  types.forEach((t) => { typeMap[t.code] = t; });
  const renderTypeTag = (code?: string) => {
    const t = code ? typeMap[code] : undefined;
    if (!t) return code ? <Tag>{code}</Tag> : null;
    return <Tag color={t.color} style={{ borderRadius: 6 }}>{t.name}</Tag>;
  };

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { page_size: 100 };
      if (statusFilter) params.status = statusFilter;
      const res = await projectApi.list(params);
      setProjects(res?.items || []);
    } catch (e: any) {
      message.error(t("messages.loadError"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [statusFilter]);

  // 由 /projects?new=1 直达：自动打开新建弹窗并清掉 query，避免刷新/后退重复弹出
  useEffect(() => {
    if (searchParams.get("new") === "1") {
      handleCreate();
      const next = new URLSearchParams(searchParams);
      next.delete("new");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams]);

  const handleCreate = () => {
    setEditingProject(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (p: any) => {
    setEditingProject(p);
    form.setFieldsValue({
      ...p,
      start_date: p.start_date ? dayjs(p.start_date) : undefined,
      end_date: p.end_date ? dayjs(p.end_date) : undefined,
    });
    setModalOpen(true);
  };

  const handleSave = async (values: any) => {
    try {
      const payload = { ...values };
      if (values.start_date) payload.start_date = values.start_date.format("YYYY-MM-DD");
      if (values.end_date) payload.end_date = values.end_date.format("YYYY-MM-DD");
      if (values.budget === null || values.budget === undefined || values.budget === "") delete payload.budget;
      else payload.budget = Number(values.budget);
      if (editingProject) {
        await projectApi.update(editingProject.id, payload);
        message.success(t("messages.updateSuccess"));
      } else {
        await projectApi.create(payload);
        message.success(t("messages.createSuccess"));
      }
      setModalOpen(false);
      load();
    } catch (e: any) { message.error(e?.response?.data?.detail || t("messages.opError")); }
  };

  const handleDelete = async (id: string) => {
    try {
      await projectApi.remove(id);
      message.success(t("messages.deleteSuccess"));
      load();
    } catch { message.error(t("messages.deleteError")); }
  };

  const filtered = projects.filter(p => {
    if (search && !p.name?.toLowerCase().includes(search.toLowerCase()) && !p.description?.toLowerCase().includes(search.toLowerCase())) return false;
    if (priorityFilter && p.priority !== priorityFilter) return false;
    return true;
  });

  const getStatusColor = (s: string) => s === "active" ? "green" : s === "planning" ? "blue" : s === "done" ? "default" : "default";
  const statusLabel = (s: string) =>
    s === "active" ? t("statusInProgress") :
    s === "planning" ? t("statusPlanning") :
    s === "done" ? t("statusDone") :
    t("statusArchived");
  const priorityLabel = (p: number) => p <= 2 ? t("priorityHigh") : p === 3 ? t("priorityMedium") : t("priorityLow");

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>{t("title")}</Title>
          <Text type="secondary">{t("subtitle")}</Text>
        </div>
        <Space wrap>
          <Input prefix={<SearchOutlined />} placeholder={t("searchPlaceholder")} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200, borderRadius: 10 }} allowClear />
          <Select placeholder={t("filterStatusPlaceholder")} allowClear style={{ width: 120 }} value={statusFilter || undefined} onChange={v => setStatusFilter(v || "")}
            options={[
              { label: t("filterAll"), value: "" },
              { label: t("statusInProgress"), value: "active" },
              { label: t("statusPlanning"), value: "planning" },
              { label: t("statusDone"), value: "done" },
              { label: t("statusArchived"), value: "archived" },
            ]} />
          <Select placeholder={t("filterPriorityPlaceholder")} allowClear style={{ width: 110 }} value={priorityFilter || undefined} onChange={(v) => setPriorityFilter(v ?? "")}
            options={[
              { label: t("filterAll"), value: "" },
              { label: t("priorityHigh"), value: 1 },
              { label: t("priorityMedium"), value: 3 },
              { label: t("priorityLow"), value: 5 },
            ]} />
          <Button data-tour="proj-new" type="primary" icon={<PlusOutlined />} onClick={handleCreate}>{t("newProject")}</Button>
        </Space>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spin size="large" /></div>
      ) : filtered.length === 0 ? (
        <div className="enhanced-empty">
          <div style={{ fontSize: 60, marginBottom: 16 }}>🚀</div>
          <h3>{search || statusFilter || priorityFilter ? t("emptyNoMatch") : t("emptyNone")}</h3>
          <p>{search || statusFilter || priorityFilter ? t("emptyNoMatchHint") : t("emptyNoneHint")}</p>
          {!search && !statusFilter && !priorityFilter && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>{t("createFirst")}</Button>
          )}
        </div>
      ) : (
        <div data-tour="proj-list" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 16 }}>
          {filtered.map((p, idx) => (
            <motion.div key={p.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.04 }}>
              <Card
                className="card-hover"
                style={{ borderRadius: 16, cursor: "pointer" }}
                onClick={() => navigate(`/projects/${p.id}`)}
                actions={[
                  <EditOutlined key="edit" onClick={e => { e.stopPropagation(); handleEdit(p); }} />,
                  <Popconfirm
                    key="delete"
                    title={t("deleteTitle")}
                    description={t("deleteDescription")}
                    okText={t("deleteOk")}
                    okType="danger"
                    cancelText={t("deleteCancel")}
                    onConfirm={() => handleDelete(p.id)}
                  >
                    <DeleteOutlined onClick={e => e.stopPropagation()} />
                  </Popconfirm>,
                ]}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div>
                    <Text strong style={{ fontSize: 15 }}>{p.name}</Text>
                    <div style={{ marginTop: 4, display: "flex", gap: 4, flexWrap: "wrap" }}>
                      <Tag color={getStatusColor(p.status)} style={{ borderRadius: 6 }}>
                        {statusLabel(p.status)}
                      </Tag>
                      <Tag color={p.priority <= 2 ? "red" : p.priority === 3 ? "orange" : "blue"} style={{ borderRadius: 6 }}>
                        {priorityLabel(p.priority)}
                      </Tag>
                      {renderTypeTag(p.project_type)}
                    </div>
                  </div>
                </div>
                <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 12, height: 36, overflow: "hidden" }} ellipsis>
                  {p.description || t("noDescription")}
                </Text>
                <Progress percent={p.progress || 0} size="small" strokeColor={{ from: "#4F46E5", to: "#7C3AED" }} showInfo={false} />
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{p.start_date || "—"} ~ {p.end_date || "—"}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{p.progress || 0}%</Text>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      )}

      <Modal title={editingProject ? t("edit") : t("create")} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} destroyOnClose width={640}>
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <div style={{ marginBottom: 12 }}>
            <AIAssistButton
              formType="project"
              getValues={() => {
                const v = form.getFieldsValue(true);
                if (v.start_date) v.start_date = v.start_date?.format?.("YYYY-MM-DD");
                if (v.end_date) v.end_date = v.end_date?.format?.("YYYY-MM-DD");
                return v;
              }}
              onApply={(s) => form.setFieldsValue(s)}
              // \u628a\u9879\u76ee\u7c7b\u578b\u7684\u5408\u6cd5 code \u4e0b\u53d1\u7ed9\u540e\u7aef\uff0cAI \u53ea\u4f1a\u5728\u8fd9\u4e9b\u53d6\u503c\u91cc\u9009\uff0c
              // \u907f\u514d\u56de\u586b\u4e00\u4e2a Select \u91cc\u4e0d\u5b58\u5728\u7684\u503c\u5bfc\u81f4\u4e0b\u62c9\u6846\u7a7a\u767d
              options={{ project_type: types.map((t) => ({ value: t.code, label: t.name })) }}
              dateFields={["start_date", "end_date"]}
            />
          </div>
          <Form.Item label={t("form.name")} name="name" rules={[{ required: true, message: t("form.nameRequired") }]}><Input placeholder="e.g.: Smart City Management System / Website Revamp" /></Form.Item>
          <Form.Item label={t("form.description")} name="description"><Input.TextArea rows={2} placeholder={t("form.descriptionPlaceholder")} /></Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label={t("form.status")} name="status" initialValue="planning"><Select style={{ width: 140 }} options={[
              { label: t("statusPlanning"), value: "planning" },
              { label: t("statusInProgress"), value: "active" },
              { label: t("statusDone"), value: "done" },
              { label: t("statusArchived"), value: "archived" },
            ]} /></Form.Item>
            <Form.Item label={t("form.priority")} name="priority" initialValue={3}><Select style={{ width: 120 }} options={[
              { label: t("priorityHigh"), value: 1 },
              { label: t("priorityMedium"), value: 3 },
              { label: t("priorityLow"), value: 5 },
            ]} /></Form.Item>
            <Form.Item label={t("form.projectType")} name="project_type">
              <Select
                placeholder={t("form.projectTypePlaceholder")}
                allowClear
                showSearch
                optionFilterProp="label"
                options={types.map((t) => ({
                  label: (
                    <Space>
                      <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 3, background: t.color, border: "1px solid #d9d9d9" }} />
                      {t.name} <Text type="secondary" style={{ fontSize: 12 }}>{t.code}</Text>
                    </Space>
                  ),
                  value: t.code,
                }))}
              />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item label={t("form.industry")} name="industry_type"><Input placeholder={t("form.industryPlaceholder")} style={{ width: 150 }} /></Form.Item>
            <Form.Item label={t("form.budget")} name="budget"><InputNumber min={0} prefix="¥" style={{ width: 150 }} placeholder={t("form.budgetPlaceholder")} /></Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item label={t("form.startDate")} name="start_date"><DatePicker style={{ width: 150 }} /></Form.Item>
            <Form.Item
              label={t("form.endDate")}
              name="end_date"
              dependencies={["start_date"]}
              rules={[
                {
                  validator: async (_rule, value) => {
                    const s = form.getFieldValue("start_date");
                    if (value && s && value.isBefore(s, "day")) {
                      throw new Error(t("form.endDateAfterStart"));
                    }
                  },
                },
              ]}
            >
              <DatePicker
                style={{ width: 150 }}
                disabledDate={(cur) => {
                  const s = form.getFieldValue("start_date");
                  return !!s && !!cur && cur.isBefore(s, "day");
                }}
              />
            </Form.Item>
          </Space>
          <Form.Item><Button type="primary" htmlType="submit" block>{editingProject ? t("saveChanges") : t("create")}</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Projects;
