import React, { useEffect, useMemo, useState } from "react";
import {
  App, Card, Table, Button, Space, Tag, Typography, Alert, Input, Tooltip, Modal, Form, message as antdMessage,
} from "antd";
import {
  ReloadOutlined, SafetyCertificateOutlined, UserSwitchOutlined,
  TeamOutlined, CrownOutlined, DownCircleOutlined, SearchOutlined,
} from "@ant-design/icons";
import { listAdminUsers, setUserRole, type AdminUserItem } from "../../api/ucm";

const { Title, Text } = Typography;

const ROLE_META: Record<string, { label: string; color: string; icon: React.ReactNode; desc: string }> = {
  super_admin: {
    label: "系统管理",
    color: "magenta",
    icon: <CrownOutlined />,
    desc: "可操作系统全部功能（含整个运营管理板块）",
  },
  admin: {
    label: "用户管理",
    color: "blue",
    icon: <SafetyCertificateOutlined />,
    desc: "可管理用户、用户级别与功能开通，但不能操作系统级配置",
  },
  user: {
    label: "用户",
    color: "default",
    icon: <UserSwitchOutlined />,
    desc: "仅可使用除运营管理板块外的全部功能",
  },
};

const FeatureGrants: React.FC = () => {
  const { message } = App.useApp();
  const [list, setList] = useState<AdminUserItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | "super_admin" | "admin" | "user">("all");
  const [submitting, setSubmitting] = useState(false);
  const [roleRec, setRoleRec] = useState<AdminUserItem | null>(null);
  const [targetRole, setTargetRole] = useState<string>("");
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await listAdminUsers();
      setList(res?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载用户失败");
      setList([]);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  // 统计
  const stats = useMemo(() => {
    const total = list.length;
    const superCnt = list.filter((u) => u.role === "super_admin").length;
    const adminCnt = list.filter((u) => u.role === "admin").length;
    const userCnt = list.filter((u) => u.role === "user").length;
    return { total, superCnt, adminCnt, userCnt };
  }, [list]);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return list.filter((u) => {
      if (roleFilter !== "all" && u.role !== roleFilter) return false;
      if (!kw) return true;
      return (
        (u.username || "").toLowerCase().includes(kw) ||
        (u.full_name || "").toLowerCase().includes(kw) ||
        (u.email || "").toLowerCase().includes(kw)
      );
    });
  }, [list, keyword, roleFilter]);

  const openSetRole = (rec: AdminUserItem, target: string) => {
    setRoleRec(rec);
    setTargetRole(target);
    form.resetFields();
  };

  const submitSetRole = async () => {
    if (!roleRec || !targetRole) return;
    let values: any = {};
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
      const res = await setUserRole(roleRec.id, {
        role: targetRole,
        reason: values.reason,
      });
      antdMessage.success(
        `${res.username} 已从「${ROLE_META[res.prev_role]?.label || res.prev_role}」` +
        `切换为「${ROLE_META[res.new_role]?.label || res.new_role}」`
      );
      setRoleRec(null);
      await load();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || "切换失败");
    } finally {
      setSubmitting(false);
    }
  };

  const renderAction = (r: AdminUserItem) => {
    const buttons: React.ReactNode[] = [];
    if (r.role !== "super_admin") {
      buttons.push(
        <Tooltip key="to-super" title="开通系统管理：可操作系统全部功能">
          <Button
            size="small" type="primary" icon={<CrownOutlined />}
            onClick={() => openSetRole(r, "super_admin")}
          >开通系统管理</Button>
        </Tooltip>
      );
    }
    if (r.role !== "admin") {
      buttons.push(
        <Tooltip key="to-admin" title="开通用户管理：只能管理用户">
          <Button
            size="small" icon={<SafetyCertificateOutlined />}
            onClick={() => openSetRole(r, "admin")}
          >开通用户管理</Button>
        </Tooltip>
      );
    }
    if (r.role !== "user") {
      buttons.push(
        <Tooltip key="to-user" title="降为普通用户：仅可使用除运营管理板块外的功能">
          <Button
            size="small" danger icon={<DownCircleOutlined />}
            onClick={() => openSetRole(r, "user")}
          >降为普通用户</Button>
        </Tooltip>
      );
    }
    if (buttons.length === 0) {
      return <Text type="secondary">—</Text>;
    }
    return <Space size={4} wrap>{buttons}</Space>;
  };

  const columns = [
    {
      title: "用户",
      key: "user",
      render: (_: any, r: AdminUserItem) => (
        <Space size={6} direction="vertical" style={{ lineHeight: 1.3 }}>
          <Space size={6}>
            <Text strong>{r.full_name || r.username}</Text>
            {!r.is_active && <Tag color="red">已停用</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>@{r.username}{r.email ? ` · ${r.email}` : ""}</Text>
        </Space>
      ),
    },
    {
      title: "当前管理角色",
      key: "role",
      width: 220,
      render: (_: any, r: AdminUserItem) => {
        const meta = ROLE_META[r.role] || ROLE_META.user;
        return (
          <Space size={6} direction="vertical" style={{ lineHeight: 1.3 }}>
            <Tag color={meta.color} icon={meta.icon} style={{ fontSize: 13, padding: "2px 10px" }}>
              {meta.label}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>{meta.desc}</Text>
          </Space>
        );
      },
      filters: [
        { text: "系统管理", value: "super_admin" },
        { text: "用户管理", value: "admin" },
        { text: "普通用户", value: "user" },
      ],
      onFilter: (val: any, r: AdminUserItem) => r.role === val,
    },
    {
      title: "权限范围",
      key: "scope",
      width: 180,
      render: (_: any, r: AdminUserItem) => {
        if (r.role === "super_admin") return <Tag color="magenta">全系统</Tag>;
        if (r.role === "admin") return <Tag color="blue">用户/级别/权限开通</Tag>;
        return <Tag>业务功能</Tag>;
      },
    },
    {
      title: "最近登录",
      dataIndex: "last_login",
      width: 160,
      render: (v: any) => v ? <Text style={{ fontSize: 12 }}>{new Date(v).toLocaleString("zh-CN")}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: "操作",
      key: "action",
      width: 280,
      fixed: "right" as const,
      render: (_: any, r: AdminUserItem) => renderAction(r),
    },
  ];

  return (
    <div>
      <Title level={3}>功能开通</Title>
      <Alert
        type="info" showIcon
        style={{ marginBottom: 16 }}
        message="管理权限三档说明"
        description={
          <Space size={16} wrap style={{ marginTop: 4 }}>
            <span><Tag color="magenta" icon={<CrownOutlined />}>系统管理</Tag>可操作系统全部功能（含整个运营管理板块）</span>
            <span><Tag color="blue" icon={<SafetyCertificateOutlined />}>用户管理</Tag>仅可管理用户、用户级别与功能开通</span>
            <span><Tag icon={<UserSwitchOutlined />}>用户</Tag>仅可使用除「运营管理」板块外的功能</span>
          </Space>
        }
      />

      {/* 统计卡 */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        <Card size="small" hoverable>
          <Space direction="vertical" size={2}>
            <Text type="secondary" style={{ fontSize: 12 }}>用户总数</Text>
            <Text strong style={{ fontSize: 22 }}>{stats.total}</Text>
          </Space>
        </Card>
        <Card size="small" hoverable style={{ borderColor: "#F0A6CA" }}>
          <Space direction="vertical" size={2}>
            <Text type="secondary" style={{ fontSize: 12 }}><CrownOutlined /> 系统管理员</Text>
            <Text strong style={{ fontSize: 22, color: "#C026D3" }}>{stats.superCnt}</Text>
          </Space>
        </Card>
        <Card size="small" hoverable style={{ borderColor: "#93C5FD" }}>
          <Space direction="vertical" size={2}>
            <Text type="secondary" style={{ fontSize: 12 }}><SafetyCertificateOutlined /> 用户管理员</Text>
            <Text strong style={{ fontSize: 22, color: "#2563EB" }}>{stats.adminCnt}</Text>
          </Space>
        </Card>
        <Card size="small" hoverable>
          <Space direction="vertical" size={2}>
            <Text type="secondary" style={{ fontSize: 12 }}><TeamOutlined /> 普通用户</Text>
            <Text strong style={{ fontSize: 22 }}>{stats.userCnt}</Text>
          </Space>
        </Card>
      </div>

      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>管理权限开通</span>
          </Space>
        }
        extra={
          <Space>
            <Input
              allowClear prefix={<SearchOutlined />}
              placeholder="搜索用户名/姓名/邮箱"
              style={{ width: 240 }}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <Space.Compact>
              <Button size="small" type={roleFilter === "all" ? "primary" : "default"} onClick={() => setRoleFilter("all")}>全部</Button>
              <Button size="small" type={roleFilter === "super_admin" ? "primary" : "default"} onClick={() => setRoleFilter("super_admin")}>系统管理</Button>
              <Button size="small" type={roleFilter === "admin" ? "primary" : "default"} onClick={() => setRoleFilter("admin")}>用户管理</Button>
              <Button size="small" type={roleFilter === "user" ? "primary" : "default"} onClick={() => setRoleFilter("user")}>普通用户</Button>
            </Space.Compact>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          data-tour="admin-grants-list"
          size="middle"
          loading={loading}
          dataSource={filtered}
          columns={columns}
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 个用户` }}
        />
      </Card>

      <Modal
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>设置管理角色</span>
          </Space>
        }
        open={!!roleRec}
        onOk={submitSetRole}
        confirmLoading={submitting}
        onCancel={() => setRoleRec(null)}
        okText="确认切换"
        cancelText="取消"
      >
        {roleRec && (
          <>
            <Alert
              type="warning" showIcon style={{ marginBottom: 12 }}
              message={
                <span>
                  将 <Text strong>{roleRec.full_name || roleRec.username}</Text> 从
                  <Tag color={ROLE_META[_roleOf(roleRec)].color} style={{ margin: "0 4px" }}>
                    {ROLE_META[_roleOf(roleRec)].label}
                  </Tag>
                  切换为
                  <Tag color={ROLE_META[targetRole]?.color} style={{ margin: "0 4px" }}>
                    {ROLE_META[targetRole]?.label}
                  </Tag>
                </span>
              }
              description={ROLE_META[targetRole]?.desc}
            />
            <Form form={form} layout="vertical">
              <Form.Item name="reason" label="备注（可选）">
                <Input.TextArea rows={2} placeholder="例如：授予组织管理员权限 / 收回临时授权 / 等等" />
              </Form.Item>
            </Form>
          </>
        )}
      </Modal>
    </div>
  );
};

// helper: 取当前角色
function _roleOf(r: AdminUserItem): "super_admin" | "admin" | "user" {
  return r.role || "user";
}

export default FeatureGrants;
