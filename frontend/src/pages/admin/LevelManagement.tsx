import React, { useEffect, useState } from "react";
import {
  App, Card, Table, Button, Modal, Form, Input, InputNumber, Select, Space, Typography, Descriptions, Collapse, Alert,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { listLevels, createLevel, getUserLevel, setUserLevel, getLevelRecords } from "../../api/ucm";

const { Title } = Typography;

const LevelManagement: React.FC = () => {
  const { message } = App.useApp();
  const [levels, setLevels] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const [levelOpen, setLevelOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  // 用户级别调整
  const [userId, setUserId] = useState<string>("");
  const [userLevel, setUserLevelData] = useState<any>(null);
  const [records, setRecords] = useState<any[]>([]);
  const [recordsOpen, setRecordsOpen] = useState(false);
  const [setOpen, setSetOpen] = useState(false);
  const [setForm] = Form.useForm();

  const loadLevels = async () => {
    setLoading(true);
    try {
      const res = await listLevels();
      setLevels(Array.isArray(res) ? res : (res?.data || []));
    } catch {
      setLevels([]);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadLevels(); }, []);

  const openCreate = () => {
    form.resetFields();
    setLevelOpen(true);
  };
  const handleCreate = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await createLevel(values);
      message.success("级别已创建");
      setLevelOpen(false);
      await loadLevels();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const handleQuery = async () => {
    if (!userId) {
      message.warning("请输入用户 ID");
      return;
    }
    try {
      const res = await getUserLevel(userId);
      setUserLevelData(res);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "查询失败");
      setUserLevelData(null);
    }
  };

  const openSet = () => {
    setForm.resetFields();
    setForm.setFieldsValue({ level_code: userLevel?.level_code });
    setSetOpen(true);
  };
  const handleSet = async () => {
    if (!userId) return;
    const values = await setForm.validateFields();
    setSaving(true);
    try {
      await setUserLevel(userId, values);
      message.success("用户级别已调整");
      setSetOpen(false);
      await handleQuery();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "调整失败");
    } finally {
      setSaving(false);
    }
  };

  const loadRecords = async () => {
    if (!userId) return;
    try {
      const res = await getLevelRecords(userId);
      setRecords(Array.isArray(res) ? res : (res?.data || []));
    } catch {
      setRecords([]);
    }
  };

  const levelColumns = [
    { title: "级别编码", dataIndex: "code" },
    { title: "级别名称", dataIndex: "name" },
    { title: "所需积分", dataIndex: "min_points" },
    { title: "权益", dataIndex: "benefits", render: (v: any) => v || "-" },
  ];

  const recordColumns = [
    { title: "级别", dataIndex: "level_code" },
    { title: "变更类型", dataIndex: "change_type", render: (v: any) => v || "-" },
    { title: "原因", dataIndex: "reason", render: (v: any) => v || "-" },
    { title: "操作人", dataIndex: "operator_id", render: (v: any) => v || "-" },
    { title: "时间", dataIndex: "created_at", render: (v: any) => v || "-" },
  ];

  return (
    <div>
      <Title level={3}>用户级别管理</Title>
      <Card
        title="级别定义"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadLevels}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-tour="admin-levels-new">新建级别</Button>
          </Space>
        }
      >
        <Table rowKey="code" size="small" loading={loading} dataSource={levels} columns={levelColumns} data-tour="admin-levels-list" />
      </Card>

      <Card title="用户级别调整" style={{ marginTop: 16 }}>
        <Space style={{ marginBottom: 12 }}>
          <Input placeholder="输入用户 ID" value={userId} onChange={(e) => setUserId(e.target.value)} style={{ width: 240 }} />
          <Button type="primary" onClick={handleQuery}>查询</Button>
        </Space>

        {userLevel ? (
          <>
            <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="当前级别">{userLevel.level_code || "-"}</Descriptions.Item>
              <Descriptions.Item label="级别名称">{userLevel.level_name || "-"}</Descriptions.Item>
              <Descriptions.Item label="积分">{userLevel.points ?? "-"}</Descriptions.Item>
            </Descriptions>
            <Space style={{ marginBottom: 12 }}>
              <Button type="primary" onClick={openSet}>调整级别</Button>
              <Button onClick={() => { setRecordsOpen(true); loadRecords(); }}>查看级别记录</Button>
            </Space>
            <Collapse
              activeKey={recordsOpen ? ["records"] : []}
              onChange={(k) => setRecordsOpen(Array.isArray(k) ? k.includes("records") : false)}
              items={[
                {
                  key: "records",
                  label: "级别变更记录",
                  children: <Table rowKey="id" size="small" dataSource={records} columns={recordColumns} pagination={false} />,
                },
              ]}
            />
          </>
        ) : (
          <Alert type="info" showIcon message="输入用户 ID 并点击查询，查看其当前级别与积分。" />
        )}
      </Card>

      <Modal title="新建级别" open={levelOpen} onOk={handleCreate} confirmLoading={saving} onCancel={() => setLevelOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="级别编码" rules={[{ required: true }]}>
            <Input placeholder="如 L1" />
          </Form.Item>
          <Form.Item name="name" label="级别名称" rules={[{ required: true }]}>
            <Input placeholder="如 青铜" />
          </Form.Item>
          <Form.Item name="min_points" label="所需积分" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="benefits" label="权益说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="icon" label="图标（可选）">
            <Input placeholder="图标 URL 或编码" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="调整用户级别" open={setOpen} onOk={handleSet} confirmLoading={saving} onCancel={() => setSetOpen(false)} destroyOnClose>
        <Form form={setForm} layout="vertical">
          <Form.Item name="level_code" label="目标级别" rules={[{ required: true }]}>
            <Select placeholder="选择级别" options={levels.map((l) => ({ label: `${l.name}（${l.code}）`, value: l.code }))} />
          </Form.Item>
          <Form.Item name="reason" label="调整原因">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default LevelManagement;
