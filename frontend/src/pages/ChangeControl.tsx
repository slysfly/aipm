import React, { useState, useEffect, useMemo } from "react";
import {
  Card, Typography, Tag, Button, Space, Table, Modal, Form, Input, Select, App,
  Row, Col, Statistic, Divider, Spin, Popconfirm, Alert, Tooltip, Empty,
} from "antd";
import {
  PlusOutlined, SwapOutlined, HistoryOutlined, CheckCircleOutlined,
  CloseCircleOutlined, ProjectOutlined, DeleteOutlined, ArrowRightOutlined,
  WarningOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import { motion } from "framer-motion";
import { changeApi, projectApi } from "../api";

const { Title, Text } = Typography;

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface ChangeItem {
  key: string;
  scope: string;           // 业务标签（自动 = 实体名 + 字段名）
  entity_type: "project" | "task" | "milestone" | "";
  entity_id: string;
  entity_label: string;    // 显示用实体名
  field: string;
  field_label: string;     // 显示用字段名
  before: string;
  after: string;
}

interface ChangeRequest {
  id: string;
  projectId: string;
  projectName: string;
  title: string;
  description: string;
  reason: string;
  impact: string;
  priority: string;
  status: string;
  category: string;
  requestedBy: string;
  approvedBy: string;
  createdAt: string;
  resolvedAt: string;
  changeItems?: ChangeItem[];
  executionLog?: Array<{
    scope: string; entity_type: string; entity_id: string; field: string;
    before: any; after: any; applied: boolean; verified: boolean;
    applied_at: string; error: string;
  }>;
}

const ENTITY_TYPE_LABEL: Record<string, string> = {
  project: "项目", task: "任务", milestone: "里程碑",
};

const ENTITY_TYPE_LIST: Array<{ value: string; label: string }> = [
  { value: "project", label: "项目" },
  { value: "task", label: "任务" },
  { value: "milestone", label: "里程碑" },
];

// ── 校验：硬阻断，未明确「由什么变为什么」一律拒绝 ────────────────────────────────
function validateItems(items: ChangeItem[]): string | null {
  if (!items.length) return "请至少添加一条「由什么变为什么」的变更明细";
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    const idx = i + 1;
    if (!it.entity_type) return `第 ${idx} 条：未选择实体类型`;
    if (!it.entity_id)   return `第 ${idx} 条：未选择实体`;
    if (!it.field)       return `第 ${idx} 条：未选择变更字段`;
    if (it.before === "" || it.before === null || it.before === undefined)
      return `第 ${idx} 条：未拉取当前值（选择实体+字段后会自动填充）`;
    if (it.after === "" || it.after === null || it.after === undefined)
      return `第 ${idx} 条：未填写「新内容」`;
    if (String(it.before).trim() === String(it.after).trim())
      return `第 ${idx} 条：「原内容」与「新内容」相同，未明确变化内容，不予提交`;
  }
  return null;
}

