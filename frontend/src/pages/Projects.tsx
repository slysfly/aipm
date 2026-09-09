import React, { useEffect, useState } from "react";
import { Card, Typography, Tag, Button, Space, Modal, Form, Input, Select, DatePicker, App, Spin, Row, Col, Progress, InputNumber, Empty, Popconfirm } from "antd";
import AIAssistButton from "../components/AIAssistButton";
import { PlusOutlined, SearchOutlined, DeleteOutlined, EditOutlined, FundProjectionScreenOutlined, FilterOutlined, ClearOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { projectApi, projectTypeApi } from "../api";
import dayjs from "dayjs";

const { Title, Text } = Typography;

const Projects: React.FC = () => {
  const navigate = useNavigate();
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
    } catch { /* 忽略，类型缺失时回退显示 code */ }
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
      message.error("加载项目列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [statusFilter]);

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
        message.success("项目已更新");
      } else {
        await projectApi.create(payload);
        message.success("项目已创建");
      }
      setModalOpen(false);
      load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "操作失败"); }
  };

  const handleDelete = async (id: string) => {
    try {
      await projectApi.remove(id);
      message.success("项目已删除");
      load();
    } catch { message.error("删除失败"); }
  };

  const filtered = projects.filter(p => {
    if (search && !p.name?.toLowerCase().includes(search.toLowerCase()) && !p.description?.toLowerCase().includes(search.toLowerCase())) return false;
    if (priorityFilter && p.priority !== priorityFilter) return false;
    return true;
  });

  const getStatusColor = (s: string) => s === "active" ? "green" : s === "planning" ? "blue" : s === "done" ? "default" : "default";

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>项目</Title>
          <Text type="secondary">管理所有项目，支持瀑布、敏捷、混合等多种方法论</Text>
        </div>
        <Space wrap>
          <Input prefix={<SearchOutlined />} placeholder="搜索项目..." value={search} onChange={e => setSearch(e.target.value)} style={{ width: 200, borderRadius: 10 }} allowClear />
          <Select placeholder="状态筛选" allowClear style={{ width: 120 }} value={statusFilter || undefined} onChange={v => setStatusFilter(v || "")}
            options={[{ label: "全部", value: "" }, { label: "进行中", value: "active" }, { label: "规划", value: "planning" }, { label: "已完成", value: "done" }, { label: "已归档", value: "archived" }]} />
          <Select placeholder="优先级" allowClear style={{ width: 110 }} value={priorityFilter || undefined} onChange={(v) => setPriorityFilter(v ?? "")}
            options={[{ label: "全部", value: "" }, { label: "高", value: 1 }, { label: "中", value: 3 }, { label: "低", value: 5 }]} />
          <Button data-tour="proj-new" type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建项目</Button>
        </Space>
      </div>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spin size="large" /></div>
      ) : filtered.length === 0 ? (
        <div className="enhanced-empty">
          <div style={{ fontSize: 60, marginBottom: 16 }}>🚀</div>
          <h3>{search || statusFilter || priorityFilter ? "没有匹配的项目" : "还没有项目"}</h3>
          <p>{search || statusFilter || priorityFilter ? "尝试调整筛选条件" : "创建第一个项目，开启你的项目管理之旅"}</p>
          {!search && !statusFilter && !priorityFilter && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>创建第一个项目</Button>
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
                    title="确认删除该项目？"
                    description="将一并删除其下所有任务与文档，且不可恢复。"
                    okText="删除"
                    okType="danger"
                    cancelText="取消"
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
                        {p.status === "active" ? "进行中" : p.status === "planning" ? "规划" : p.status === "done" ? "已完成" : "归档"}
                      </Tag>
                      <Tag color={p.priority <= 2 ? "red" : p.priority === 3 ? "orange" : "blue"} style={{ borderRadius: 6 }}>
                        {p.priority <= 2 ? "高" : p.priority === 3 ? "中" : "低"}
                      </Tag>
                      {renderTypeTag(p.project_type)}
                    </div>
                  </div>
                </div>
                <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 12, height: 36, overflow: "hidden" }} ellipsis>
                  {p.description || "暂无描述"}
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

      <Modal title={editingProject ? "编辑项目" : "新建项目"} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} destroyOnClose width={640}>
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
            />
          </div>
          <Form.Item label="项目名称" name="name" rules={[{ required: true, message: "请输入项目名称" }]}><Input placeholder="例如：智慧城市管理系统 / 官网改版项目" /></Form.Item>
          <Form.Item label="描述" name="description"><Input.TextArea rows={2} placeholder="例如：在6个月内完成一期建设，覆盖门禁、停车、能耗三大子系统" /></Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label="状态" name="status" initialValue="planning"><Select style={{ width: 140 }} options={[{ label: "规划", value: "planning" }, { label: "进行中", value: "active" }, { label: "已完成", value: "done" }, { label: "已归档", value: "archived" }]} /></Form.Item>
            <Form.Item label="优先级" name="priority" initialValue={3}><Select style={{ width: 120 }} options={[{ label: "高", value: 1 }, { label: "中", value: 3 }, { label: "低", value: 5 }]} /></Form.Item>
            <Form.Item label="项目类型" name="project_type">
              <Select
                placeholder="选择项目类型"
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
            <Form.Item label="行业" name="industry_type"><Input placeholder="例如：IT软件 / 金融 / 制造 / 建筑" style={{ width: 150 }} /></Form.Item>
            <Form.Item label="预算" name="budget"><InputNumber min={0} prefix="¥" style={{ width: 150 }} placeholder="预算金额" /></Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item label="开始日期" name="start_date"><DatePicker style={{ width: 150 }} /></Form.Item>
            <Form.Item label="结束日期" name="end_date"><DatePicker style={{ width: 150 }} /></Form.Item>
          </Space>
          <Form.Item><Button type="primary" htmlType="submit" block>{editingProject ? "保存变更" : "创建项目"}</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Projects;
