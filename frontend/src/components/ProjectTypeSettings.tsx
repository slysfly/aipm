import React, { useEffect, useState } from "react";
import {
  Card, Table, Button, Modal, Form, Input, InputNumber, Popconfirm, Space, Tag,
  App, Typography, Alert,
} from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import { projectTypeApi } from "../api";

const { Title, Text } = Typography;

interface ProjectTypeItem {
  id: string;
  name: string;
  code: string;
  color: string;
  description?: string | null;
  is_system: boolean;
  sort_order: number;
}

function slugify(text: string): string {
  const s = text.trim().toLowerCase().replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
  if (/[\u4e00-\u9fa5]/.test(s)) return "pt_" + Math.random().toString(36).slice(2, 10);
  return s.slice(0, 50);
}

const ProjectTypeSettings: React.FC = () => {
  const { message } = App.useApp();
  const [types, setTypes] = useState<ProjectTypeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectTypeItem | null>(null);
  const [form] = Form.useForm();
  const [nameDraft, setNameDraft] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const data = await projectTypeApi.list();
      setTypes(Array.isArray(data) ? data : []);
    } catch {
      message.error("加载项目类型失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ color: "#1890ff", sort_order: types.length });
    setNameDraft("");
    setModalOpen(true);
  };

  const openEdit = (t: ProjectTypeItem) => {
    setEditing(t);
    form.setFieldsValue({
      name: t.name,
      code: t.code,
      color: t.color,
      description: t.description || "",
      sort_order: t.sort_order,
    });
    setNameDraft(t.name);
    setModalOpen(true);
  };

  const handleDelete = async (t: ProjectTypeItem) => {
    try {
      await projectTypeApi.remove(t.id);
      message.success("已删除");
      load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail || "删除失败";
      message.error(detail);
    }
  };

  const handleSubmit = async () => {
    const v = await form.validateFields();
    try {
      if (editing) {
        await projectTypeApi.update(editing.id, {
          name: v.name,
          color: v.color,
          description: v.description,
          sort_order: v.sort_order,
        });
        message.success("已保存");
      } else {
        await projectTypeApi.create({
          name: v.name,
          code: v.code ? v.code.trim() : slugify(v.name),
          color: v.color,
          description: v.description,
          sort_order: v.sort_order ?? types.length,
        });
        message.success("已创建");
      }
      setModalOpen(false);
      load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail || "保存失败";
      message.error(detail);
    }
  };

  const columns = [
    {
      title: "颜色",
      dataIndex: "color",
      width: 70,
      render: (c: string) => (
        <span style={{ display: "inline-block", width: 18, height: 18, borderRadius: 4, background: c || "#1890ff", border: "1px solid #d9d9d9" }} />
      ),
    },
    { title: "名称", dataIndex: "name" },
    {
      title: "标识(code)",
      dataIndex: "code",
      render: (code: string, r: ProjectTypeItem) => (
        <Space>
          <Text code>{code}</Text>
          {r.is_system && <Tag color="blue">系统</Tag>}
        </Space>
      ),
    },
    { title: "描述", dataIndex: "description", render: (d: string) => d || "—" },
    { title: "排序", dataIndex: "sort_order", width: 70 },
    {
      title: "操作",
      width: 140,
      render: (_: any, r: ProjectTypeItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除该类型？" description="被项目引用时无法删除" onConfirm={() => handleDelete(r)} okText="删除" cancelText="取消">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <Title level={5} style={{ margin: 0 }}>项目类型管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增类型</Button>
      </div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="项目类型用于替代原先写死的方法论/类型枚举，可由管理员在此统一定义（名称 + 颜色 + 标识）。创建后标识不可修改，以保证已有项目的引用不失效。"
      />
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={types}
        columns={columns}
        pagination={false}
      />

      <Modal
        title={editing ? "编辑项目类型" : "新增项目类型"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item label="名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="例如：敏捷研发 / 外包交付 / 咨询项目" onChange={(e) => { if (!editing) setNameDraft(e.target.value); }} />
          </Form.Item>
          <Form.Item
            label="标识(code)"
            name="code"
            extra={editing ? "标识创建后不可修改" : "留空则按名称自动生成；创建后不可修改，作为项目引用的稳定键"}
          >
            <Input disabled={!!editing} placeholder={slugify(nameDraft || "新类型")} />
          </Form.Item>
          <Form.Item label="颜色" name="color">
            <Input type="color" style={{ width: 60, padding: 2 }} />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
          <Form.Item label="排序" name="sort_order">
            <InputNumber min={0} style={{ width: 120 }} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ProjectTypeSettings;