// ── 主组件 ─────────────────────────────────────────────────────────────────────
const ChangeControl: React.FC = () => {
  const { message } = App.useApp();
  const [changes, setChanges] = useState<ChangeRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [detailModal, setDetailModal] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [form] = Form.useForm();

  // 结构化变更明细
  const [items, setItems] = useState<ChangeItem[]>([]);
  const [whitelist, setWhitelist] = useState<Record<string, Record<string, any>>>({});
  const [entities, setEntities] = useState<{ tasks: any[]; milestones: any[] }>({ tasks: [], milestones: [] });
  const [itemsError, setItemsError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await changeApi.list(projectId ? { project_id: projectId } : {});
      setChanges(r?.items || []);
    } catch {
      message.error("加载变更请求失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [projectId]);
  useEffect(() => {
    projectApi.list().then((r: any) => setProjects(r?.items || r || [])).catch(() => {});
  }, []);

  // 打开模态时拉取字段白名单
  useEffect(() => {
    if (!modalOpen) return;
    changeApi.whitelist().then((w: any) => setWhitelist(w || {})).catch(() => {});
  }, [modalOpen]);

  // 监听表单内 projectId 变化 → 拉取 entities + 清空 items
  const watchedPid = Form.useWatch("projectId", form);
  useEffect(() => {
    if (!modalOpen) return;
    const pid = watchedPid || projectId;
    if (!pid) {
      setEntities({ tasks: [], milestones: [] });
      setItems([]); setItemsError(null);
      return;
    }
    changeApi.entities(pid).then((r: any) => {
      setEntities({ tasks: r?.tasks || [], milestones: r?.milestones || [] });
    }).catch(() => setEntities({ tasks: [], milestones: [] }));
    setItems([]); setItemsError(null);
  }, [watchedPid, modalOpen, projectId]);

  // 每次 items 变化重新校验
  useEffect(() => {
    setItemsError(validateItems(items));
  }, [items]);

  const updateStatus = async (id: string, status: string, approvedBy?: string) => {
    try {
      const r: any = await changeApi.update(id, { status, ...(approvedBy ? { approvedBy } : {}) });
      // 后端在 approved 时会触发执行并回写 execution_log
      if (status === "approved") {
        const log = r?.executionLog || [];
        const ok = log.filter((x: any) => x.verified).length;
        const fail = log.length - ok;
        if (log.length === 0) {
          message.warning("已批准，但无变更明细可执行");
        } else if (fail === 0) {
          message.success(`已批准并成功执行 ${ok} 项变更`);
        } else {
          message.warning(`已批准：${ok} 项成功，${fail} 项失败（详见详情）`);
        }
      } else {
        message.success("操作成功");
      }
      await load();
    } catch (e: any) {
      message.error("操作失败：" + (e?.response?.data?.detail || e?.message || "未知错误"));
    }
  };

  const handleDelete = async (id: string) => {
    try { await changeApi.remove(id); message.success("已删除"); await load(); }
    catch { message.error("删除失败"); }
  };

  const filtered = statusFilter === "all" ? changes : changes.filter(c => c.status === statusFilter);

  const getStatusTag = (s: string) => {
    const map: Record<string, { color: string; label: string }> = {
      draft: { color: "default", label: "草稿" },
      submitted: { color: "blue", label: "已提交" },
      in_review: { color: "orange", label: "评审中" },
      approved: { color: "green", label: "已批准" },
      rejected: { color: "red", label: "已拒绝" },
      implemented: { color: "purple", label: "已实施" },
    };
    return <Tag color={map[s]?.color || "default"}>{map[s]?.label || s}</Tag>;
  };

  const columns = [
    { title: "变更标题", dataIndex: "title", key: "title", render: (t: string, r: ChangeRequest) => (
      <Button type="link" onClick={() => setDetailModal(r.id)} style={{ padding: 0, textAlign: "left" }}>
        <Text strong>{t}</Text>
        {r.changeItems && r.changeItems.length > 0 &&
          <Tag color="geekblue" style={{ marginLeft: 8 }}>{r.changeItems.length} 项明细</Tag>}
      </Button>
    )},
    { title: "关联项目", dataIndex: "projectName", key: "projectName", render: (v: string) =>
      v ? <Tag icon={<ProjectOutlined />} color="geekblue">{v}</Tag> : <Text type="secondary">未关联</Text> },
    { title: "类别", dataIndex: "category", key: "category", render: (c: string) => <Tag style={{ borderRadius: 6 }}>{c}</Tag> },
    { title: "优先级", dataIndex: "priority", key: "priority", render: (p: string) => <Tag color={p === "high" ? "red" : p === "medium" ? "orange" : "blue"}>{p === "high" ? "高" : p === "medium" ? "中" : "低"}</Tag> },
    { title: "状态", dataIndex: "status", key: "status", render: (s: string) => getStatusTag(s) },
    { title: "申请人", dataIndex: "requestedBy", key: "requestedBy" },
    { title: "创建时间", dataIndex: "createdAt", key: "createdAt" },
    { title: "操作", key: "action", render: (_: any, r: ChangeRequest) => (
      <Space wrap>
        {r.status === "submitted" && <Button size="small" type="primary" onClick={() => { updateStatus(r.id, "in_review"); message.success("已进入评审"); }}>提交评审</Button>}
        {r.status === "in_review" && <>
          <Button size="small" type="primary" style={{ background: "#10B981", borderColor: "#10B981" }} onClick={() => updateStatus(r.id, "approved", "CCB")}>批准</Button>
          <Button size="small" danger onClick={() => updateStatus(r.id, "rejected", "CCB")}>拒绝</Button>
        </>}
        <Popconfirm title="确定删除该变更？" onConfirm={() => handleDelete(r.id)} okText="删除" cancelText="取消">
          <Button size="small" type="link" danger>删除</Button>
        </Popconfirm>
      </Space>
    )},
  ];

  const detail = detailModal ? changes.find(c => c.id === detailModal) : null;

  // ── 提交：先校验，再调后端 ─────────────────────────────────────────────────────
  const handleSubmit = async (values: any) => {
    const err = validateItems(items);
    if (err) { setItemsError(err); message.error(err); return; }
    const pid = values.projectId || projectId || "";
    const pname = projects.find((p: any) => p.id === pid)?.name || "";
    if (!pid) { message.error("请先关联一个项目"); return; }
    setSaving(true);
    try {
      // 仅发送白名单内字段
      const cleanItems = items.map((it) => ({
        scope: it.scope || `${it.entity_label || ""} · ${it.field_label || it.field}`,
        entity_type: it.entity_type, entity_id: it.entity_id, entity_label: it.entity_label,
        field: it.field, field_label: it.field_label,
        before: String(it.before), after: String(it.after),
      }));
      await changeApi.create({
        ...values, status: "submitted",
        project_id: pid, project_name: pname,
        change_items: cleanItems,
      });
      message.success("变更请求已提交，等待 CCB 评审");
      setModalOpen(false); form.resetFields(); setItems([]); setItemsError(null);
      await load();
    } catch (e: any) {
      const detail = e?.response?.data?.detail || "提交失败";
      message.error(detail);
    } finally {
      setSaving(false);
    }
  };

  // ── 行编辑器：选择实体后自动填 before；切换字段也自动刷新 before ────────────────
  const updateItem = (key: string, patch: Partial<ChangeItem>) => {
    setItems((prev) => prev.map((it) => {
      if (it.key !== key) return it;
      const next = { ...it, ...patch };
      // 选择实体后自动尝试填 before
      if (patch.entity_type !== undefined || patch.entity_id !== undefined || patch.field !== undefined) {
        next.before = _resolveBefore(next);
        next.scope = `${next.entity_label || ""} · ${next.field_label || next.field}`;
      }
      return next;
    }));
  };

  const _resolveBefore = (it: ChangeItem): string => {
    if (!it.entity_type || !it.entity_id || !it.field) return "";
    let obj: any = null;
    if (it.entity_type === "project") {
      obj = projects.find((p: any) => p.id === it.entity_id) || null;
    } else if (it.entity_type === "task") {
      obj = entities.tasks.find((t: any) => t.id === it.entity_id) || null;
    } else if (it.entity_type === "milestone") {
      obj = entities.milestones.find((m: any) => m.id === it.entity_id) || null;
    }
    if (!obj) return "";
    const v = obj[it.field];
    if (v === null || v === undefined) return "";
    return String(v);
  };

  const addItem = () => {
    setItems((prev) => [...prev, {
      key: Math.random().toString(36).slice(2, 10),
      scope: "", entity_type: "", entity_id: "", entity_label: "",
      field: "", field_label: "", before: "", after: "",
    }]);
  };
  const removeItem = (key: string) => setItems((prev) => prev.filter((i) => i.key !== key));

  // 当前选中项目对应的实体选项
  const entityOptions = useMemo(() => {
    return (et: string) => {
      if (et === "project") return projects.map((p: any) => ({ label: p.name, value: p.id }));
      if (et === "task")     return entities.tasks.map((t: any) => ({ label: `${t.wbs_code ? t.wbs_code + " " : ""}${t.name}`, value: t.id }));
      if (et === "milestone")return entities.milestones.map((m: any) => ({ label: m.name, value: m.id }));
      return [];
    };
  }, [projects, entities]);

  const fieldOptions = (et: string) => {
    const dict = whitelist[et] || {};
    return Object.keys(dict).map((k) => ({ label: dict[k].label, value: k }));
  };

  // 简单必填校验（标题 + 关联项目）
  const formHasBase = !!form.getFieldValue("title") && !!form.getFieldValue("projectId") &&
                      !!form.getFieldValue("category") && !!form.getFieldValue("priority");
  const canSubmit = !itemsError && formHasBase && items.length > 0;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>变更控制 (Change Control)</Title>
          <Text type="secondary">PMI中国AI项目管理社区 变更管理 · 一体化变更控制流程 (CCB) · 审批通过后 AI 自动落地 + 校验</Text>
        </div>
        <Space wrap>
          <Select allowClear placeholder="全部项目" style={{ width: 180 }} value={projectId || undefined}
            onChange={(v) => setProjectId(v || "")}
            options={projects.map((p: any) => ({ label: p.name, value: p.id }))} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)} data-tour="changes-new">提交变更请求</Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>总变更</span>} value={changes.length} prefix={<SwapOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>已批准</span>} value={changes.filter(c => c.status === "approved" || c.status === "implemented").length} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>评审中</span>} value={changes.filter(c => c.status === "in_review").length} prefix={<HistoryOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #EF4444 0%, #DC2626 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>已拒绝</span>} value={changes.filter(c => c.status === "rejected").length} prefix={<CloseCircleOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
      </Row>

      <Card title="变更请求列表" style={{ borderRadius: 16 }} className="card-hover" data-tour="changes-list" extra={
        <Select defaultValue="all" style={{ width: 130 }} onChange={setStatusFilter}
          options={[{ label: "全部状态", value: "all" }, { label: "草稿", value: "draft" }, { label: "已提交", value: "submitted" }, { label: "评审中", value: "in_review" }, { label: "已批准", value: "approved" }, { label: "已拒绝", value: "rejected" }]} />
      }>
        <Spin spinning={loading}>
          <Table dataSource={filtered} columns={columns} rowKey="id" pagination={{ pageSize: 10 }} className="enhanced-table" />
        </Spin>
      </Card>

      {/* ── 详情弹窗 ──────────────────────────────────────────────────────────── */}
      <Modal title="变更详情" open={!!detailModal} onCancel={() => setDetailModal(null)} footer={null} width={760}>
        {detail && (
          <div>
            <div style={{ marginBottom: 12 }}><Title level={5}>{detail.title}</Title></div>
            <Space style={{ marginBottom: 16 }} wrap>
              {getStatusTag(detail.status)}
              <Tag color={detail.priority === "high" ? "red" : detail.priority === "medium" ? "orange" : "blue"}>
                {detail.priority === "high" ? "高优先级" : detail.priority === "medium" ? "中优先级" : "低优先级"}
              </Tag>
              <Tag>{detail.category}</Tag>
            </Space>

            {/* 变更明细对比表 */}
            <Divider orientation="left" plain>
              <ThunderboltOutlined style={{ color: "#FA8C16" }} /> 变更明细（由 → 为）
            </Divider>
            {(detail.changeItems && detail.changeItems.length > 0) ? (
              <Table
                size="small"
                rowKey={(r: any, i: number) => `${r.entity_id}-${r.field}-${i}`}
                pagination={false}
                dataSource={detail.changeItems}
                columns={[
                  { title: "实体", dataIndex: "entity_type", width: 80, render: (v: string) => <Tag>{ENTITY_TYPE_LABEL[v] || v}</Tag> },
                  { title: "名称", dataIndex: "entity_label", width: 200 },
                  { title: "字段", dataIndex: "field_label", width: 120, render: (v: string, r: any) => v || r.field },
                  {
                    title: "原内容", dataIndex: "before", width: 180,
                    render: (v: any) => <Text code style={{ background: "#FFF1F0", color: "#CF1322" }}>{String(v ?? "")}</Text>,
                  },
                  { title: "", width: 40, render: () => <ArrowRightOutlined style={{ color: "#10B981" }} /> },
                  {
                    title: "新内容", dataIndex: "after", width: 180,
                    render: (v: any) => <Text code style={{ background: "#F6FFED", color: "#389E0D" }}>{String(v ?? "")}</Text>,
                  },
                ]}
              />
            ) : <Empty description="无结构化变更明细" />}

            {/* 执行结果 */}
            {(detail.executionLog && detail.executionLog.length > 0) && (
              <>
                <Divider orientation="left" plain>
                  <ThunderboltOutlined /> AI 执行结果与校验
                </Divider>
                <Table
                  size="small"
                  rowKey={(r: any, i: number) => `log-${r.entity_id}-${r.field}-${i}`}
                  pagination={false}
                  dataSource={detail.executionLog}
                  columns={[
                    {
                      title: "状态", width: 90,
                      render: (_: any, r: any) => r.verified
                        ? <Tag color="green" icon={<CheckCircleOutlined />}>已校验</Tag>
                        : r.applied
                          ? <Tag color="orange" icon={<WarningOutlined />}>写入但未校验</Tag>
                          : <Tag color="red" icon={<CloseCircleOutlined />}>失败</Tag>,
                    },
                    { title: "实体", dataIndex: "entity_type", width: 80, render: (v: string) => <Tag>{ENTITY_TYPE_LABEL[v] || v}</Tag> },
                    { title: "字段", dataIndex: "field", width: 120 },
                    { title: "原 → 新", render: (_: any, r: any) =>
                      <span><Text code>{String(r.before)}</Text> <ArrowRightOutlined /> <Text code>{String(r.after)}</Text></span> },
                    { title: "应用时间", dataIndex: "applied_at", width: 170, render: (v: string) => v || "—" },
                    { title: "校验说明", dataIndex: "error", render: (v: string) => v ? <Text type="danger">{v}</Text> : <Text type="secondary">—</Text> },
                  ]}
                />
              </>
            )}

            <Divider>变更描述 / 原因 / 影响</Divider>
            <div style={{ marginBottom: 8 }}><Text strong>描述：</Text><Text>{detail.description || "—"}</Text></div>
            <div style={{ marginBottom: 8 }}><Text strong>原因：</Text><Text>{detail.reason || "—"}</Text></div>
            <div style={{ marginBottom: 8 }}><Text strong>影响：</Text><Text>{detail.impact || "—"}</Text></div>

            <Divider>审批信息</Divider>
            <Text>关联项目：{detail.projectName || "未关联"} | 申请人：{detail.requestedBy} | 审批人：{detail.approvedBy || "待审批"} | 创建：{detail.createdAt} | 解决：{detail.resolvedAt || "—"}</Text>
          </div>
        )}
      </Modal>

      {/* ── 提交弹窗 ──────────────────────────────────────────────────────────── */}
      <Modal
        title="提交变更请求"
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setItems([]); setItemsError(null); }}
        footer={null}
        destroyOnClose
        width={820}
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          message="CCB 变更控制规范"
          description={
            <div>
              审批通过后，AI 将按下方每条「由什么变为什么」自动落地到对应实体，并立即再读回校验。
              <br />
              <Text strong>提交前必须明确每一项的变化内容；前后相同或描述不清的变更不予提交。</Text>
            </div>
          }
        />
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item label="变更标题" name="title" rules={[{ required: true, message: "请输入变更标题" }]}>
                <Input placeholder="例如：增加 AI 多智能体模块" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="关联项目" name="projectId" rules={[{ required: true, message: "请选择关联项目" }]} initialValue={projectId || undefined}>
                <Select placeholder="选择关联的项目" options={projects.map((p: any) => ({ label: p.name, value: p.id }))} />
              </Form.Item>
            </Col>
          </Row>

          {/* ── 结构化变更明细 ────────────────────────────────────────────────── */}
          <Divider orientation="left" plain>
            <SwapOutlined /> 变更明细（由 → 为）
          </Divider>

          {items.length === 0 && (
            <Alert type="warning" showIcon style={{ marginBottom: 12 }}
              message="尚未添加任何变更明细"
              description="请明确至少一条「由什么变为什么」，否则无法提交。"
            />
          )}

          {items.map((it, idx) => (
            <Card key={it.key} size="small" style={{ marginBottom: 10, borderRadius: 10 }}
              title={<span><Text strong>#{idx + 1}</Text> {it.scope || <Text type="secondary">未选择实体/字段</Text>}</span>}
              extra={
                <Button danger size="small" type="text" icon={<DeleteOutlined />} onClick={() => removeItem(it.key)}>移除</Button>
              }
            >
              <Row gutter={[8, 8]}>
                <Col xs={24} md={5}>
                  <div style={{ marginBottom: 4 }}><Text type="secondary" style={{ fontSize: 12 }}>实体类型</Text></div>
                  <Select
                    style={{ width: "100%" }} value={it.entity_type || undefined}
                    placeholder="选择类型"
                    options={ENTITY_TYPE_LIST}
                    onChange={(v) => updateItem(it.key, { entity_type: v as any, entity_id: "", entity_label: "", field: "", field_label: "", before: "", after: "" })}
                  />
                </Col>
                <Col xs={24} md={7}>
                  <div style={{ marginBottom: 4 }}><Text type="secondary" style={{ fontSize: 12 }}>实体</Text></div>
                  <Select
                    style={{ width: "100%" }} value={it.entity_id || undefined}
                    placeholder={it.entity_type ? "选择实体" : "先选类型"}
                    disabled={!it.entity_type}
                    options={entityOptions(it.entity_type)}
                    showSearch optionFilterProp="label"
                    onChange={(v, opt: any) => updateItem(it.key, { entity_id: v, entity_label: opt?.label || "" })}
                  />
                </Col>
                <Col xs={24} md={5}>
                  <div style={{ marginBottom: 4 }}><Text type="secondary" style={{ fontSize: 12 }}>变更字段</Text></div>
                  <Select
                    style={{ width: "100%" }} value={it.field || undefined}
                    placeholder={it.entity_type ? "选择字段" : "先选类型"}
                    disabled={!it.entity_type}
                    options={fieldOptions(it.entity_type)}
                    onChange={(v, opt: any) => updateItem(it.key, { field: v, field_label: opt?.label || v })}
                  />
                </Col>
                <Col xs={24} md={7}>
                  <div style={{ marginBottom: 4 }}><Text type="secondary" style={{ fontSize: 12 }}>原内容（自动拉取）</Text></div>
                  <Input
                    value={it.before}
                    placeholder={it.entity_id && it.field ? "已自动拉取" : "—"}
                    readOnly
                    style={{ background: "#FFF7E6", color: "#874D00", fontWeight: 600 }}
                  />
                </Col>
                <Col xs={24} md={24}>
                  <div style={{ marginBottom: 4 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      新内容（必填，且必须与原内容不同）
                    </Text>
                    {it.field && whitelist[it.entity_type]?.[it.field]?.kind && (
                      <Tag style={{ marginLeft: 8 }} color="blue">
                        类型：{whitelist[it.entity_type][it.field].kind}
                        {whitelist[it.entity_type][it.field].options && ` · 可选：${whitelist[it.entity_type][it.field].options.join("/")}`}
                      </Tag>
                    )}
                  </div>
                  <Input
                    value={it.after}
                    placeholder={it.field ? `输入新的「${it.field_label || it.field}」` : "先选择字段"}
                    disabled={!it.field}
                    onChange={(e) => updateItem(it.key, { after: e.target.value })}
                    style={{ background: "#F6FFED" }}
                  />
                </Col>
              </Row>
            </Card>
          ))}

          <Button type="dashed" block icon={<PlusOutlined />} onClick={addItem} style={{ marginBottom: 12 }}>
            添加变更项
          </Button>

          {itemsError && <Alert type="error" showIcon style={{ marginBottom: 12 }} message={itemsError} />}

          <Row gutter={12}>
            <Col xs={24} md={16}>
              <Form.Item label="详细描述" name="description">
                <Input.TextArea rows={2} placeholder="可选：补充说明本次变更的背景/动机" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item label="类别" name="category" rules={[{ required: true }]} initialValue="范围变更">
                <Select options={[{ label: "范围变更", value: "范围变更" }, { label: "进度变更", value: "进度变更" }, { label: "成本变更", value: "成本变更" }, { label: "技术变更", value: "技术变更" }, { label: "设计变更", value: "设计变更" }, { label: "资源变更", value: "资源变更" }]} />
              </Form.Item>
              <Form.Item label="优先级" name="priority" rules={[{ required: true }]} initialValue="medium">
                <Select options={[{ label: "高", value: "high" }, { label: "中", value: "medium" }, { label: "低", value: "low" }]} />
              </Form.Item>
              <Form.Item label="变更原因" name="reason">
                <Input.TextArea rows={2} placeholder="可选" />
              </Form.Item>
              <Form.Item label="影响分析" name="impact">
                <Input.TextArea rows={2} placeholder="可选" />
              </Form.Item>
            </Col>
          </Row>

          <Tooltip title={!canSubmit ? (itemsError || "请补全标题、关联项目与至少一条有效变更明细") : "提交后进入评审，审批通过后 AI 将自动落地变更"}>
            <Button type="primary" htmlType="submit" block loading={saving} disabled={!canSubmit}
              icon={<CheckCircleOutlined />}>
              提交变更请求
            </Button>
          </Tooltip>
        </Form>
      </Modal>
    </div>
  );
};

export default ChangeControl;