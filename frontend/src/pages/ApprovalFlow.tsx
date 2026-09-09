import React, { useState, useEffect } from "react";
import { Card, Typography, Tag, Button, Space, Table, Modal, Form, Input, Select, App, Row, Col, Statistic, Popconfirm } from "antd";
import { PlusOutlined, CheckCircleOutlined, CloseCircleOutlined, AuditOutlined, DeleteOutlined, ClockCircleOutlined } from "@ant-design/icons";
import { approvalApi } from "../api";

const { Title, Text } = Typography;

interface Flow {
  id: string;
  name: string;
  description?: string;
  entity_type: string;
  is_active: boolean;
  steps: any[];
}

const ENTITY_OPTIONS = [
  { label: "任务审批", value: "task" },
  { label: "预算审批", value: "budget" },
  { label: "请假审批", value: "leave" },
  { label: "费用审批", value: "expense" },
];

const ApprovalFlow: React.FC = () => {
  const { message } = App.useApp();
  const [flows, setFlows] = useState<Flow[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [stats, setStats] = useState<any>({});
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const r = await approvalApi.listFlows();
      const items: any[] = r?.items || r || [];
      setFlows(
        items.map((f: any) => ({
          id: f.id,
          name: f.name,
          description: f.description,
          entity_type: f.entity_type,
          is_active: f.is_active,
          steps: f.steps || [],
        }))
      );
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载审批流程失败");
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try { const d = await approvalApi.dashboard(); setStats(d || {}); } catch { /* ignore */ }
  };

  useEffect(() => { load(); loadStats(); }, []);

  const onCreate = async () => {
    const v = await form.validateFields();
    try {
      await approvalApi.createFlow({ name: v.name, description: v.description, entity_type: v.entity_type, steps: [] });
      message.success("审批流程已创建");
      setModalOpen(false); form.resetFields(); load(); loadStats();
    } catch (e: any) { message.error(e?.response?.data?.detail || "创建失败"); }
  };

  const onToggle = async (f: Flow) => {
    try {
      if (f.is_active) await approvalApi.deactivateFlow(f.id);
      else await approvalApi.activateFlow(f.id);
      message.success("状态已更新"); load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "操作失败"); }
  };

  const onDelete = async (id: string) => {
    try { await approvalApi.removeFlow(id); message.success("已删除"); load(); loadStats(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "删除失败"); }
  };

  const columns = [
    { title: "流程名称", dataIndex: "name", key: "name", render: (n: string) => <Text strong>{n}</Text> },
    { title: "类型", dataIndex: "entity_type", key: "entity_type", render: (t: string) => <Tag>{ENTITY_OPTIONS.find(o => o.value === t)?.label || t}</Tag> },
    { title: "步骤数", key: "steps", render: (_: any, r: Flow) => r.steps?.length || 0 },
    { title: "状态", key: "status", render: (_: any, r: Flow) => <Tag color={r.is_active ? "green" : "default"}>{r.is_active ? "启用" : "停用"}</Tag> },
    { title: "操作", key: "action", render: (_: any, r: Flow) => (
      <Space>
        <Button size="small" onClick={() => onToggle(r)}>{r.is_active ? "停用" : "启用"}</Button>
        <Popconfirm title="确认删除该流程?" onConfirm={() => onDelete(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      </Space>
    ) },
  ];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>审批流引擎</Title>
          <Text type="secondary">多级审批 · 自定义流程 · 全链路追踪</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建流程</Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={8}><Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B, #D97706)" }}>
          <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>待审批</span>} value={stats.pending_count ?? 0} prefix={<AuditOutlined />} valueStyle={{ color: "#fff" }} /></Card></Col>
        <Col xs={8}><Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981, #059669)" }}>
          <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>已批准</span>} value={stats.approved_count ?? 0} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff" }} /></Card></Col>
        <Col xs={8}><Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #EF4444, #DC2626)" }}>
          <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>已拒绝</span>} value={stats.rejected_count ?? 0} prefix={<CloseCircleOutlined />} valueStyle={{ color: "#fff" }} /></Card></Col>
      </Row>

      <Card title="审批流程列表" style={{ borderRadius: 16 }} className="card-hover">
        <Table dataSource={flows} columns={columns} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} className="enhanced-table"
          locale={{ emptyText: <span><ClockCircleOutlined /> 暂无流程，点击右上角新建</span> }} />
      </Card>

      <Modal title="新建审批流程" open={modalOpen} onOk={onCreate} onCancel={() => setModalOpen(false)} okText="创建" cancelText="取消" destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item label="流程名称" name="name" rules={[{ required: true, message: "请输入流程名称" }]}>
            <Input placeholder="例如：预算审批流程" />
          </Form.Item>
          <Form.Item label="类型" name="entity_type" rules={[{ required: true, message: "请选择类型" }]}>
            <Select options={ENTITY_OPTIONS} placeholder="选择审批类型" />
          </Form.Item>
          <Form.Item label="说明" name="description">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ApprovalFlow;
