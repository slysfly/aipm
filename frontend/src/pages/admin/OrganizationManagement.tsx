import React, { useEffect, useMemo, useState } from "react";
import {
  App, Card, Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag,
  Tabs, Popconfirm, Typography, Alert, Switch, Divider, message as antdMessage,
} from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, UserAddOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  getOrgTree, createOrganization, updateOrganization, deleteOrganization,
  listDepartments, createDepartment, deleteDepartment,
  listMembers, addMember, updateMember, removeMember,
  listUsersForPicker, listPlans,
} from "../../api/ucm";

const { Text, Title } = Typography;

const STATUS_OPTIONS = [
  { label: "启用", value: "active" },
  { label: "停用", value: "inactive" },
  { label: "冻结", value: "suspended" },
];
const STATUS_COLOR: Record<string, string> = {
  active: "green", inactive: "default", suspended: "red",
};

const ROLE_OPTIONS = [
  { label: "所有者", value: "owner" },
  { label: "管理员", value: "admin" },
  { label: "成员", value: "member" },
];

const flatten = (nodes: any[], acc: any[] = []): any[] => {
  nodes.forEach((n) => {
    acc.push(n);
    if (n.children && n.children.length) flatten(n.children, acc);
  });
  return acc;
};

/* ───────────────────────────────────────────────────────────────
 * 共享：用户下拉（搜索式 + 全站 / 同组织）
 *  - 优先显示当前组织成员（更相关）
 *  - 顶部"全站搜索"按钮可拉全站用户
 * ─────────────────────────────────────────────────────────────── */
const UserPicker: React.FC<{
  value?: string;
  onChange?: (v: string | undefined) => void;
  disabled?: boolean;
  orgMembers?: any[];                // 当前组织成员（更相关的候选）
  placeholder?: string;
}> = ({ value, onChange, disabled, orgMembers = [], placeholder = "选择用户" }) => {
  const [users, setUsers] = useState<any[]>(orgMembers);
  const [searching, setSearching] = useState(false);
  const [scope, setScope] = useState<"org" | "all">("org");

  useEffect(() => {
    if (scope === "org") {
      setUsers(orgMembers);
    }
  }, [scope, orgMembers]);

  const onSearch = async (q: string) => {
    if (!q || !q.trim()) {
      setUsers(scope === "org" ? orgMembers : []);
      return;
    }
    setSearching(true);
    try {
      const res = await listUsersForPicker(q);
      setUsers(Array.isArray(res) ? res : []);
    } catch {
      /* 网络错误静默，保持上一次结果 */
    } finally {
      setSearching(false);
    }
  };

  const options = useMemo(
    () =>
      users.map((u) => ({
        label: u.full_name
          ? `${u.full_name}（${u.username}）${u.email ? " · " + u.email : ""}`
          : `${u.username}${u.email ? " · " + u.email : ""}`,
        value: u.id,
        username: u.username,
        full_name: u.full_name,
        email: u.email,
      })),
    [users]
  );

  return (
    <Select
      showSearch
      allowClear
      value={value}
      onChange={onChange}
      onSearch={onSearch}
      disabled={disabled}
      placeholder={placeholder}
      loading={searching}
      filterOption={false}
      options={options}
      notFoundContent={searching ? "搜索中…" : "无匹配用户"}
      optionLabelProp="label"
      dropdownRender={(menu) => (
        <div>
          <div style={{ padding: 4, borderBottom: "1px solid #f0f0f0" }}>
            <Space size="small">
              <Text type="secondary" style={{ fontSize: 12 }}>候选范围：</Text>
              <Switch
                size="small"
                checked={scope === "all"}
                onChange={(v) => {
                  setScope(v ? "all" : "org");
                  if (v) onSearch("");
                }}
                checkedChildren="全站用户"
                unCheckedChildren="本组织成员"
              />
            </Space>
          </div>
          {menu}
        </div>
      )}
    />
  );
};

