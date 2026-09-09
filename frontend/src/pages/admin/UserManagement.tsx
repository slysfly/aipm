import React, { useEffect, useMemo, useState } from "react";
import {
  App, Card, Table, Button, Modal, Form, Select, Input, Space, Tag, Typography, Alert,
  Popconfirm, Tabs, Row, Col, Statistic, Empty, Divider, Switch,
} from "antd";
import { PlusOutlined, ReloadOutlined, CrownOutlined, ExclamationCircleOutlined, ThunderboltOutlined, SafetyCertificateOutlined, UserSwitchOutlined } from "@ant-design/icons";
import {
  listOrganizations, listMembers, addMember, updateMember, removeMember,
  listDepartments, listPlans, rechargeOrg, listUsersForPicker, UserPickerItem,
  setUserRole,
} from "../../api/ucm";
import { useAuth } from "../../store/AuthContext";

const { Title, Text } = Typography;
const ROLE_OPTIONS = [
  { label: "所有者", value: "owner" },
  { label: "管理员", value: "admin" },
  { label: "成员", value: "member" },
];
const BILLING_OPTIONS = [
  { label: "月付", value: "monthly" },
  { label: "年付", value: "yearly" },
];
const PAYMENT_OPTIONS = [
  { label: "现金", value: "manual_cash" },
  { label: "微信", value: "manual_wechat" },
  { label: "支付宝", value: "manual_alipay" },
  { label: "银行转账", value: "manual_bank" },
];

