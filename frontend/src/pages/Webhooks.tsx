import React, { useEffect, useState } from "react";
import {
  Table, Button, Modal, Form, Input, Select, App, Space, Popconfirm, Tag, Typography,
} from "antd";
import { PlusOutlined, DeleteOutlined, ApiOutlined, SendOutlined } from "@ant-design/icons";
import { webhookApi, projectApi } from "../api";

const { Text } = Typography;

const EVENT_OPTIONS = [
  { value: "task.created", label: "任务创建" },
  { value: "task.updated", label: "任务更新" },
  { value: "task.completed", label: "任务完成" },
  { value: "project.created", label: "项目创建" },
];

const Webhooks: React.FC = () => {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await webhookApi.list();
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
  }, []);

  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({ events: ["task.created"] });
    setModalOpen(true);
  };

  const submit = async () => {
    try {
      const v = await form.validateFields();
      await webhookApi.create({ ...v, project_id: v.project_id || null });
      message.success("Webhook 创建成功");
      setModalOpen(false);
      load();
    } catch (e: any) {
      if (e?.response) message.error(e.response.data?.detail || "保存失败");
    }
  };

  const test = async (id: string) => {
    try {
      const res = await webhookApi.test(id);
      message.info(res?.success ? "测试已发送" : "测试未成功");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "测试失败");
    }
  };

  const remove = async (id: string) => {
    try {
      await webhookApi.remove(id);
      message.success("删除成功");
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "删除失败");
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name" },
    { title: "URL", dataIndex: "url", ellipsis: true },
    { title: "事件", dataIndex: "events", render: (e: string[]) => (e || []).map((x) => <Tag key={x}>{x}</Tag>) },
    { title: "状态", dataIndex: "is_active", render: (a: boolean) => <Tag color={a ? "green" : "default"}>{a ? "启用" : "停用"}</Tag> },
    {
      title: "操作",
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<SendOutlined />} onClick={() => test(r.id)}>测试</Button>
          <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>Webhook 管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-tour="webhook-new">新建 Webhook</Button>
      </div>
      <Text type="secondary">当任务/项目事件发生时，系统会向配置的 URL 推送事件（签名校验、投递记录可追溯）。</Text>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={data} style={{ marginTop: 12 }} data-tour="webhook-list" />

      <Modal title="新建 Webhook" open={modalOpen} onOk={submit} onCancel={() => setModalOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="例如：内部通知服务 / Jenkins 构建钩子" />
          </Form.Item>
          <Form.Item name="url" label="回调 URL" rules={[{ required: true, type: "url" }]}>
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>
          <Form.Item name="events" label="订阅事件" rules={[{ required: true }]}>
            <Select mode="multiple" options={EVENT_OPTIONS} />
          </Form.Item>
          <Form.Item name="project_id" label="限定项目">
            <Select allowClear options={projects.map((p: any) => ({ value: p.id, label: p.name }))} />
          </Form.Item>
          <Form.Item name="secret" label="签名密钥 (可选)">
            <Input.Password placeholder="用于 X-Hub-Signature 校验" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Webhooks;
