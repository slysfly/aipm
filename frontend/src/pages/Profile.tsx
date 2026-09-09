import React, { useEffect, useState } from "react";
import {
  Card, Descriptions, Tag, Button, App, Typography, Form, Input,
  Space, Divider, Alert, Table, Popconfirm, Modal, Select,
  InputNumber, Tabs, Row, Col, Statistic, Badge,
} from "antd";
import {
  UserOutlined, PhoneOutlined, MailOutlined,
  EditOutlined, SaveOutlined, ReloadOutlined,
  PlusOutlined, CreditCardOutlined, BankOutlined,
  ThunderboltOutlined, SafetyCertificateOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import { get, put, post } from "../api/http";
import { useAuth } from "../store/AuthContext";

const { Title, Text } = Typography;

interface UserProfile {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  phone?: string | null;
  department?: string | null;
  position?: string | null;
  is_superuser: boolean;
  is_org_admin: boolean;
  is_active: boolean;
  level_code: string;
  level_points: number;
  last_login?: string | null;
  created_at?: string | null;
  organizations: Array<{
    org_id: string;
    org_name: string;
    plan_name: string;
    expire_at?: string | null;
    role_in_org: string;
  }>;
}

interface Order {
  id: string;
  org_id: string;
  type: string;
  amount: number;
  status: string;
  payment_method: string;
  paid_at?: string | null;
  created_at?: string | null;
}

interface Refund {
  id: string;
  order_id: string;
  amount: number;
  reason: string;
  method: string;
  status: string;
  handled_at?: string | null;
  created_at?: string | null;
}

interface AdminUser {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  is_superuser: boolean;
  is_org_admin: boolean;
  is_active: boolean;
  level_code: string;
  created_at?: string | null;
  last_login?: string | null;
}

const Profile: React.FC = () => {
  const { message } = App.useApp();
  const { user } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form] = Form.useForm();
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [rechargeForm] = Form.useForm();
  const [plans, setPlans] = useState<any[]>([]);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [refundOpen, setRefundOpen] = useState(false);
  const [refundForm] = Form.useForm();
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [roleTarget, setRoleTarget] = useState<AdminUser | null>(null);
  const [roleForm] = Form.useForm();

  const loadProfile = async () => {
    try {
      const data = await get("/profile/me");
      setProfile(data);
      form.setFieldsValue({
        full_name: data.full_name,
        phone: data.phone,
        department: data.department,
        position: data.position,
      });
    } catch (e) {
      message.error("加载个人信息失败");
    }
  };

  const loadOrders = async () => {
    try {
      const data = await get("/profile/orders");
      setOrders(Array.isArray(data) ? data : []);
    } catch { setOrders([]); }
  };

  const loadRefunds = async () => {
    try {
      const data = await get("/profile/refunds");
      setRefunds(Array.isArray(data) ? data : []);
    } catch { setRefunds([]); }
  };

  const loadAdminUsers = async () => {
    if (!user?.is_superuser) return;
    try {
      const data = await get("/profile/users");
      setAdminUsers(Array.isArray(data) ? data : []);
    } catch { setAdminUsers([]); }
  };

  const loadPlans = async () => {
    try {
      const data = await get("/ucm/plans");
      setPlans(Array.isArray(data) ? data.filter((p: any) => p.is_active !== false) : []);
    } catch { setPlans([]); }
  };

  const loadOrgs = async () => {
    try {
      const data = await get("/ucm/organizations");
      setOrgs(Array.isArray(data) ? data : []);
    } catch { setOrgs([]); }
  };

  useEffect(() => {
    loadProfile();
    loadOrders();
    loadRefunds();
    loadAdminUsers();
    loadPlans();
    loadOrgs();
  }, []);

  const handleSaveProfile = async () => {
    try {
      const values = await form.validateFields();
      await put("/profile/me", values);
      message.success("个人信息已更新");
      setEditing(false);
      await loadProfile();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "更新失败");
    }
  };

  const handleRecharge = async () => {
    try {
      const values = await rechargeForm.validateFields();
      const res = await post("/profile/recharge", values);
      message.success("充值申请已提交");
      setRechargeOpen(false);
      rechargeForm.resetFields();
      await loadOrders();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "充值失败");
    }
  };

  const handleRefund = async () => {
    try {
      const values = await refundForm.validateFields();
      const res = await post("/profile/refund", values);
      message.success("退费申请已提交，等待管理员审批");
      setRefundOpen(false);
      refundForm.resetFields();
      await loadRefunds();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "退费失败");
    }
  };

  const handleUpdateUserRole = async (userId: string, values: any) => {
    try {
      await put(`/api/v1/profile/users/${userId}/role`, values);
      message.success("用户角色已更新");
      setRoleModalOpen(false);
      await loadAdminUsers();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "更新失败");
    }
  };

  const orderStatusColor = { unpaid: "orange", paid: "green", refunded: "blue", cancelled: "red" };
  const refundStatusColor = { pending: "orange", done: "green", rejected: "red" };

  const orderColumns = [
    { title: "订单ID", dataIndex: "id", render: (v: string) => v.slice(0, 8) + "..." },
    { title: "类型", dataIndex: "type", render: (v: string) => ({ subscription: "新购", renew: "续费", addon: "增购", topup: "充值" })[v] || v },
    { title: "金额", dataIndex: "amount", render: (v: number) => "▥" + v.toFixed(2) },
    { title: "状态", dataIndex: "status", render: (v: string) => <Tag color={orderStatusColor[v]}>{v}</Tag> },
    { title: "创建时间", dataIndex: "created_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
    { title: "支付时间", dataIndex: "paid_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
  ];

  const refundColumns = [
    { title: "订单ID", dataIndex: "order_id", render: (v: string) => v.slice(0, 8) + "..." },
    { title: "金额", dataIndex: "amount", render: (v: number) => "▥" + v.toFixed(2) },
    { title: "原因", dataIndex: "reason" },
    { title: "状态", dataIndex: "status", render: (v: string) => <Tag color={refundStatusColor[v]}>{v}</Tag> },
    { title: "申请时间", dataIndex: "created_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
    { title: "处理时间", dataIndex: "handled_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
  ];

  const adminUserColumns = [
    { title: "用户名", dataIndex: "username" },
    { title: "姓名", dataIndex: "full_name", render: (v: string) => v || "-" },
    { title: "邮箱", dataIndex: "email" },
    { title: "等级", dataIndex: "level_code", render: (v: string) => <Tag>{v}</Tag> },
    { title: "角色", dataIndex: "is_superuser", render: (_: any, r: AdminUser) => (
      r.is_superuser ? <Tag color="purple">系统管理</Tag> :
      r.is_org_admin ? <Tag color="blue">组织管理</Tag> :
      <Tag>用户</Tag>
    ) },
    { title: "状态", dataIndex: "is_active", render: (v: boolean) => v ? <Badge status="success" text="正常" /> : <Badge status="error" text="禁用" /> },
    { title: "最后登录", dataIndex: "last_login", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "从未登录" },
    {
      title: "操作", key: "action", render: (_: any, r: AdminUser) => (
        <Button size="small" onClick={() => {
          setRoleTarget(r);
          roleForm.setFieldsValue({ is_superuser: r.is_superuser, is_org_admin: r.is_org_admin, is_active: r.is_active });
          setRoleModalOpen(true);
        }}>管理角色</Button>
      ),
    },
  ];

  const orgTabs = profile?.organizations?.map((org) => ({
    key: org.org_id,
    label: org.org_name,
    children: (
      <Card size="small" title="组织信息">
        <Descriptions column={2} size="small">
          <Descriptions.Item label="组织名称">{org.org_name}</Descriptions.Item>
          <Descriptions.Item label="组织内角色">{org.role_in_org}</Descriptions.Item>
          <Descriptions.Item label="当前套餐">{org.plan_name}</Descriptions.Item>
          <Descriptions.Item label="到期时间">{org.expire_at ? dayjs(org.expire_at).format("YYYY-MM-DD") : "永久"}</Descriptions.Item>
        </Descriptions>
      </Card>
    ),
  })) || [];

  return (
    <div style={{ padding: "24px" }}>
      <Title level={2}>个人中心</Title>

      <Tabs items={[
        {
          key: "profile",
          label: "个人信息",
          children: (
            <Card
              title="基本信息"
              extra={
                <Button icon={editing ? <SaveOutlined /> : <EditOutlined />} onClick={() => editing ? handleSaveProfile() : setEditing(true)}>
                  {editing ? "保存" : "编辑"}
                </Button>
              }
            >
              <Form form={form} layout="vertical" disabled={!editing}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="full_name" label="姓名">
                      <Input prefix={<UserOutlined />} placeholder="请输入姓名" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="phone" label="电话">
                      <Input prefix={<PhoneOutlined />} placeholder="请输入电话" />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="department" label="部门">
                      <Input placeholder="请输入部门" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="position" label="职位">
                      <Input placeholder="请输入职位" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="email" label="邮箱">
                  <Input prefix={<MailOutlined />} disabled />
                  <Text type="secondary" style={{ fontSize: 12 }}>邮箱不可修改，请联系管理员</Text>
                </Form.Item>
              </Form>
            </Card>
          ),
        },
        {
          key: "orgs",
          label: "我的组织",
          children: orgTabs.length > 0 ? <Tabs items={orgTabs} /> : <Alert message="您尚未加入任何组织" type="info" />,
        },
        {
          key: "orders",
          label: "充值记录",
          children: (
            <div>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setRechargeOpen(true)}>申请充值</Button>
                <Button icon={<ReloadOutlined />} onClick={loadOrders}>刷新</Button>
              </Space>
              <Table columns={orderColumns} dataSource={orders} rowKey="id" loading={loading} />
            </div>
          ),
        },
        {
          key: "refunds",
          label: "退费申请",
          children: (
            <div>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setRefundOpen(true)}>申请退费</Button>
                <Button icon={<ReloadOutlined />} onClick={loadRefunds}>刷新</Button>
              </Space>
              <Table columns={refundColumns} dataSource={refunds} rowKey="id" loading={loading} />
            </div>
          ),
        },
        ...(user?.is_superuser ? [{
          key: "admin",
          label: "用户管理",
          children: (
            <div>
              <Space style={{ marginBottom: 16 }}>
                <Button icon={<ReloadOutlined />} onClick={loadAdminUsers}>刷新</Button>
              </Space>
              <Table columns={adminUserColumns} dataSource={adminUsers} rowKey="id" loading={loading} />
            </div>
          ),
        }] : []),
      ]} />

      {/* 充值Modal */}
      <Modal title="申请充值" open={rechargeOpen} onOk={handleRecharge} onCancel={() => setRechargeOpen(false)} width={520}>
        <Form form={rechargeForm} layout="vertical">
          <Form.Item name="org_id" label="选择组织" rules={[{ required: true }]}>
            <Select placeholder="选择组织" options={orgs.map((o: any) => ({ label: o.name, value: o.id }))} />
          </Form.Item>
          <Form.Item name="plan_id" label="选择套餐" rules={[{ required: true }]}>
            <Select placeholder="选择套餐" options={plans.map((p: any) => ({
              label: p.name,
              value: p.id,
            }))} />
          </Form.Item>
          <Form.Item name="billing_cycle" label="账期" rules={[{ required: true }]}>
            <Select options={[{ label: "月付", value: "monthly" }, { label: "年付", value: "yearly" }]} />
          </Form.Item>
          <Form.Item name="payment_method" label="支付方式" rules={[{ required: true }]}>
            <Select options={[
              { label: "银行转账", value: "manual_bank" },
              { label: "支付宝", value: "alipay" },
              { label: "微信支付", value: "wechat" },
            ]} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="如：合同编号、转账流水号" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 退费Modal */}
      <Modal title="申请退费" open={refundOpen} onOk={handleRefund} onCancel={() => setRefundOpen(false)} width={520}>
        <Form form={refundForm} layout="vertical">
          <Form.Item name="order_id" label="订单ID" rules={[{ required: true, message: "请输入订单ID" }]}>
            <Input placeholder="请输入要退费的订单ID（前8位即可）" />
          </Form.Item>
          <Form.Item name="amount" label="退费金额" rules={[{ required: true }]}>
            <InputNumber prefix={<BankOutlined />} min={0} style={{ width: "100%" }} placeholder="请输入退费金额" />
          </Form.Item>
          <Form.Item name="reason" label="退费原因" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="请说明退费原因" />
          </Form.Item>
          <Form.Item name="method" label="退费方式" rules={[{ required: true }]}>
            <Select options={[
              { label: "原路退回", value: "original_method" },
              { label: "银行转账", value: "bank_transfer" },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 角色管理Modal */}
      <Modal
        title="管理用户角色"
        open={roleModalOpen}
        onOk={() => roleTarget && handleUpdateUserRole(roleTarget.id, roleForm.getFieldsValue())}
        onCancel={() => setRoleModalOpen(false)}
        width={480}
      >
        {roleTarget && (
          <Alert
            style={{ marginBottom: 16 }}
            type="info"
            message="请选择要充值的组织"
          />
        )}
        <Form form={roleForm} layout="vertical">
          <Form.Item name="is_superuser" valuePropName="checked">
            <Tag.CheckableTag checked={false} onChange={(c) => roleForm.setFieldValue("is_superuser", c)}>
              系统管理员（可操作系统全部功能）
            </Tag.CheckableTag>
          </Form.Item>
          <Form.Item name="is_org_admin" valuePropName="checked">
            <Tag.CheckableTag checked={false} onChange={(c) => roleForm.setFieldValue("is_org_admin", c)}>
              组织管理员（可管理用户和收费）
            </Tag.CheckableTag>
          </Form.Item>
          <Form.Item name="is_active" valuePropName="checked">
            <Tag.CheckableTag checked={roleTarget?.is_active ?? true} onChange={(c) => roleForm.setFieldValue("is_active", c)}>
              账号正常（勾选=禁用，取消=启用）
            </Tag.CheckableTag>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Profile;
