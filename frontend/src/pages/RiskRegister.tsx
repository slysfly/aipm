import React, { useState, useEffect } from "react";
import { Card, Typography, Tag, Table, Button, Space, Modal, Form, Input, Select, Slider, Progress, App, Empty, Row, Col, Statistic, Popconfirm } from "antd";
import { PlusOutlined, AlertOutlined, WarningOutlined, CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, DeleteOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { riskApi, projectApi } from "../api";

const { Title, Text } = Typography;

/** 后端 Risk 字段量纲：probability / impact / risk_score 均为 0-1，前端直接使用，不做任何换算 */
interface Risk {
  id: string;
  title: string;
  description: string;
  category: string;
  probability: number; // 0-1
  impact: number; // 0-1
  score: number; // 0-1 = probability * impact
  status: string;
  owner: string;
  response: string;
  responseStrategy: string;
  createdAt: string;
}

const CATEGORIES = ["技术", "进度", "成本", "质量", "资源", "市场", "法律合规", "安全"];
const STRATEGIES = ["规避", "转移", "减轻", "接受", "开拓", "分享", "提高"];

const mapRisk = (r: any): Risk => ({
  id: r.id,
  title: r.name,
  description: r.description || "",
  category: r.category || "技术",
  probability: typeof r.probability === "number" ? r.probability : 0.5,
  impact: typeof r.impact === "number" ? r.impact : 0.5,
  score: typeof r.risk_score === "number" ? r.risk_score : (r.probability || 0) * (r.impact || 0),
  status: r.status,
  owner: r.owner_id || "",
  response: r.response_plan || "",
  responseStrategy: r.response_strategy || "减轻",
  createdAt: (r.created_at || "").slice(0, 10),
});

const pct = (v: number) => `${Math.round(v * 100)}%`;

const getScoreColor = (score: number) => {
  if (score >= 0.5) return "#EF4444";
  if (score >= 0.25) return "#F59E0B";
  if (score >= 0.1) return "#3B82F6";
  return "#10B981";
};

const getScoreLabel = (score: number) => {
  if (score >= 0.5) return "极高";
  if (score >= 0.25) return "高";
  if (score >= 0.1) return "中";
  return "低";
};

/** 把 0-1 概率/影响映射到 1-5 的矩阵格（仅用于热力图定位，不改变存储值） */
const band = (v: number) => Math.min(5, Math.max(1, Math.round(v * 5)));

const RiskRegister: React.FC = () => {
  const { message } = App.useApp();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRisk, setEditingRisk] = useState<Risk | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await riskApi.list(projectId ? { project_id: projectId } : {});
      const items: any[] = r?.items || r || [];
      setRisks(items.map(mapRisk));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载风险失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [projectId]);
  useEffect(() => {
    projectApi.list().then((r: any) => setProjects(r?.items || r || [])).catch(() => {});
  }, []);

  const handleCreate = () => {
    setEditingRisk(null);
    form.resetFields();
    form.setFieldsValue({ category: "技术", probability: 50, impact: 50, status: "identified", responseStrategy: "减轻" });
    setModalOpen(true);
  };

  const handleEdit = (r: Risk) => {
    setEditingRisk(r);
    form.setFieldsValue({
      title: r.title, description: r.description, category: r.category,
      probability: Math.round(r.probability * 100), impact: Math.round(r.impact * 100),
      status: r.status, owner: r.owner, responseStrategy: r.responseStrategy, response: r.response,
    });
    setModalOpen(true);
  };

  /** 表单用百分比(0-100)输入，仅在提交边界换算为后端量纲 0-1 */
  const handleSave = async () => {
    const values = await form.validateFields();
    const payload = {
      name: values.title,
      description: values.description,
      category: values.category,
      probability: (values.probability ?? 50) / 100,
      impact: (values.impact ?? 50) / 100,
      status: values.status,
      owner_id: values.owner,
      response_strategy: values.responseStrategy,
      response_plan: values.response,
      project_id: projectId || undefined,
    };
    try {
      if (editingRisk?.id) await riskApi.update(editingRisk.id, payload);
      else await riskApi.create(payload);
      message.success("已保存");
      setModalOpen(false);
      load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "保存失败"); }
  };

  const handleDelete = async (id: string) => {
    try { await riskApi.remove(id); message.success("已删除"); load(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "删除失败"); }
  };

  const getStatusTag = (status: string) => {
    const map: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
      identified: { color: "red", icon: <CloseCircleOutlined />, label: "未处理" },
      analyzing: { color: "orange", icon: <ExclamationCircleOutlined />, label: "分析中" },
      occurred: { color: "volcano", icon: <AlertOutlined />, label: "已发生" },
      monitoring: { color: "blue", icon: <WarningOutlined />, label: "监控中" },
      mitigated: { color: "cyan", icon: <CheckCircleOutlined />, label: "已缓解" },
      closed: { color: "green", icon: <CheckCircleOutlined />, label: "已关闭" },
    };
    const item = map[status] || { color: "default", icon: null, label: status };
    return <Tag color={item.color} icon={item.icon as any}>{item.label}</Tag>;
  };

  const columns = [
    { title: "风险标题", dataIndex: "title", key: "title", render: (t: string) => <Text strong>{t}</Text> },
    { title: "类别", dataIndex: "category", key: "category", render: (c: string) => <Tag style={{ borderRadius: 6 }}>{c}</Tag> },
    { title: "概率", dataIndex: "probability", key: "probability", render: (p: number) => <Tag color={p >= 0.6 ? "red" : p >= 0.3 ? "orange" : "blue"}>{pct(p)}</Tag> },
    { title: "影响", dataIndex: "impact", key: "impact", render: (i: number) => <Tag color={i >= 0.6 ? "red" : i >= 0.3 ? "orange" : "blue"}>{pct(i)}</Tag> },
    {
      title: "风险等级", dataIndex: "score", key: "score", render: (s: number) => (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Progress type="circle" percent={Math.round(s * 100)} size={36} strokeColor={getScoreColor(s)} format={() => ""} />
          <Tag color={getScoreColor(s)} style={{ fontWeight: 600 }}>{getScoreLabel(s)} ({pct(s)})</Tag>
        </div>
      ),
    },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => getStatusTag(s) },
    { title: "负责人", dataIndex: "owner", key: "owner" },
    { title: "应对策略", dataIndex: "responseStrategy", key: "responseStrategy" },
    {
      title: "操作", key: "action", render: (_: any, r: Risk) => (
        <Space>
          <Button type="link" onClick={() => handleEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(r.id)}>
            <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>风险登记册 (Risk Register)</Title>
          <Text type="secondary">PMI中国AI项目管理社区 风险管理 · 识别、分析、应对、监控全流程（概率/影响量纲 0-100%）</Text>
        </div>
        <Space wrap>
          <Select allowClear placeholder="全部项目" style={{ width: 180 }} value={projectId || undefined} onChange={(v) => setProjectId(v || "")} options={projects.map((p: any) => ({ label: p.name, value: p.id }))} />
          <Button data-tour="risk-new" type="primary" icon={<PlusOutlined />} onClick={handleCreate}>识别风险</Button>
        </Space>
      </div>

      {loading && risks.length === 0 && <Empty description="加载中..." style={{ marginTop: 40 }} />}

      {/* 风险统计 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #EF4444 0%, #DC2626 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>未处理风险</span>} value={risks.filter(r => r.status === "identified" || r.status === "occurred").length} prefix={<AlertOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
        <Col xs={12} sm={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B 0%, #D97706 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>应对中</span>} value={risks.filter(r => r.status === "analyzing" || r.status === "mitigating" || r.status === "monitoring").length} prefix={<ExclamationCircleOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
        <Col xs={12} sm={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #3B82F6 0%, #2563EB 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>监控中</span>} value={risks.filter(r => r.status === "monitoring").length} prefix={<WarningOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
        <Col xs={12} sm={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981 0%, #059669 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>已关闭</span>} value={risks.filter(r => r.status === "closed").length} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
      </Row>

      {/* 概率-影响矩阵热力图（量纲与后端一致：0-1） */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={8}>
          <Card title="概率-影响矩阵 (P-I Matrix)" style={{ borderRadius: 16 }} className="card-hover">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4 }}>
              {[5, 4, 3, 2, 1].map((pIdx) => (
                [1, 2, 3, 4, 5].map((iIdx) => {
                  const score = (pIdx / 5) * (iIdx / 5);
                  const color = getScoreColor(score);
                  const count = risks.filter(r => band(r.probability) === pIdx && band(r.impact) === iIdx).length;
                  return (
                    <div key={`${pIdx}-${iIdx}`} style={{ background: color, borderRadius: 4, padding: 6, textAlign: "center", opacity: count > 0 ? 1 : 0.5, minHeight: 36, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Text style={{ color: "#fff", fontSize: 11, fontWeight: count > 0 ? 700 : 400 }}>{count > 0 ? count : "—"}</Text>
                    </div>
                  );
                })
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 10 }}>影响 →</Text>
              <Text type="secondary" style={{ fontSize: 10 }}>概率 ↓</Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="风险热力图分布" style={{ borderRadius: 16 }} className="card-hover">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {["极高", "高", "中", "低"].map(level => {
                const color = level === "极高" ? "#EF4444" : level === "高" ? "#F59E0B" : level === "中" ? "#3B82F6" : "#10B981";
                const count = risks.filter(r => {
                  const s = r.score;
                  if (level === "极高") return s >= 0.5;
                  if (level === "高") return s >= 0.25;
                  if (level === "中") return s >= 0.1;
                  return s < 0.1;
                }).length;
                return (
                  <div key={level} style={{ flex: 1, padding: 16, borderRadius: 12, background: `${color}15`, border: `1px solid ${color}30`, textAlign: "center" }}>
                    <Text style={{ color, fontSize: 24, fontWeight: 800 }}>{count}</Text>
                    <div style={{ color, fontSize: 12, fontWeight: 600, marginTop: 4 }}>{level}</div>
                  </div>
                );
              })}
            </div>
          </Card>
        </Col>
      </Row>

      {/* 风险列表 */}
      <Card title="风险登记册" style={{ borderRadius: 16 }} className="card-hover" loading={loading}>
        <Table data-tour="risk-table" dataSource={risks} columns={columns} rowKey="id" pagination={{ pageSize: 10 }} className="enhanced-table" />
      </Card>

      <Modal title={editingRisk?.id ? "编辑风险" : "识别新风险"} open={modalOpen} onCancel={() => { setModalOpen(false); setEditingRisk(null); }} footer={null} destroyOnClose width={640}>
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item label="风险标题" name="title" rules={[{ required: true, message: "请输入风险标题" }]}>
            <Input placeholder="例如：核心开发人员离职风险" />
          </Form.Item>
          <Form.Item label="详细描述" name="description">
            <Input.TextArea rows={2} placeholder="例如：关键模块只有单一负责人，人员流动可能导致交付延期" />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label="风险类别" name="category" rules={[{ required: true }]}>
              <Select style={{ width: 150 }} options={CATEGORIES.map(c => ({ label: c, value: c }))} />
            </Form.Item>
            <Form.Item label="概率 (%)" name="probability" rules={[{ required: true }]}>
              <Slider min={0} max={100} step={5} marks={{ 0: "0%", 50: "50%", 100: "100%" }} style={{ width: 160 }} tooltip={{ formatter: (v) => `${v}%` }} />
            </Form.Item>
          </Space>
          <Form.Item label="影响 (%)" name="impact" rules={[{ required: true }]}>
            <Slider min={0} max={100} step={5} marks={{ 0: "0%", 50: "50%", 100: "100%" }} tooltip={{ formatter: (v) => `${v}%` }} />
          </Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label="状态" name="status">
              <Select style={{ width: 130 }} options={[
                { label: "未处理", value: "identified" },
                { label: "分析中", value: "analyzing" },
                { label: "已发生", value: "occurred" },
                { label: "监控中", value: "monitoring" },
                { label: "已缓解", value: "mitigated" },
                { label: "已关闭", value: "closed" },
              ]} />
            </Form.Item>
            <Form.Item label="负责人" name="owner">
              <Input placeholder="例如：HR / 技术负责人" style={{ width: 150 }} />
            </Form.Item>
            <Form.Item label="应对策略" name="responseStrategy">
              <Select style={{ width: 130 }} options={STRATEGIES.map(s => ({ label: s, value: s }))} />
            </Form.Item>
          </Space>
          <Form.Item label="应对措施" name="response">
            <Input.TextArea rows={2} placeholder="例如：建立知识共享机制，培养备选人员，降低单点依赖" />
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>{editingRisk?.id ? "保存变更" : "识别风险"}</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RiskRegister;
