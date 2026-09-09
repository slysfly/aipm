import React, { useEffect, useState } from "react";
import {
  App, Card, Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, Typography, Checkbox,
} from "antd";
import { PlusOutlined, EditOutlined, ReloadOutlined } from "@ant-design/icons";
import { listPlans, createPlan, updatePlan, listFeatures } from "../../api/ucm";

const { Title } = Typography;

const PlanManagement: React.FC = () => {
  const { message } = App.useApp();
  const [list, setList] = useState<any[]>([]);
  const [features, setFeatures] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await listPlans();
      setList(Array.isArray(res) ? res : (res?.data || []));
    } catch {
      setList([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    listFeatures().then((res) => setFeatures(Array.isArray(res) ? res : (res?.data || []))).catch(() => setFeatures([]));
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true });
    setModal(true);
  };
  const openEdit = (r: any) => {
    setEditing(r);
    form.resetFields();
    form.setFieldsValue({ ...r, is_active: r.is_active !== false });
    setModal(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updatePlan(editing.id, values);
        message.success("套餐已更新");
      } else {
        await createPlan(values);
        message.success("套餐已创建");
      }
      setModal(false);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const featureOptions = features.map((f: any) => ({ label: f.name, value: f.code }));

  const columns = [
    { title: "套餐名称", dataIndex: "name" },
    { title: "编码", dataIndex: "code" },
    { title: "月价", dataIndex: "price_monthly", render: (v: any) => (v != null ? `¥${v}` : "-") },
    { title: "年价", dataIndex: "price_yearly", render: (v: any) => (v != null ? `¥${v}` : "-") },
    { title: "席位上限", dataIndex: "max_seats" },
    { title: "状态", dataIndex: "is_active", render: (v: any) => (v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>) },
    { title: "描述", dataIndex: "description", render: (v: any) => v || "-" },
    {
      title: "操作", key: "action",
      render: (_: any, r: any) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>套餐管理</Title>
      <Card
        title="套餐列表"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-tour="admin-plans-new">新建套餐</Button>
          </Space>
        }
      >
        <Table rowKey="id" size="small" loading={loading} dataSource={list} columns={columns} data-tour="admin-plans-list" />
      </Card>
      <Modal
        title={editing ? "编辑套餐" : "新建套餐"}
        open={modal}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setModal(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="套餐编码" rules={[{ required: true }]}>
            <Input placeholder="如 pro" />
          </Form.Item>
          <Form.Item name="name" label="套餐名称" rules={[{ required: true }]}>
            <Input placeholder="如 专业版" />
          </Form.Item>
          <Space size="large" wrap>
            <Form.Item name="price_monthly" label="月价" rules={[{ required: true }]}>
              <InputNumber min={0} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="price_yearly" label="年价" rules={[{ required: true }]}>
              <InputNumber min={0} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="max_seats" label="席位上限" rules={[{ required: true }]}>
              <InputNumber min={1} style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="features" label="功能模块（可多选）">
            <Select mode="multiple" allowClear placeholder="选择功能" options={featureOptions} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Checkbox>启用该套餐</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default PlanManagement;
