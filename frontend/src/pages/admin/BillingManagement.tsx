import React, { useEffect, useState } from "react";
import {
  App, Card, Table, Button, Modal, Form, Select, Input, InputNumber, Tabs, Space, Tag, Typography, Popconfirm,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  listOrganizations, listOrders, createOrder, payOrder,
  listRefunds, createRefund, approveRefund, rejectRefund, listTransactions,
} from "../../api/ucm";

const { Title, Text } = Typography;

const ORDER_TYPE_OPTIONS = [
  { label: "新购订阅", value: "subscription" },
  { label: "续费", value: "renewal" },
  { label: "增购", value: "addon" },
  { label: "充值", value: "topup" },
];
const PAYMENT_OPTIONS = [
  { label: "支付宝", value: "alipay" },
  { label: "微信支付", value: "wechat" },
  { label: "银行转账", value: "bank_transfer" },
  { label: "银行卡", value: "card" },
];
const ORDER_STATUS_COLOR: Record<string, string> = {
  unpaid: "orange", paid: "green", refunded: "blue", cancelled: "red",
};
const REFUND_STATUS_COLOR: Record<string, string> = {
  pending: "orange", approved: "green", rejected: "red",
};

const BillingManagement: React.FC = () => {
  const { message } = App.useApp();
  const [orgs, setOrgs] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [refunds, setRefunds] = useState<any[]>([]);
  const [txns, setTxns] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const [orderOpen, setOrderOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payRec, setPayRec] = useState<any>(null);
  const [refundOpen, setRefundOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [payForm] = Form.useForm();
  const [refundForm] = Form.useForm();

  useEffect(() => {
    listOrganizations().then((res) => setOrgs(Array.isArray(res) ? res : (res?.data || []))).catch(() => setOrgs([]));
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [o, r, t] = await Promise.all([listOrders(), listRefunds(), listTransactions()]);
      setOrders(Array.isArray(o) ? o : (o?.data || []));
      setRefunds(Array.isArray(r) ? r : (r?.data || []));
      setTxns(Array.isArray(t) ? t : (t?.data || []));
    } catch {
      setOrders([]);
      setRefunds([]);
      setTxns([]);
    } finally {
      setLoading(false);
    }
  };

  const openOrder = () => {
    form.resetFields();
    setOrderOpen(true);
  };
  const handleCreateOrder = async () => {
    const values = await form.validateFields();
    const body: any = { ...values };
    if (values.items) {
      try {
        body.items = JSON.parse(values.items);
      } catch {
        message.error("items 不是合法 JSON");
        return;
      }
    } else {
      delete body.items;
    }
    setSaving(true);
    try {
      await createOrder(body);
      message.success("订单已创建");
      setOrderOpen(false);
      await loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const openPay = (r: any) => {
    setPayRec(r);
    payForm.resetFields();
    setPayOpen(true);
  };
  const handlePay = async () => {
    if (!payRec) return;
    const values = await payForm.validateFields();
    setSaving(true);
    try {
      await payOrder(payRec.id, values);
      message.success("订单已标记付款");
      setPayOpen(false);
      await loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    } finally {
      setSaving(false);
    }
  };

  const openRefund = () => {
    refundForm.resetFields();
    setRefundOpen(true);
  };
  const handleCreateRefund = async () => {
    const values = await refundForm.validateFields();
    setSaving(true);
    try {
      await createRefund(values);
      message.success("退款申请已提交");
      setRefundOpen(false);
      await loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "申请失败");
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveRefund(id);
      message.success("已通过");
      await loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };
  const handleReject = async (id: string) => {
    try {
      await rejectRefund(id);
      message.success("已驳回");
      await loadAll();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "操作失败");
    }
  };

  const orderColumns = [
    { title: "组织 ID", dataIndex: "org_id", render: (v: any) => v || "-" },
    {
      title: "类型",
      dataIndex: "type",
      render: (v: any) => <Tag>{ORDER_TYPE_OPTIONS.find((x) => x.value === v)?.label || v || "-"}</Tag>,
    },
    { title: "金额", dataIndex: "amount", render: (v: any) => (v != null ? `¥${v}` : "-") },
    { title: "状态", dataIndex: "status", render: (v: any) => <Tag color={ORDER_STATUS_COLOR[v] || "default"}>{v || "-"}</Tag> },
    { title: "支付方式", dataIndex: "payment_method", render: (v: any) => v || "-" },
    { title: "付款时间", dataIndex: "paid_at", render: (v: any) => (v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-") },
    { title: "发票号", dataIndex: "invoice_no", render: (v: any) => v || "-" },
    {
      title: "操作", key: "action",
      render: (_: any, r: any) =>
        r.status === "unpaid" ? (
          <Button size="small" type="primary" onClick={() => openPay(r)}>标记付款</Button>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  const refundColumns = [
    { title: "订单 ID", dataIndex: "order_id", render: (v: any) => v || "-" },
    { title: "金额", dataIndex: "amount", render: (v: any) => (v != null ? `¥${v}` : "-") },
    { title: "原因", dataIndex: "reason", render: (v: any) => v || "-" },
    { title: "状态", dataIndex: "status", render: (v: any) => <Tag color={REFUND_STATUS_COLOR[v] || "default"}>{v || "-"}</Tag> },
    {
      title: "操作", key: "action",
      render: (_: any, r: any) =>
        r.status === "pending" ? (
          <Space>
            <Popconfirm title="确认通过该退款？" onConfirm={() => handleApprove(r.id)}>
              <Button size="small" type="primary">通过</Button>
            </Popconfirm>
            <Popconfirm title="确认驳回该退款？" onConfirm={() => handleReject(r.id)}>
              <Button size="small" danger>驳回</Button>
            </Popconfirm>
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  const txnColumns = [
    { title: "类型", dataIndex: "type", render: (v: any) => <Tag>{v || "-"}</Tag> },
    { title: "金额", dataIndex: "amount", render: (v: any) => (v != null ? `¥${v}` : "-") },
    { title: "变动后余额", dataIndex: "balance_after", render: (v: any) => (v != null ? `¥${v}` : "-") },
    { title: "时间", dataIndex: "created_at", render: (v: any) => (v ? dayjs(v).format("YYYY-MM-DD HH:mm") : "-") },
  ];

  return (
    <div>
      <Title level={3}>收费退费</Title>
      <Card title="收费退费管理" extra={<Space><Button icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button></Space>}>
        <Tabs
          data-tour="admin-billing-tabs"
          items={[
            {
              key: "orders",
              label: "订单",
              children: (
                <>
                  <div style={{ marginBottom: 12, display: "flex", justifyContent: "flex-end" }}>
                    <Button type="primary" icon={<PlusOutlined />} onClick={openOrder}>新建订单</Button>
                  </div>
                  <Table rowKey="id" size="small" loading={loading} dataSource={orders} columns={orderColumns} data-tour="admin-billing-list" />
                </>
              ),
            },
            {
              key: "refunds",
              label: "退款",
              children: (
                <>
                  <Space style={{ marginBottom: 12 }}>
                    <Button type="primary" icon={<PlusOutlined />} onClick={openRefund}>申请退款</Button>
                  </Space>
                  <Table rowKey="id" size="small" loading={loading} dataSource={refunds} columns={refundColumns} />
                </>
              ),
            },
            {
              key: "txns",
              label: "资金流水",
              children: <Table rowKey="id" size="small" loading={loading} dataSource={txns} columns={txnColumns} />,
            },
          ]}
        />
      </Card>

      <Modal title="新建订单" open={orderOpen} onOk={handleCreateOrder} confirmLoading={saving} onCancel={() => setOrderOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical">
          <Form.Item name="org_id" label="组织 ID" rules={[{ required: true }]}>
            <Select placeholder="选择组织" options={orgs.map((o) => ({ label: o.name, value: o.id }))} />
          </Form.Item>
          <Form.Item name="amount" label="金额" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="type" label="订单类型" rules={[{ required: true }]}>
            <Select options={ORDER_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="plan_id" label="套餐 ID（可选）">
            <Input placeholder="关联套餐 ID" />
          </Form.Item>
          <Form.Item name="payment_method" label="支付方式">
            <Select allowClear options={PAYMENT_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="items" label="明细 items（可选，JSON 数组）">
            <Input.TextArea rows={3} placeholder='[{"name":"套餐","qty":1,"price":199}]' />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="标记付款" open={payOpen} onOk={handlePay} confirmLoading={saving} onCancel={() => setPayOpen(false)} destroyOnClose>
        <Form form={payForm} layout="vertical">
          <Form.Item name="payment_method" label="支付方式">
            <Select allowClear options={PAYMENT_OPTIONS} />
          </Form.Item>
          <Form.Item name="invoice_no" label="发票号（可选）">
            <Input placeholder="如 INV-2025-001" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="申请退款" open={refundOpen} onOk={handleCreateRefund} confirmLoading={saving} onCancel={() => setRefundOpen(false)} destroyOnClose>
        <Form form={refundForm} layout="vertical">
          <Form.Item name="order_id" label="订单 ID" rules={[{ required: true }]}>
            <Input placeholder="关联订单 ID" />
          </Form.Item>
          <Form.Item name="amount" label="退款金额" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="reason" label="退款原因" rules={[{ required: true }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="method" label="退款方式">
            <Select allowClear options={PAYMENT_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default BillingManagement;
