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
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation('profile');

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
      message.error(t('profile.loadError'));
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
      message.success(t('profile.updateSuccess'));
      setEditing(false);
      await loadProfile();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t('profile.updateFail'));
    }
  };

  const handleRecharge = async () => {
    try {
      const values = await rechargeForm.validateFields();
      const res = await post("/profile/recharge", values);
      message.success(t('profile.rechargeSuccess'));
      setRechargeOpen(false);
      rechargeForm.resetFields();
      await loadOrders();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t('profile.rechargeFail'));
    }
  };

  const handleRefund = async () => {
    try {
      const values = await refundForm.validateFields();
      const res = await post("/profile/refund", values);
      message.success(t('profile.refundSuccess'));
      setRefundOpen(false);
      refundForm.resetFields();
      await loadRefunds();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t('profile.refundFail'));
    }
  };

  const handleUpdateUserRole = async (userId: string, values: any) => {
    try {
      await put(`/profile/users/${userId}/role`, values);
      message.success(t('profile.roleUpdateSuccess'));
      setRoleModalOpen(false);
      await loadAdminUsers();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || t('profile.roleUpdateFail'));
    }
  };

  const orderStatusColor = { unpaid: "orange", paid: "green", refunded: "blue", cancelled: "red" };
  const refundStatusColor = { pending: "orange", done: "green", rejected: "red" };

  const orderColumns = [
    { title: t('profile.orderId'), dataIndex: "id", render: (v: string) => v.slice(0, 8) + "..." },
    { title: t('profile.type'), dataIndex: "type", render: (v: string) => ({ subscription: t('profile.newPurchase'), renew: t('profile.renewal'), addon: t('profile.addon'), topup: t('profile.topup') })[v] || v },
    { title: t('profile.amount'), dataIndex: "amount", render: (v: number) => "▥" + v.toFixed(2) },
    { title: t('profile.status'), dataIndex: "status", render: (v: string) => <Tag color={orderStatusColor[v]}>{v}</Tag> },
    { title: t('profile.createdAt'), dataIndex: "created_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
    { title: t('profile.paidAt'), dataIndex: "paid_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
  ];

  const refundColumns = [
    { title: t('profile.orderId'), dataIndex: "order_id", render: (v: string) => v.slice(0, 8) + "..." },
    { title: t('profile.amount'), dataIndex: "amount", render: (v: number) => "▥" + v.toFixed(2) },
    { title: t('profile.reason'), dataIndex: "reason" },
    { title: t('profile.status'), dataIndex: "status", render: (v: string) => <Tag color={refundStatusColor[v]}>{v}</Tag> },
    { title: t('profile.applyTime'), dataIndex: "created_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
    { title: t('profile.handleTime'), dataIndex: "handled_at", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-" },
  ];

  const adminUserColumns = [
    { title: t('profile.username'), dataIndex: "username" },
    { title: t('profile.name'), dataIndex: "full_name", render: (v: string) => v || "-" },
    { title: t('profile.email'), dataIndex: "email" },
    { title: t('profile.level'), dataIndex: "level_code", render: (v: string) => <Tag>{v}</Tag> },
    { title: t('profile.role'), dataIndex: "is_superuser", render: (_: any, r: AdminUser) => (
      r.is_superuser ? <Tag color="purple">{t('profile.systemAdmin')}</Tag> :
      r.is_org_admin ? <Tag color="blue">{t('profile.orgAdmin')}</Tag> :
      <Tag>{t('profile.user')}</Tag>
    ) },
    { title: t('profile.status'), dataIndex: "is_active", render: (v: boolean) => v ? <Badge status="success" text={t('profile.active')} /> : <Badge status="error" text={t('profile.disabled')} /> },
    { title: t('profile.lastLogin'), dataIndex: "last_login", render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD HH:mm") : t('profile.neverLogin') },
    {
      title: t('profile.action'), key: "action", render: (_: any, r: AdminUser) => (
        <Button size="small" onClick={() => {
          setRoleTarget(r);
          roleForm.setFieldsValue({ is_superuser: r.is_superuser, is_org_admin: r.is_org_admin, is_active: r.is_active });
          setRoleModalOpen(true);
        }}>{t('profile.manageRole')}</Button>
      ),
    },
  ];

  const orgTabs = profile?.organizations?.map((org) => ({
    key: org.org_id,
    label: org.org_name,
    children: (
      <Card size="small" title={t("profile.orgInfo")}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t("profile.orgName")}>{org.org_name}</Descriptions.Item>
          <Descriptions.Item label={t("profile.orgRole")}>{org.role_in_org}</Descriptions.Item>
          <Descriptions.Item label={t("profile.currentPlan")}>{org.plan_name}</Descriptions.Item>
          <Descriptions.Item label={t("profile.expireAt")}>{org.expire_at ? dayjs(org.expire_at).format("YYYY-MM-DD") : t("profile.permanent")}</Descriptions.Item>
        </Descriptions>
      </Card>
    ),
  })) || [];

  return (
    <div style={{ padding: "24px" }}>
      <Title level={2}>{t('profile.title')}</Title>

      <Tabs items={[
        {
          key: "profile",
          label: t('profile.info'),
          children: (
            <Card
              title={t('profile.basicInfo')}
              extra={
                <Button icon={editing ? <SaveOutlined /> : <EditOutlined />} onClick={() => editing ? handleSaveProfile() : setEditing(true)}>
                  {editing ? t('profile.save') : t('profile.edit')}
                </Button>
              }
            >
              <Form form={form} layout="vertical" disabled={!editing}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="full_name" label={t('profile.name')}>
                      <Input prefix={<UserOutlined />} placeholder={t('profile.namePlaceholder')} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="phone" label={t('profile.phone')}>
                      <Input prefix={<PhoneOutlined />} placeholder={t('profile.phonePlaceholder')} />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="department" label={t('profile.department')}>
                      <Input placeholder="\u8bf7\u8f93\u5165\u90e8\u95e8" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="position" label={t('profile.position')}>
                      <Input placeholder="\u8bf7\u8f93\u5165\u804c\u4f4d" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="email" label={t('profile.email')}>
                  <Input prefix={<MailOutlined />} disabled />
                  <Text type="secondary" style={{ fontSize: 12 }}>{t('profile.emailNote')}</Text>
                </Form.Item>
              </Form>
            </Card>
          ),
        },
        {
          key: "orgs",
          label: t('profile.orgs'),
          children: orgTabs.length > 0 ? <Tabs items={orgTabs} /> : <Alert message={t('profile.noOrg')} type="info" />,
        },
        {
          key: "orders",
          label: t('profile.orders'),
          children: (
            <div>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setRechargeOpen(true)}>{t('profile.recharge')}</Button>
                <Button icon={<ReloadOutlined />} onClick={loadOrders}>{t('profile.refresh')}</Button>
              </Space>
              <Table columns={orderColumns} dataSource={orders} rowKey="id" loading={loading} />
            </div>
          ),
        },
        {
          key: "refunds",
          label: t('profile.refunds'),
          children: (
            <div>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setRefundOpen(true)}>{t('profile.refundApply')}</Button>
                <Button icon={<ReloadOutlined />} onClick={loadRefunds}>{t('profile.refresh')}</Button>
              </Space>
              <Table columns={refundColumns} dataSource={refunds} rowKey="id" loading={loading} />
            </div>
          ),
        },
        ...(user?.is_superuser ? [{
          key: "admin",
          label: t('profile.admin'),
          children: (
            <div>
              <Space style={{ marginBottom: 16 }}>
                <Button icon={<ReloadOutlined />} onClick={loadAdminUsers}>{t('profile.refresh')}</Button>
              </Space>
              <Table columns={adminUserColumns} dataSource={adminUsers} rowKey="id" loading={loading} />
            </div>
          ),
        }] : []),
      ]} />

      {/* \u5145\u503c\u004d\u006f\u0064\u0061\u006c */}
      <Modal title={t('profile.rechargeTitle')} open={rechargeOpen} onOk={handleRecharge} onCancel={() => setRechargeOpen(false)} width={520}>
        <Form form={rechargeForm} layout="vertical">
          <Form.Item name="org_id" label={t('profile.selectOrg')} rules={[{ required: true }]}>
            <Select placeholder={t('profile.selectOrgPlaceholder')} options={orgs.map((o: any) => ({ label: o.name, value: o.id }))} />
          </Form.Item>
          <Form.Item name="plan_id" label={t('profile.selectPlan')} rules={[{ required: true }]}>
            <Select placeholder={t('profile.selectPlanPlaceholder')} options={plans.map((p: any) => ({
              label: p.name,
              value: p.id,
            }))} />
          </Form.Item>
          <Form.Item name="billing_cycle" label={t('profile.billingCycle')} rules={[{ required: true }]}>
            <Select options={[{ label: t('profile.monthly'), value: "monthly" }, { label: t('profile.yearly'), value: "yearly" }]} />
          </Form.Item>
          <Form.Item name="payment_method" label={t('profile.paymentMethod')} rules={[{ required: true }]}>
            <Select options={[
              { label: t('profile.bankTransfer'), value: "manual_bank" },
              { label: t('profile.alipay'), value: "alipay" },
              { label: t('profile.wechat'), value: "wechat" },
            ]} />
          </Form.Item>
          <Form.Item name="remark" label={t('profile.remark')}>
            <Input.TextArea rows={2} placeholder={t('profile.remarkPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* \u9000\u8d39\u004d\u006f\u0064\u0061\u006c */}
      <Modal title={t('profile.refundTitle')} open={refundOpen} onOk={handleRefund} onCancel={() => setRefundOpen(false)} width={520}>
        <Form form={refundForm} layout="vertical">
          <Form.Item name="order_id" label={t('profile.orderId')} rules={[{ required: true, message: t('profile.orderIdRequired') }]}>
            <Input placeholder={t('profile.orderIdPlaceholder')} />
          </Form.Item>
          <Form.Item name="amount" label={t('profile.refundAmount')} rules={[{ required: true }]}>
            <InputNumber prefix={<BankOutlined />} min={0} style={{ width: "100%" }} placeholder={t('profile.refundAmountPlaceholder')} />
          </Form.Item>
          <Form.Item name="reason" label={t('profile.refundReason')} rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder={t('profile.refundReasonPlaceholder')} />
          </Form.Item>
          <Form.Item name="method" label={t('profile.refundMethod')} rules={[{ required: true }]}>
            <Select options={[
              { label: t('profile.originalMethod'), value: "original_method" },
              { label: t('profile.bankTransfer'), value: "bank_transfer" },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* \u89d2\u8272\u7ba1\u7406\u004d\u006f\u0064\u0061\u006c */}
      <Modal
        title={t('profile.roleManagement')}
        open={roleModalOpen}
        onOk={() => roleTarget && handleUpdateUserRole(roleTarget.id, roleForm.getFieldsValue())}
        onCancel={() => setRoleModalOpen(false)}
        width={480}
      >
        {roleTarget && (
          <Alert
            style={{ marginBottom: 16 }}
            type="info"
            message={t('profile.selectOrgForRecharge')}
          />
        )}
        <Form form={roleForm} layout="vertical">
          <Form.Item name="is_superuser" valuePropName="checked">
            <Tag.CheckableTag checked={false} onChange={(c) => roleForm.setFieldValue("is_superuser", c)}>
              {t('profile.superAdmin')}
            </Tag.CheckableTag>
          </Form.Item>
          <Form.Item name="is_org_admin" valuePropName="checked">
            <Tag.CheckableTag checked={false} onChange={(c) => roleForm.setFieldValue("is_org_admin", c)}>
              {t('profile.orgAdmin')}
            </Tag.CheckableTag>
          </Form.Item>
          <Form.Item name="is_active" valuePropName="checked">
            <Tag.CheckableTag checked={roleTarget?.is_active ?? true} onChange={(c) => roleForm.setFieldValue("is_active", c)}>
              {t('profile.accountStatus')}
            </Tag.CheckableTag>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Profile;