/* ───────────────────────────────────────────────────────────────
 * 组织 Modal：含「下级组织继承上级成员」开关
 * ─────────────────────────────────────────────────────────────── */
const OrganizationManagement: React.FC = () => {
  const { message } = App.useApp();
  const [tree, setTree] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [editRecord, setEditRecord] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [plans, setPlans] = useState<any[]>([]);
  const [form] = Form.useForm();
  // 「继承上级组织成员」开关
  const [inheritMembers, setInheritMembers] = useState(true);
  // 当前选中父组织对象
  const parentId = Form.useWatch("parent_id", form);
  const parentOrg = useMemo(() => {
    if (!parentId) return null;
    return flatten(tree).find((o) => o.id === parentId) || null;
  }, [parentId, tree]);

  const loadTree = async () => {
    setLoading(true);
    try {
      const res = await getOrgTree();
      setTree(Array.isArray(res) ? res : (res?.data || []));
    } catch {
      setTree([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadTree(); }, []);

  // 拉套餐列表（供「套餐 ID」下拉使用）
  const loadPlans = async () => {
    try {
      const res: any = await listPlans();
      const arr = Array.isArray(res) ? res : (res?.items || []);
      setPlans(arr);
    } catch {
      setPlans([]);
    }
  };
  useEffect(() => { loadPlans(); }, []);

  const openCreate = () => {
    setEditRecord(null);
    form.resetFields();
    form.setFieldsValue({ status: "active" });
    setInheritMembers(true);
    setCreateOpen(true);
    loadPlans();
  };
  const openEdit = (record: any) => {
    setEditRecord(record);
    form.resetFields();
    form.setFieldsValue({
      code: record.code,
      name: record.name,
      parent_id: record.parent_id || undefined,
      owner_user_id: record.owner_user_id,
      plan_id: record.plan_id || undefined,
      status: record.status || "active",
      max_seats: record.max_seats,
    });
    setInheritMembers(false);
    setCreateOpen(true);
    loadPlans();
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      let created: any = null;
      if (editRecord) {
        created = await updateOrganization(editRecord.id, values);
        message.success("组织已更新");
      } else {
        created = await createOrganization(values);
        message.success("组织已创建");
      }

      // 新建 + 选了上级 + 勾选继承 → 把上级组织当前成员批量加进来
      if (!editRecord && values.parent_id && inheritMembers) {
        const parentId = values.parent_id;
        try {
          const existing = await listMembers(created.id);
          const existingIds = new Set((existing as any[]).map((m) => m.user_id));
          const parentMembers = (await listMembers(parentId)) as any[];
          let okCount = 0;
          let skipCount = 0;
          for (const m of parentMembers) {
            if (existingIds.has(m.user_id)) { skipCount++; continue; }
            try {
              await addMember(created.id, {
                user_id: m.user_id,
                department_id: null,
                role_in_org: m.role_in_org || "member",
              });
              okCount++;
            } catch {
              /* 单个失败跳过（席位满/重复） */
            }
          }
          if (okCount > 0) {
            message.success(`已从「${parentOrg?.name || "上级组织"}」继承 ${okCount} 名成员${skipCount ? `（跳过 ${skipCount}）` : ""}`);
          } else if (skipCount > 0) {
            antdMessage.info("上级组织成员已全部在当前组织中，无需重复继承");
          }
        } catch (e) {
          antdMessage.warning("继承上级成员失败，可稍后手动添加");
        }
      }

      setCreateOpen(false);
      await loadTree();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteOrganization(id);
      message.success("组织已删除");
      if (selectedId === id) setSelectedId(null);
      await loadTree();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "删除失败");
    }
  };

  const parentOptions = flatten(tree)
    .filter((o) => !editRecord || o.id !== editRecord.id)
    .map((o) => ({ label: o.name, value: o.id }));

  const columns = [
    {
      title: "组织名称", dataIndex: "name",
      render: (v: any, r: any) => (
        <Space size={6} wrap>
          <Text strong>{v}</Text>
          <Tag color="blue">{r.code}</Tag>
          {r.parent_id ? null : <Tag color="purple">顶级</Tag>}
        </Space>
      ),
    },
    { title: "状态", dataIndex: "status", render: (s: any) => <Tag color={STATUS_COLOR[s] || "default"}>{s || "-"}</Tag> },
    { title: "席位上限", dataIndex: "max_seats", render: (v: any) => v ?? "-" },
    {
      title: "成员数", dataIndex: "used_seats",
      render: (v: any, r: any) => {
        const used = v ?? 0;
        const max = r.max_seats ?? 0;
        const ratio = max > 0 ? used / max : 0;
        const color = ratio >= 1 ? "red" : ratio >= 0.8 ? "orange" : "green";
        return (
          <Space size={4}>
            <Tag color={color} style={{ marginInlineEnd: 0 }}>{used}</Tag>
            <Text type="secondary">/ {max}</Text>
          </Space>
        );
      },
    },
    {
      title: "套餐", dataIndex: "plan_name",
      render: (v: any) =>
        v ? (
          <Tag color="gold">{v}</Tag>
        ) : (
          <Tag color="default">未开通</Tag>
        ),
    },
    {
      title: "到期时间", dataIndex: "expire_at",
      render: (v: any) =>
        v ? (
          <Space size={4}>
            <Text>{dayjs(v).format("YYYY-MM-DD")}</Text>
            {dayjs(v).isBefore(dayjs()) && <Tag color="red">已过期</Tag>}
          </Space>
        ) : (
          <Text type="secondary">-</Text>
        ),
    },
    {
      title: "操作", key: "action",
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); openEdit(r); }}>编辑</Button>
          <Popconfirm title="确认删除该组织？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const selectedOrg = flatten(tree).find((o) => o.id === selectedId) || null;

  return (
    <div>
      <Title level={3}>组织管理</Title>
      <Card
        title="组织树"
        data-tour="admin-org-tree"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadTree}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} data-tour="admin-org-new">新建组织</Button>
          </Space>
        }
      >
        <Alert type="info" showIcon style={{ marginBottom: 12 }} message="点击任意组织行，可在下方查看并管理其「部门」与「成员」。" />
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={tree}
          columns={columns}
          pagination={false}
          onRow={(record) => ({
            onClick: () => setSelectedId(record.id),
            style: { cursor: "pointer", background: record.id === selectedId ? "#f0f7ff" : undefined },
          })}
        />
      </Card>

      {selectedOrg && (
        <Card
          title={`「${selectedOrg.name}」的部门与成员`}
          style={{ marginTop: 16 }}
          extra={
            <Button icon={<ReloadOutlined />} size="small" onClick={() => {
              // 触发子组件刷新：派发一个全局事件
              window.dispatchEvent(new CustomEvent("aipm:org-refresh", { detail: { orgId: selectedOrg.id } }));
            }}>刷新</Button>
          }
        >
          <Tabs
            defaultActiveKey="member"
            items={[
              {
                key: "dept", label: "部门",
                children: (
                  <DeptTab
                    orgId={selectedOrg.id}
                    headerExtra={
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => {
                        // 触发 DeptTab 内的 form/modal 打开（用自定义事件解耦）
                        window.dispatchEvent(new CustomEvent("aipm:dept-add", { detail: { orgId: selectedOrg.id } }));
                      }}>新建部门</Button>
                    }
                  />
                ),
              },
              {
                key: "member", label: "成员",
                children: (
                  <MemberTab
                    orgId={selectedOrg.id}
                    headerExtra={
                      <Button type="primary" icon={<UserAddOutlined />} onClick={() => {
                        window.dispatchEvent(new CustomEvent("aipm:member-add", { detail: { orgId: selectedOrg.id } }));
                      }}>添加成员</Button>
                    }
                  />
                ),
              },
            ]}
          />
        </Card>
      )}

      <Modal
        title={editRecord ? "编辑组织" : "新建组织"}
        open={createOpen}
        onOk={handleSubmit}
        confirmLoading={saving}
        onCancel={() => setCreateOpen(false)}
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="组织编码" rules={[{ required: true }]}>
            <Input placeholder="如 org-001" />
          </Form.Item>
          <Form.Item name="name" label="组织名称" rules={[{ required: true }]}>
            <Input placeholder="如 某某科技有限公司" />
          </Form.Item>
          <Form.Item name="parent_id" label="上级组织（可选）">
            <Select
              allowClear
              placeholder="顶级组织"
              options={parentOptions}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="owner_user_id" label="负责人">
            <UserPicker placeholder="从本组织成员或全站用户中选一个作为负责人" />
          </Form.Item>
          <Form.Item name="plan_id" label="套餐（可选）">
            <Select
              allowClear
              placeholder="不关联套餐"
              showSearch
              optionFilterProp="label"
              options={plans.map((p) => ({
                label: `${p.name}（${p.code}）月 ¥${p.price_monthly || 0} · ${p.max_seats || 0} 席位`,
                value: p.id,
              }))}
              notFoundContent={plans.length === 0 ? "暂无套餐，请先到「套餐管理」建立" : "无匹配"}
            />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="max_seats" label="席位上限" rules={[{ required: true }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>

          {/* 仅新建 + 选了上级组织 时显示「继承上级成员」开关 */}
          {!editRecord && parentOrg && (
            <>
              <Divider style={{ margin: "8px 0 12px" }} />
              <Alert
                type="success"
                showIcon
                style={{ marginBottom: 8 }}
                message={
                  <Space>
                    <UserAddOutlined />
                    <span>将自动从「{parentOrg.name}」继承现有成员到新组织</span>
                  </Space>
                }
              />
              <Form.Item label=" " colon={false} style={{ marginBottom: 0 }}>
                <Space>
                  <Switch checked={inheritMembers} onChange={setInheritMembers} />
                  <Text>同时继承上级组织的成员（默认开）</Text>
                </Space>
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
};

/* ───────────────────────────────────────────────────────────────
 * 部门 Modal：parent_id 和 leader_user_id 改成 Select
 * ─────────────────────────────────────────────────────────────── */
const DeptTab: React.FC<{ orgId: string; headerExtra?: React.ReactNode }> = ({ orgId, headerExtra }) => {
  const { message } = App.useApp();
  const [list, setList] = useState<any[]>([]);
  const [members, setMembers] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await listDepartments(orgId);
      setList(Array.isArray(res) ? res : (res?.data || []));
    } catch {
      setList([]);
    }
    try {
      const res = await listMembers(orgId);
      setMembers(Array.isArray(res) ? res : (res?.data || []));
    } catch {
      setMembers([]);
    }
    setLoading(false);
  };
  useEffect(() => { load(); }, [orgId]);

  // 监听来自 Card 的"新建部门"按钮事件
  useEffect(() => {
    const onAdd = (e: any) => {
      if (e?.detail?.orgId === orgId) {
        form.resetFields();
        setModal(true);
      }
    };
    const onRefresh = (e: any) => {
      if (e?.detail?.orgId === orgId) load();
    };
    window.addEventListener("aipm:dept-add" as any, onAdd as any);
    window.addEventListener("aipm:org-refresh" as any, onRefresh as any);
    return () => {
      window.removeEventListener("aipm:dept-add" as any, onAdd as any);
      window.removeEventListener("aipm:org-refresh" as any, onRefresh as any);
    };
  }, [orgId]);

  const handleCreate = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await createDepartment(orgId, values);
      message.success("部门已创建");
      setModal(false);
      form.resetFields();
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteDepartment(orgId, id);
      message.success("部门已删除");
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "删除失败");
    }
  };

  const deptOptions = list.map((d) => ({ label: d.name, value: d.id }));

  const columns = [
    { title: "部门名称", dataIndex: "name" },
    {
      title: "上级部门", dataIndex: "parent_id",
      render: (v: any) => {
        if (!v) return <Text type="secondary">顶级</Text>;
        const p = list.find((d) => d.id === v);
        return p ? p.name : <Text type="secondary">{v}</Text>;
      },
    },
    {
      title: "负责人", dataIndex: "leader_user_id",
      render: (v: any) => {
        if (!v) return "-";
        const m = members.find((u) => u.user_id === v);
        if (m) return `${m.full_name || m.username}${m.email ? " · " + m.email : ""}`;
        return v;
      },
    },
    {
      title: "操作", key: "action",
      render: (_: any, r: any) => (
        <Popconfirm title="确认删除该部门？" onConfirm={() => handleDelete(r.id)}>
          <Button size="small" danger>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 12,
      }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          为本组织建立部门层级，负责人可从已添加的成员中选
        </Text>
        <Space>{headerExtra}</Space>
      </div>
      <Table rowKey="id" size="small" loading={loading} dataSource={list} columns={columns} pagination={false}
        locale={{ emptyText: "暂无部门，请点击右上角「新建部门」" }} />
      <Modal title="新建部门" open={modal} onOk={handleCreate} confirmLoading={saving} onCancel={() => setModal(false)} destroyOnClose width={520}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="部门名称" rules={[{ required: true }]}>
            <Input placeholder="如 研发部" />
          </Form.Item>
          <Form.Item name="parent_id" label="上级部门（可选）">
            <Select
              allowClear
              placeholder="顶级部门"
              options={deptOptions}
              showSearch
              optionFilterProp="label"
              notFoundContent="暂无部门"
            />
          </Form.Item>
          <Form.Item name="leader_user_id" label="负责人（可选）">
            <UserPicker orgMembers={members} placeholder="从本组织成员中选一个作为部门负责人" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

/* ───────────────────────────────────────────────────────────────
 * 成员 Modal：user_id 和 department_id 改成 Select
 * ─────────────────────────────────────────────────────────────── */
const MemberTab: React.FC<{ orgId: string; headerExtra?: React.ReactNode }> = ({ orgId, headerExtra }) => {
  const { message } = App.useApp();
  const [list, setList] = useState<any[]>([]);
  const [depts, setDepts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [roleModal, setRoleModal] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const [roleForm] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res = await listMembers(orgId);
      setList(Array.isArray(res) ? res : (res?.data || []));
    } catch { setList([]); }
    try {
      const res = await listDepartments(orgId);
      setDepts(Array.isArray(res) ? res : (res?.data || []));
    } catch { setDepts([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, [orgId]);

  // 监听来自 Card 的事件
  useEffect(() => {
    const onAdd = (e: any) => {
      if (e?.detail?.orgId === orgId) openAdd();
    };
    const onRefresh = (e: any) => {
      if (e?.detail?.orgId === orgId) load();
    };
    window.addEventListener("aipm:member-add" as any, onAdd as any);
    window.addEventListener("aipm:org-refresh" as any, onRefresh as any);
    return () => {
      window.removeEventListener("aipm:member-add" as any, onAdd as any);
      window.removeEventListener("aipm:org-refresh" as any, onRefresh as any);
    };
  }, [orgId]);

  const openAdd = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ role_in_org: "member" });
    setModal(true);
  };

  const handleAdd = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await addMember(orgId, values);
      message.success("成员已添加");
      setModal(false);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "添加失败");
    } finally {
      setSaving(false);
    }
  };

  const openRole = (r: any) => {
    setEditing(r);
    roleForm.resetFields();
    roleForm.setFieldsValue({ role_in_org: r.role_in_org || "member" });
    setRoleModal(true);
  };
  const handleRole = async () => {
    const values = await roleForm.validateFields();
    if (!editing) return;
    setSaving(true);
    try {
      await updateMember(orgId, editing.user_id || editing.id, values);
      message.success("角色已更新");
      setRoleModal(false);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "更新失败");
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (userId: string) => {
    try {
      await removeMember(orgId, userId);
      message.success("成员已移除");
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "移除失败");
    }
  };

  const deptOptions = depts.map((d) => ({ label: d.name, value: d.id }));

  const columns = [
    {
      title: "姓名", dataIndex: "username",
      render: (v: any, r: any) => (
        <Space direction="vertical" size={0}>
          <Text strong>{r.full_name || v}</Text>
          {r.full_name && <Text type="secondary" style={{ fontSize: 12 }}>@{v}</Text>}
        </Space>
      ),
    },
    { title: "邮箱", dataIndex: "email", render: (v: any) => v || "-" },
    {
      title: "组织内角色", dataIndex: "role_in_org",
      render: (v: any) => {
        const color = v === "owner" ? "gold" : v === "org_admin" ? "geekblue" : "default";
        const label = v === "owner" ? "所有者" : v === "org_admin" ? "管理员" : v === "admin" ? "管理员" : "成员";
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: "部门", dataIndex: "department_id",
      render: (v: any) => {
        if (!v) return <Text type="secondary">未分配</Text>;
        const d = depts.find((x) => x.id === v);
        return d ? d.name : <Text type="secondary">{v}</Text>;
      },
    },
    {
      title: "套餐", dataIndex: "plan_name",
      render: (v: any, r: any) => {
        if (r.is_default_user) return <Tag color="default">默认用户</Tag>;
        if (v) return (
          <Space size={4}>
            <Tag color="gold">{v}</Tag>
            {r.expire_at && dayjs(r.expire_at).isBefore(dayjs()) && <Tag color="red">已过期</Tag>}
          </Space>
        );
        return <Text type="secondary">-</Text>;
      },
    },
    { title: "等级", dataIndex: "level_code", render: (v: any) => v || "-" },
    {
      title: "操作", key: "action",
      render: (_: any, r: any) => (
        <Space>
          <Button size="small" onClick={() => openRole(r)}>调整角色</Button>
          <Popconfirm title="确认移除该成员？" onConfirm={() => handleRemove(r.user_id || r.id)}>
            <Button size="small" danger>移除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 12,
      }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {list.length > 0
            ? `共 ${list.length} 名成员（其中 ${list.filter((m: any) => m.is_default_user).length} 名为默认用户需充值才能使用）`
            : "暂无成员，请点击右上角「添加成员」"}
        </Text>
        <Space>{headerExtra}</Space>
      </div>
      <Table
        rowKey={(r: any) => r.user_id || r.id}
        size="small"
        loading={loading}
        dataSource={list}
        columns={columns}
        pagination={false}
        locale={{ emptyText: "暂无成员，请点击右上角「添加成员」" }}
      />

      <Modal title="添加成员" open={modal} onOk={handleAdd} confirmLoading={saving} onCancel={() => setModal(false)} destroyOnClose width={520}>
        <Form form={form} layout="vertical">
          <Form.Item name="user_id" label="用户" rules={[{ required: true }]}>
            <UserPicker placeholder="输入姓名 / 用户名 / 邮箱搜索" />
          </Form.Item>
          <Form.Item name="department_id" label="部门（可选）">
            <Select
              allowClear
              placeholder="不分配"
              options={deptOptions}
              showSearch
              optionFilterProp="label"
              notFoundContent="暂无部门，请先创建"
            />
          </Form.Item>
          <Form.Item name="role_in_org" label="组织内角色" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="调整成员角色" open={roleModal} onOk={handleRole} confirmLoading={saving} onCancel={() => setRoleModal(false)} destroyOnClose>
        <Form form={roleForm} layout="vertical">
          <Form.Item name="role_in_org" label="组织内角色" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default OrganizationManagement;