// 用户选择器（与 OrganizationManagement 复用同一接口）
const UserPicker: React.FC<{
  value?: string;
  onChange?: (v: string) => void;
  orgId?: string;
  placeholder?: string;
}> = ({ value, onChange, orgId, placeholder }) => {
  const [opts, setOpts] = useState<UserPickerItem[]>([]);
  const [scope, setScope] = useState<"org" | "all">(orgId ? "org" : "all");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res: any = await listUsersForPicker(q || undefined);
        setOpts(Array.isArray(res) ? res : (res?.items || res?.data || []));
      } catch { setOpts([]); }
    }, 200);
    return () => clearTimeout(t);
  }, [q, scope]);
  return (
    <Select
      showSearch
      value={value}
      onChange={onChange}
      placeholder={placeholder || "搜索用户名/姓名/邮箱"}
      filterOption={false}
      onSearch={setQ}
      options={opts.map((u) => ({
        label: `${u.full_name || u.username}${u.department ? ` · ${u.department}` : ""}（${u.email || u.username}）`,
        value: u.id,
      }))}
      notFoundContent={q ? "无匹配用户" : <span>输入关键字搜索</span>}
      dropdownRender={(menu) => (
        <div>
          {orgId && (
            <div style={{ padding: 6, display: "flex", alignItems: "center", gap: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>范围：</Text>
              <Switch size="small" checked={scope === "all"} onChange={(c) => setScope(c ? "all" : "org")}
                checkedChildren="全站" unCheckedChildren="本组织" />
              <span style={{ flex: 1 }} />
              <Text type="secondary" style={{ fontSize: 12 }}>{opts.length} 人可选</Text>
            </div>
          )}
          <Divider style={{ margin: "4px 0" }} />
          {menu}
        </div>
      )}
    />
  );
};

const UserManagement: React.FC = () => {
  const { message } = App.useApp();
  // 组织
  const [orgs, setOrgs] = useState<any[]>([]);
  const [orgId, setOrgId] = useState<string | undefined>(undefined);
  // 成员
  const [list, setList] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  // 部门/套餐
  const [depts, setDepts] = useState<any[]>([]);
  const [plans, setPlans] = useState<any[]>([]);
  // Tab
  const [tab, setTab] = useState<"all" | "default" | "paid">("all");

  // Modals
  const [addOpen, setAddOpen] = useState(false);
  const [roleOpen, setRoleOpen] = useState(false);
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [rechargeTarget, setRechargeTarget] = useState<any>(null);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  // 管理角色切换
  const [adminRoleRec, setAdminRoleRec] = useState<any>(null);
  const [adminTargetRole, setAdminTargetRole] = useState<string>("");
  const [adminForm] = Form.useForm();
  const [addForm] = Form.useForm();
  const [roleForm] = Form.useForm();
  const [rechargeForm] = Form.useForm();
  // 当前组织
  const currentOrg = useMemo(() => orgs.find((o) => o.id === orgId), [orgs, orgId]);
  const orgPlan = useMemo(() => plans.find((p) => p.id === currentOrg?.plan_id), [plans, currentOrg]);
  const orgIsDefault = !currentOrg?.plan_id;

  // ── 加载组织 ──
  const loadOrgs = async () => {
    try {
      const res: any = await listOrganizations();
      // 后端返回 {items:[...], total:N}
      const items = Array.isArray(res) ? res : (res?.items || res?.data || []);
      setOrgs(items);
    } catch { setOrgs([]); }
  };
  useEffect(() => { loadOrgs(); loadPlans(); }, []);

  const loadPlans = async () => {
    try {
      const res: any = await listPlans();
      const items = Array.isArray(res) ? res : (res?.items || res?.data || []);
      setPlans(items.filter((p: any) => p.is_active !== false));
    } catch { setPlans([]); }
  };

  // ── 加载成员 ──
  const load = async () => {
    if (!orgId) { setList([]); return; }
    setLoading(true);
    try {
      const res: any = await listMembers(orgId);
      setList(Array.isArray(res) ? res : (res?.items || res?.data || []));
    } catch { setList([]); }
    finally { setLoading(false); }
  };
  const loadDepts = async () => {
    if (!orgId) { setDepts([]); return; }
    try {
      const res: any = await listDepartments(orgId);
      setDepts(Array.isArray(res) ? res : (res?.items || res?.data || []));
    } catch { setDepts([]); }
  };
  useEffect(() => { load(); loadDepts(); }, [orgId]);

  // ── 添加成员（含可选套餐） ──
  const openAdd = () => {
    setEditing(null);
    addForm.resetFields();
    addForm.setFieldsValue({ role_in_org: "member", billing_cycle: "monthly" });
    setAddOpen(true);
  };
  const handleAdd = async () => {
    if (!orgId) return;
    const values = await addForm.validateFields();
    setSaving(true);
    try {
      const res: any = await addMember(orgId, values);
      if (values.plan_id && res?.order?.order_id) {
        message.success(`成员已添加，套餐订单 ${res.order.order_id.slice(0, 8)}… 已创建，到期 ${res.order.expire_at?.slice(0, 10) || "-"}`);
      } else {
        message.success("成员已添加（默认用户，需充值后才能使用完整功能）");
      }
      setAddOpen(false);
      await load(); await loadOrgs(); // 更新组织 used_seats
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "添加失败");
    } finally { setSaving(false); }
  };

  // ── 调整角色 ──
  const openRole = (r: any) => {
    setEditing(r);
    roleForm.resetFields();
    roleForm.setFieldsValue({ role_in_org: r.role_in_org || "member" });
    setRoleOpen(true);
  };
  const handleRole = async () => {
    if (!orgId || !editing) return;
    const values = await roleForm.validateFields();
    setSaving(true);
    try {
      await updateMember(orgId, editing.user_id || editing.id, values);
      message.success("角色已更新");
      setRoleOpen(false);
      await load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "更新失败"); }
    finally { setSaving(false); }
  };

  // ── 移除成员 ──
  const handleRemove = async (userId: string) => {
    if (!orgId) return;
    try {
      await removeMember(orgId, userId);
      message.success("成员已移除");
      await load(); await loadOrgs();
    } catch (e: any) { message.error(e?.response?.data?.detail || "移除失败"); }
  };

  // ── 充值 ──
  const openRecharge = () => {
    rechargeForm.resetFields();
    rechargeForm.setFieldsValue({ billing_cycle: "monthly", payment_method: "manual_cash" });
    setRechargeTarget(currentOrg);
    setRechargeOpen(true);
  };
  const handleRecharge = async () => {
    if (!orgId) return;
    const values = await rechargeForm.validateFields();
    setSaving(true);
    try {
      const res: any = await rechargeOrg(orgId, values);
      message.success(`充值成功，到期 ${res?.expire_at?.slice(0, 10) || "-"}，金额 ¥${res?.amount || 0}`);
      setRechargeOpen(false);
      await load(); await loadOrgs();
    } catch (e: any) { message.error(e?.response?.data?.detail || "充值失败"); }
    finally { setSaving(false); }
  };

  // 当前登录用户（仅系统管理员可切换管理权限角色）
  const { user } = useAuth();
  const canManageRole = !!user?.is_superuser;

  // ── 管理角色切换（三档） ──
  const _resolveAdminRole = (m: any): "super_admin" | "admin" | "user" => {
    if (m.is_superuser) return "super_admin";
    if (m.is_org_admin) return "admin";
    return "user";
  };
  const openAdminRole = (m: any, target: string) => {
    setAdminRoleRec(m);
    setAdminTargetRole(target);
    adminForm.resetFields();
  };
  const submitAdminRole = async () => {
    if (!adminRoleRec) return;
    let values: any = {};
    try { values = await adminForm.validateFields(); } catch { return; }
    setSaving(true);
    try {
      const res: any = await setUserRole(adminRoleRec.user_id || adminRoleRec.id, {
        role: adminTargetRole,
        reason: values.reason,
      });
      message.success(`已将 ${res.username} 切换为「${adminTargetRole === "super_admin" ? "系统管理" : adminTargetRole === "admin" ? "用户管理" : "用户"}」`);
      setAdminRoleRec(null);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "切换失败");
    } finally {
      setSaving(false);
    }
  };

  // ── 表格 ──
  const filteredList = useMemo(() => {
    if (tab === "default") return list.filter((m) => m.is_default_user);
    if (tab === "paid") return list.filter((m) => !m.is_default_user);
    return list;
  }, [list, tab]);

  const columns = [
    { title: "用户名", dataIndex: "username", render: (v: any, r: any) => (
      <Space size={4}><strong>{v}</strong>{r.is_default_user && <Tag color="warning">默认用户</Tag>}</Space>
    ) },
    { title: "姓名", dataIndex: "full_name", render: (v: any) => v || "-" },
    { title: "邮箱", dataIndex: "email", render: (v: any) => v || "-" },
    { title: "部门", dataIndex: "department_id", render: (v: any) => depts.find((d) => d.id === v)?.name || "-" },
    { title: "组织内角色", dataIndex: "role_in_org", render: (v: any) => <Tag>{v || "-"}</Tag> },
    {
      title: "管理角色",
      key: "admin_role",
      width: 200,
      render: (_: any, r: any) => {
        const role = _resolveAdminRole(r);
        if (role === "super_admin") return <Tag color="magenta" icon={<CrownOutlined />}>系统管理</Tag>;
        if (role === "admin") return <Tag color="blue" icon={<SafetyCertificateOutlined />}>用户管理</Tag>;
        return <Tag icon={<UserSwitchOutlined />}>用户</Tag>;
      },
    },
    { title: "等级", dataIndex: "level_code", render: (v: any) => (v ? <Tag color="blue">{v}</Tag> : "-") },
    { title: "套餐", key: "plan", render: (_: any, r: any) => {
      if (!currentOrg?.plan_id) return <Tag color="default">未开通</Tag>;
      return (
        <Space size={4}>
          <Tag color="gold" icon={<CrownOutlined />}>{r.plan_name || "已开通"}</Tag>
          {r.expire_at && <Text type="secondary" style={{ fontSize: 12 }}>到期 {r.expire_at.slice(0, 10)}</Text>}
        </Space>
      );
    } },
    { title: "操作", key: "action", width: 260, render: (_: any, r: any) => (
      <Space size={4} wrap>
        <Button size="small" onClick={() => openRole(r)}>调整角色</Button>
        {canManageRole && (<>
          {(() => {
            const role = _resolveAdminRole(r);
            if (role !== "super_admin") {
              return <Button size="small" type="primary" icon={<CrownOutlined />} onClick={() => openAdminRole(r, "super_admin")}>系统管理</Button>;
            }
            return null;
          })()}
          {(() => {
            const role = _resolveAdminRole(r);
            if (role !== "admin") {
              return <Button size="small" icon={<SafetyCertificateOutlined />} onClick={() => openAdminRole(r, "admin")}>用户管理</Button>;
            }
            return null;
          })()}
          {(() => {
            const role = _resolveAdminRole(r);
            if (role !== "user") {
              return <Button size="small" danger icon={<UserSwitchOutlined />} onClick={() => openAdminRole(r, "user")}>降为用户</Button>;
            }
            return null;
          })()}
        </>)}
        <Popconfirm title="确认移除该成员？" onConfirm={() => handleRemove(r.user_id || r.id)}>
          <Button size="small" danger>移除</Button>
        </Popconfirm>
      </Space>
    ) },
  ];

  return (
    <div>
      <Title level={3}>用户管理</Title>

      <Card title="组织成员">
        <Space style={{ marginBottom: 12 }} wrap>
          <Text>选择组织：</Text>
          <Select
            style={{ width: 320 }}
            data-tour="admin-users-sel"
            placeholder="选择组织（先建组织 → 建套餐 → 再建用户）"
            value={orgId}
            onChange={(v) => { setOrgId(v); setTab("all"); }}
            options={orgs.map((o) => ({
              label: `${o.name}（${o.code}）${o.plan_id ? "" : " · 未开通套餐"}`,
              value: o.id,
            }))}
            notFoundContent={<span>暂无组织，请先到「组织管理」创建</span>}
          />
          <Button icon={<ReloadOutlined />} onClick={() => { loadOrgs(); load(); }}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} disabled={!orgId} onClick={openAdd}>
            添加成员
          </Button>
        </Space>

        {!orgId && (
          <Alert
            type="info" showIcon
            message="请先选择组织"
            description={
              <div>
                <div>完整流程：<b>先建立组织 → 再建立套餐 → 然后建用户</b>。</div>
                <div>添加成员时如未选择套餐，该成员将视为<b>默认用户</b>，需要充值后才能正常使用系统。</div>
                <div style={{ marginTop: 8 }}>
                  套餐入口：<a href="/admin/plans">套餐管理</a>　|　
                  组织入口：<a href="/admin/organizations">组织管理</a>
                </div>
              </div>
            }
          />
        )}

        {orgId && orgIsDefault && (
          <Alert
            type="warning" showIcon
            icon={<ExclamationCircleOutlined />}
            message={`组织「${currentOrg?.name}」尚未开通套餐，全部成员均为默认用户`}
            description={
              <Space>
                <span>请前往「套餐管理」创建套餐，或直接</span>
                <Button size="small" type="primary" icon={<ThunderboltOutlined />} onClick={openRecharge}>
                  立即为该组织充值
                </Button>
              </Space>
            }
            style={{ marginBottom: 12 }}
          />
        )}

        {orgId && !orgIsDefault && (
          <Alert
            type="success" showIcon
            message={
              <span>
                当前套餐：<b>{orgPlan?.name}</b>（{orgPlan?.code}）　
                到期：<b>{currentOrg?.expire_at?.slice(0, 10) || "永久"}</b>　
                席位：{currentOrg?.used_seats || 0} / {currentOrg?.max_seats || 0}
              </span>
            }
            action={
              <Button size="small" icon={<ThunderboltOutlined />} onClick={openRecharge}>续费/升级</Button>
            }
            style={{ marginBottom: 12 }}
          />
        )}

        {orgId && (
          <Row gutter={12} style={{ marginBottom: 12 }}>
            <Col span={8}><Card size="small"><Statistic title="成员总数" value={list.length} /></Card></Col>
            <Col span={8}><Card size="small"><Statistic title="默认用户" value={list.filter((m) => m.is_default_user).length} valueStyle={{ color: "#faad14" }} /></Card></Col>
            <Col span={8}><Card size="small"><Statistic title="付费成员" value={list.filter((m) => !m.is_default_user).length} valueStyle={{ color: "#52c41a" }} /></Card></Col>
          </Row>
        )}

        {orgId && (
          <Tabs activeKey={tab} onChange={(k: any) => setTab(k)} items={[
            { key: "all", label: `全部 (${list.length})` },
            { key: "default", label: `默认用户 (${list.filter((m) => m.is_default_user).length})` },
            { key: "paid", label: `付费成员 (${list.filter((m) => !m.is_default_user).length})` },
          ]} />
        )}

        <Table
          rowKey={(r: any) => r.user_id || r.id}
          data-tour="admin-users-list"
          size="small" loading={loading}
          dataSource={filteredList} columns={columns}
          locale={{ emptyText: orgId ? "该组织暂无成员" : <Empty description="请先选择组织" /> }}
          style={{ marginTop: 12 }}
        />
      </Card>

      {/* ── 添加成员 Modal ── */}
      <Modal
        title="添加成员"
        open={addOpen} onOk={handleAdd} confirmLoading={saving}
        onCancel={() => setAddOpen(false)} destroyOnClose width={560}
        okText="确认添加"
      >
        <Form form={addForm} layout="vertical">
          <Form.Item name="user_id" label="选择用户" rules={[{ required: true, message: "请选择用户" }]}>
            <UserPicker orgId={orgId} placeholder="搜索用户名/姓名/邮箱" />
          </Form.Item>
          <Form.Item name="department_id" label="部门（可选）">
            <Select allowClear placeholder="选择部门" options={depts.map((d) => ({ label: d.name, value: d.id }))} />
          </Form.Item>
          <Form.Item name="role_in_org" label="组织内角色" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>

          <Divider style={{ margin: "12px 0" }}>套餐选择（可选）</Divider>

          <Form.Item
            name="plan_id"
            label="开通套餐"
            extra={
              <span style={{ fontSize: 12, color: "#999" }}>
                不选套餐 = 该成员为<b style={{ color: "#faad14" }}>默认用户</b>，需充值后才能正常使用系统
              </span>
            }
          >
            <Select
              allowClear placeholder="暂不开通（视为默认用户）"
              options={plans.map((p) => ({
                label: `${p.name}（${p.code}）月 ¥${p.price_monthly || 0} / 年 ¥${p.price_yearly || 0}`,
                value: p.id,
              }))}
            />
          </Form.Item>
          <Form.Item shouldUpdate={(p, c) => p.plan_id !== c.plan_id} noStyle>
            {({ getFieldValue }) => getFieldValue("plan_id") ? (
              <Form.Item name="billing_cycle" label="账期">
                <Select options={BILLING_OPTIONS} />
              </Form.Item>
            ) : null}
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 调整角色 Modal ── */}
      <Modal title="调整成员角色" open={roleOpen} onOk={handleRole} confirmLoading={saving} onCancel={() => setRoleOpen(false)} destroyOnClose>
        <Form form={roleForm} layout="vertical">
          <Form.Item name="role_in_org" label="组织内角色" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 充值 Modal ── */}
      <Modal
        title={rechargeTarget ? `为「${rechargeTarget.name}」充值` : "充值"}
        open={rechargeOpen} onOk={handleRecharge} confirmLoading={saving}
        onCancel={() => setRechargeOpen(false)} destroyOnClose width={520}
        okText="确认充值"
      >
        <Form form={rechargeForm} layout="vertical">
          <Form.Item name="plan_id" label="选择套餐" rules={[{ required: true }]}>
            <Select placeholder="选择套餐" options={plans.map((p) => ({
              label: `${p.name}（${p.code}）月 ¥${p.price_monthly || 0} / 年 ¥${p.price_yearly || 0} · ${p.max_seats} 席位`,
              value: p.id,
            }))} />
          </Form.Item>
          <Form.Item name="billing_cycle" label="账期" rules={[{ required: true }]}>
            <Select options={BILLING_OPTIONS} />
          </Form.Item>
          <Form.Item name="payment_method" label="支付方式" rules={[{ required: true }]}>
            <Select options={PAYMENT_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注（可选）">
            <Input.TextArea rows={2} placeholder="如：合同编号、转账流水号" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── 管理角色切换 Modal ── */}
      <Modal
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>切换管理角色</span>
          </Space>
        }
        open={!!adminRoleRec}
        onOk={submitAdminRole}
        confirmLoading={saving}
        onCancel={() => setAdminRoleRec(null)}
        destroyOnClose
        okText="确认切换"
        cancelText="取消"
      >
        {adminRoleRec && (
          <Alert
            type="warning" showIcon style={{ marginBottom: 12 }}
            message={
              <span>
                将 <Text strong>{adminRoleRec.username}</Text> 切换为
                {adminTargetRole === "super_admin" && <Tag color="magenta" icon={<CrownOutlined />} style={{ marginLeft: 4 }}>系统管理</Tag>}
                {adminTargetRole === "admin" && <Tag color="blue" icon={<SafetyCertificateOutlined />} style={{ marginLeft: 4 }}>用户管理</Tag>}
                {adminTargetRole === "user" && <Tag icon={<UserSwitchOutlined />} style={{ marginLeft: 4 }}>用户</Tag>}
              </span>
            }
            description={
              adminTargetRole === "super_admin" ? "可操作系统全部功能（含整个运营管理板块）" :
              adminTargetRole === "admin" ? "仅可管理用户、用户级别与功能开通" :
              "仅可使用除「运营管理」板块外的功能"
            }
          />
        )}
        <Form form={adminForm} layout="vertical">
          <Form.Item name="reason" label="备注（可选）">
            <Input.TextArea rows={2} placeholder="如：授予组织管理员权限 / 收回临时授权" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default UserManagement;