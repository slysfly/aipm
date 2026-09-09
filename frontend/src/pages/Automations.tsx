import React, { useEffect, useState } from "react";
import {
  Table, Button, Modal, Form, Input, Select, Switch, App, Space, Popconfirm, Tag, Typography,
} from "antd";
import { PlusOutlined, DeleteOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { automationApi, projectApi } from "../api";

const { Text } = Typography;

const TRIGGER_TYPES = [
  { value: "task_created", label: "任务创建" },
  { value: "task_updated", label: "任务更新" },
  { value: "task_status_changed", label: "任务状态变更" },
  { value: "project_created", label: "项目创建" },
];

const ACTION_TEMPLATE = `[
  { "type": "send_notification", "title": "任务已更新", "content": "任务 {{task.name }} 状态变更为 {{task.status}}" },
  { "type": "send_email", "to": "user@example.com", "subject": "任务通知", "body": "任务 {{task.name}} 有更新" }
]`;

const Automations: React.FC = () => {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await automationApi.list();
      setData(Array.isArray(res) ? res : res?.items || []);
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
    form.setFieldsValue({ is_active: true, is_global: false, trigger_type: "task_created", actions: ACTION_TEMPLATE });
    setModalOpen(true);
  };

  const submit = async () => {
    try {
      const v = await form.validateFields();
      const payload = {
        ...v,
        trigger_conditions: safeParse(v.trigger_conditions, {}),
        actions: safeParse(v.actions, []),
      };
      await automationApi.create(payload);
      message.success("规则创建成功");
      setModalOpen(false);
      load();
    } catch (e: any) {
      if (e?.response) message.error(e.response.data?.detail || "保存失败");
      else if (e?.errorFields) message.error("请检查表单与 JSON 格式");
    }
  };

  const toggle = async (row: any) => {
    try {
      await automationApi.toggle(row.id, !row.is_active);
      message.success("状态已切换");
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  const remove = async (id: string) => {
    try {
      await automationApi.remove(id);
      message.success("删除成功");
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "删除失败");
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name" },
    { title: "触发", dataIndex: "trigger_type", render: (t: string) => <Tag icon={<ThunderboltOutlined />} color="blue">{t}</Tag> },
    { title: "项目", dataIndex: "project_id", render: (v: string) => v || <Tag>全局</Tag> },
    {
      title: "启用", dataIndex: "is_active",
      render: (a: boolean, r: any) => <Switch checked={a} onChange={() => toggle(r)} />,
    },
    {
      title: "操作",
      render: (_: any, r: any) => (
        <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>自动化规则</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-tour="auto-new">新建规则</Button>
      </div>
      <Text type="secondary">当任务/项目事件发生时，自动执行通知、邮件、Webhook 等动作（由后端 automation_engine 真实执行）。</Text>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={data} style={{ marginTop: 12 }} data-tour="auto-list" />

      <Modal title="新建自动化规则" open={modalOpen} onOk={submit} onCancel={() => setModalOpen(false)} width={640} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}>
            <Input placeholder="例如：任务完成时通知负责人" />
          </Form.Item>
          <Space size="large">
            <Form.Item name="trigger_type" label="触发类型" rules={[{ required: true }]}>
              <Select options={TRIGGER_TYPES} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="project_id" label="限定项目">
              <Select allowClear style={{ width: 200 }} options={projects.map((p: any) => ({ value: p.id, label: p.name }))} />
            </Form.Item>
          </Space>
          <Space>
            <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>
            <Form.Item name="is_global" label="全局规则" valuePropName="checked"><Switch /></Form.Item>
          </Space>
          <Form.Item name="trigger_conditions" label="触发条件 (JSON，可留空 {})">
            <Input.TextArea rows={3} placeholder='例如：只有任务状态变为 done 时触发：{ "status": "done" }' />
          </Form.Item>
          <Form.Item name="actions" label="动作 (JSON 数组)" rules={[{ required: true }]}>
            <Input.TextArea rows={6} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

function safeParse(text: string, fallback: any) {
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

export default Automations;
