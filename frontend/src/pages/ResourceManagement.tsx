import React, { useState, useEffect } from "react";
import { Card, Typography, Row, Col, Tag, Button, Progress, Space, App, Empty, Table, Statistic, Modal, Form, Input, InputNumber, Select, Segmented } from "antd";
import { PlusOutlined, TeamOutlined, BarChartOutlined, ClockCircleOutlined, WarningOutlined, EditOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { resourceApi } from "../api";
import ResourceCalendar from "./ResourceCalendar";

const { Title, Text } = Typography;

/** 与后端 Resource 模型完全一致：不含 allocation/projects/totalHours 等假字段 */
interface Resource {
  id: string;
  name: string;
  resource_type: string;
  skills: string[];
  capacity: number;
  cost_rate: number;
  department: string;
  is_active: boolean;
}

const mapResource = (r: any): Resource => ({
  id: r.id,
  name: r.name,
  resource_type: r.resource_type || "person",
  skills: r.skills || [],
  capacity: typeof r.capacity === "number" ? r.capacity : 0,
  cost_rate: typeof r.cost_rate === "number" ? r.cost_rate : 0,
  department: r.department || "—",
  is_active: r.is_active !== false,
});

const TYPE_LABEL: Record<string, string> = { person: "人力", equipment: "设备", material: "物料", budget: "预算", external: "外部" };

const ResourceManagement: React.FC = () => {
  const { message } = App.useApp();
  const [members, setMembers] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Resource | null>(null);
  const [view, setView] = useState<"ledger" | "calendar">("ledger");
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await resourceApi.list();
      const items: any[] = r?.items || r || [];
      setMembers(items.map(mapResource));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载资源失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const avgCapacity = members.length
    ? Math.round(members.reduce((s, m) => s + (m.capacity || 0), 0) / members.length)
    : 0;

  const handleCreate = async () => {
    const v = await form.validateFields();
    try {
      if (editing) {
        await resourceApi.update(editing.id, {
          name: v.name,
          resource_type: v.resource_type || "person",
          capacity: v.capacity || 8,
          cost_rate: v.cost_rate || 0,
          skills: (v.skills || "").split(/[,，]/).map((s: string) => s.trim()).filter(Boolean),
          department: v.department || undefined,
        });
        message.success("资源已更新");
      } else {
        await resourceApi.create({
          name: v.name,
          resource_type: v.resource_type || "person",
          capacity: v.capacity || 8,
          cost_rate: v.cost_rate || 0,
          skills: (v.skills || "").split(/[,，]/).map((s: string) => s.trim()).filter(Boolean),
          department: v.department || undefined,
        });
        message.success("资源已添加");
      }
      setModalOpen(false); setEditing(null); form.resetFields(); load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "操作失败"); }
  };

  const openEdit = (r: Resource) => {
    setEditing(r);
    form.setFieldsValue({
      name: r.name,
      resource_type: r.resource_type,
      capacity: r.capacity,
      cost_rate: r.cost_rate,
      skills: (r.skills || []).join(", "),
      department: r.department === "—" ? undefined : r.department,
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    try { await resourceApi.remove(id); message.success("已删除"); load(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "删除失败"); }
  };

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>资源管理</Title>
          <Text type="secondary">PMI中国AI项目管理社区 资源管理 · 容量规划 · 技能矩阵</Text>
        </div>
        <Space>
          <Button data-tour="res-new" type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>添加资源</Button>
          <Segmented
            value={view}
            onChange={(v) => setView(v as "ledger" | "calendar")}
            options={[{ label: "资源台账", value: "ledger" }, { label: "资源日历", value: "calendar" }]}
          />
        </Space>
      </div>

      {view === "ledger" && (
      <>
      {loading && members.length === 0 && <Empty description="加载中..." style={{ marginTop: 40 }} />}

      {/* 统计 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>资源总数</span>} value={members.length} prefix={<TeamOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>平均日产能</span>} value={`${avgCapacity}h`} prefix={<BarChartOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>技能标签</span>} value={members.reduce((s, m) => s + (m.skills?.length || 0), 0)} prefix={<ClockCircleOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #EF4444 0%, #DC2626 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>活跃资源</span>} value={members.filter(m => m.is_active).length} prefix={<WarningOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
      </Row>

      {/* 资源列表 */}
      <Card title="资源列表" style={{ borderRadius: 16, marginBottom: 24 }} className="card-hover" loading={loading}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {members.map((m, idx) => (
            <motion.div key={m.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.05 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(m)} style={{ flexShrink: 0 }} />
                <div style={{ width: 120, flexShrink: 0 }}>
                  <Text strong style={{ fontSize: 12 }}>{m.name}</Text>
                  <Text type="secondary" style={{ fontSize: 10, display: "block" }}>{m.department}</Text>
                </div>
                <div style={{ flex: 1 }}>
                  <Space size={4} wrap>
                    <Tag color="blue" style={{ borderRadius: 4, fontSize: 10 }}>{TYPE_LABEL[m.resource_type] || m.resource_type}</Tag>
                    {(m.skills || []).map((s: string) => <Tag key={s} style={{ borderRadius: 4, fontSize: 10 }}>{s}</Tag>)}
                    {(!m.skills || m.skills.length === 0) && <Text type="secondary" style={{ fontSize: 11 }}>暂无技能标签</Text>}
                  </Space>
                </div>
                <div style={{ width: 90, textAlign: "right" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{m.capacity}h/天</Text>
                  <div>{m.is_active ? <Tag color="green" style={{ fontSize: 10 }}>活跃</Tag> : <Tag style={{ fontSize: 10 }}>停用</Tag>}</div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </Card>

      {/* 技能矩阵 / 资源容量 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="技能矩阵" style={{ borderRadius: 16 }} className="card-hover">
            <Table dataSource={members} rowKey="id" pagination={false} className="enhanced-table"
              columns={[
                { title: "成员", dataIndex: "name", key: "name", render: (n: string) => <Text strong>{n}</Text> },
                { title: "部门", dataIndex: "department", key: "department" },
                { title: "技能标签", dataIndex: "skills", key: "skills", render: (skills: string[]) => (
                  <Space size={4}>{(skills || []).map(s => <Tag key={s} style={{ borderRadius: 4, fontSize: 10 }}>{s}</Tag>)}</Space>
                )},
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="资源容量" style={{ borderRadius: 16 }} className="card-hover"
            extra={<Button size="small" danger type="link" disabled>删除请在列表中操作</Button>}
          >
            <Table data-tour="res-alloc" dataSource={members} rowKey="id" pagination={false} className="enhanced-table"
              columns={[
                { title: "成员", dataIndex: "name", key: "name", render: (n: string) => <Text strong>{n}</Text> },
                { title: "日产能", dataIndex: "capacity", key: "capacity", render: (c: number) => <Tag color="blue">{c}h</Tag> },
                { title: "成本费率", dataIndex: "cost_rate", key: "cost_rate", render: (v: number) => <Text type="secondary">{v || 0}</Text> },
                {
                  title: "操作", key: "action", render: (_: any, r: Resource) => (
                    <Space>
                      <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
                      <Button size="small" danger type="link" icon={<WarningOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Modal title={editing ? "编辑资源" : "添加资源"} open={modalOpen} onOk={handleCreate} onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields(); }} okText={editing ? "保存" : "添加"} cancelText="取消" destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item label="资源名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="例如：张明" />
          </Form.Item>
          <Form.Item label="资源类型" name="resource_type" initialValue="person">
            <Select options={Object.entries(TYPE_LABEL).map(([v, l]) => ({ label: l, value: v }))} />
          </Form.Item>
          <Form.Item label="部门" name="department">
            <Input placeholder="例如：研发部" />
          </Form.Item>
          <Form.Item label="日产能 (小时)" name="capacity" initialValue={8}>
            <InputNumber min={0} max={24} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item label="成本费率 (元/小时)" name="cost_rate" initialValue={0}>
            <InputNumber min={0} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item label="技能 (逗号分隔)" name="skills">
            <Input placeholder="例如：Python, FastAPI, AI" />
          </Form.Item>
        </Form>
      </Modal>
      </>
      )}
      {view === "calendar" && <ResourceCalendar />}
    </div>
  );
};

export default ResourceManagement;
