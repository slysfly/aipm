import React, { useState, useEffect, useCallback } from "react";
import { Card, Button, Typography, Tag, Progress, Modal, Form, Input, Select, InputNumber, Space, Empty, App, Spin, Tooltip, Popconfirm } from "antd";
import { PlusOutlined, FlagOutlined, AimOutlined, DeleteOutlined, EditOutlined, RobotOutlined, LinkOutlined, CheckCircleOutlined, CloseCircleOutlined } from "@ant-design/icons";
import { motion, AnimatePresence } from "framer-motion";
import { okrApi, projectApi } from "../api";

const { Title, Text } = Typography;
const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];

// ---------------------------------------------------------------------------
// Inline-editable KR row component
// ---------------------------------------------------------------------------

interface KrItem {
  id: string;
  title: string;
  description: string;
  target: number;
  current: number;
  unit: string;
  progress: number;
  weight: number;
}

interface KrRowProps {
  kr: KrItem;
  index: number;
  onUpdate: (id: string, field: string, value: any) => void;
  onDelete: (id: string) => void;
}

const KrRow: React.FC<KrRowProps> = ({ kr, index, onUpdate, onDelete }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<KrItem>(kr);

  useEffect(() => { setDraft(kr); }, [kr]);

  const startEdit = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditing(true);
    setDraft({ ...kr });
  };

  const save = () => {
    // Validate
    if (!draft.title.trim()) return;
    onUpdate(kr.id, "_replace", draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(kr);
    setEditing(false);
  };

  if (editing) {
    return (
      <motion.div
        initial={{ opacity: 0.8 }}
        style={{
          padding: "14px 18px", background: "#EEF2FF",
          borderRadius: 10, border: "2px solid #6366F1",
        }}
      >
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          <AimOutlined style={{ color: "#4F46E5", fontSize: 16, marginTop: 8 }} />
          <div style={{ flex: 1 }}>
            <Input
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              placeholder="KR 标题（如：完成核心模块开发）"
              size="small"
              style={{ fontWeight: 600, marginBottom: 6 }}
            />
            <Input.TextArea
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="详细描述 / 验收标准"
              size="small"
              rows={2}
              autoSize
              style={{ marginBottom: 8 }}
            />
            <Space size="small" wrap>
              <span style={{ color: "#64748B", fontSize: 12 }}>当前</span>
              <InputNumber size="small" value={draft.current} min={0}
                onChange={(v) => setDraft({ ...draft, current: v ?? 0 })} style={{ width: 70 }} />
              <span>/</span>
              <span style={{ color: "#64748B", fontSize: 12 }}>目标</span>
              <InputNumber size="small" value={draft.target} min={0}
                onChange={(v) => setDraft({ ...draft, target: v ?? 100 })} style={{ width: 70 }} />
              <Select size="small" value={draft.unit}
                onChange={(v) => setDraft({ ...draft, unit: v })}
                options={[
                  { label: "%", value: "%" },
                  { label: "个", value: "个" },
                  { label: "天", value: "天" },
                  { label: "分", value: "分" },
                  { label: "元", value: "元" },
                  { label: "次", value: "次" },
                  { label: "项", value: "项" },
                ]}
                style={{ width: 65 }} />
              <span style={{ color: "#94A3B8", fontSize: 11 }}>权重</span>
              <InputNumber size="small" value={draft.weight} min={0.1} max={10} step={0.5}
                onChange={(v) => setDraft({ ...draft, weight: v ?? 1 })} style={{ width: 60 }} />
            </Space>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginTop: 8 }}>
          <Button size="small" icon={<CheckCircleOutlined />} type="primary" onClick={save}>保存</Button>
          <Button size="small" icon={<CloseCircleOutlined />} onClick={cancel}>取消</Button>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      style={{
        padding: "12px 16px", background: "#F8FAFC",
        borderRadius: 10, border: "1px solid #E2E8F0",
        cursor: "pointer",
        transition: "border-color 0.2s",
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "#C7D2FE"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "#E2E8F0"; }}
      onClick={startEdit}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <AimOutlined style={{ color: "#8B5CF6", fontSize: 14 }} />
          <Text strong style={{ fontSize: 13 }}>{kr.title || <Text type="secondary">点击编辑 KR 标题…</Text>}</Text>
          {kr.description && (
            <Tooltip title={kr.description}>
              <Text type="secondary" style={{ fontSize: 11, maxWidth: 200 }} ellipsis>{kr.description}</Text>
            </Tooltip>
          )}
        </div>
        <Tag style={{ borderRadius: 6, fontSize: 11 }}>
          {kr.current} / {kr.target} {kr.unit}
        </Tag>
      </div>
      <Progress
        percent={kr.progress}
        size="small"
        strokeColor={{ from: "#8B5CF6", to: "#6366F1" }}
        showInfo={false}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>完成 {kr.progress}% · 权重 {kr.weight}</Text>
        <Popconfirm title="确定删除此 KR？" onConfirm={(e) => { e?.stopPropagation(); onDelete(kr.id); }}>
          <Button size="small" type="text" danger icon={<DeleteOutlined />}
            onClick={(e) => e.stopPropagation()} />
        </Popconfirm>
      </div>
    </motion.div>
  );
};

// ---------------------------------------------------------------------------
// Main OKR page
// ---------------------------------------------------------------------------

const OKRs: React.FC = () => {
  const { message } = App.useApp();
  const [okrs, setOkrs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOkr, setEditingOkr] = useState<any>(null);
  const [expandedOkr, setExpandedOkr] = useState<string | null>(null);

  // Project list for selector
  const [projects, setProjects] = useState<any[]>([]);

  // AI generating state per OKR
  const [aiGenerating, setAiGenerating] = useState<Record<string, boolean>>({});

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await okrApi.list();
      setOkrs(r?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载 OKR 失败");
    } finally {
      setLoading(false);
    }
  };

  const loadProjects = async () => {
    try {
      const r: any = await projectApi.list({ limit: 200 });
      setProjects(r?.items || r?.data || []);
    } catch { /* silent */ }
  };

  useEffect(() => { load(); loadProjects(); }, []);

  // --- CRUD ---

  const handleCreateOkr = () => {
    setEditingOkr({
      objective: "", project_id: undefined,
      keyResults: [], year: "2026", quarter: "Q3", owner: "",
    });
    setModalOpen(true);
  };

  const handleEditOkr = (okr: any) => {
    setEditingOkr({ ...okr });
    setModalOpen(true);
  };

  const handleSaveOkr = async (values: any) => {
    try {
      if (editingOkr?.id) {
        await okrApi.update(editingOkr.id, values);
        message.success("已更新");
      } else {
        await okrApi.create(values);
        message.success("已创建");
      }
      setModalOpen(false);
      setEditingOkr(null);
      load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "保存失败"); }
  };

  const handleDeleteOkr = async (id: string) => {
    try { await okrApi.remove(id); message.success("已删除"); load(); }
    catch (e: any) { message.error(e?.response?.data?.detail || "删除失败"); }
  };

  // --- KR operations ---

  const handleAddKr = useCallback(async (okrId: string) => {
    const okr = okrs.find((o) => o.id === okrId);
    if (!okr) return;
    const newKr: KrItem = {
      id: `kr-${Date.now()}`, title: "", description: "",
      target: 100, current: 0, unit: "%", progress: 0, weight: 1.0,
    };
    const keyResults = [...(okr.keyResults || []), newKr];
    try {
      await okrApi.update(okrId, { keyResults });
      setOkrs((prev) => prev.map((o) => o.id === okrId ? { ...o, keyResults } : o));
    } catch (e: any) { message.error(e?.response?.data?.detail || "添加 KR 失败"); }
  }, [okrs]);

  const handleUpdateKr = useCallback(async (okrId: string, krId: string, field: string, value: any) => {
    const okr = okrs.find((o) => o.id === okrId);
    if (!okr) return;

    let updatedKrs: KrItem[];
    if (field === "_replace") {
      // Full replace of one KR
      updatedKrs = (okr.keyResults || []).map((k: KrItem) =>
        k.id === (value as KrItem).id ? value : k
      );
    } else {
      updatedKrs = (okr.keyResults || []).map((k: KrItem) =>
        k.id === krId ? { ...k, [field]: value } : k
      );
    }

    try {
      await okrApi.update(okrId, { keyResults: updatedKrs });
      setOkrs((prev) => prev.map((o) => o.id === okrId ? { ...o, keyResults: updatedKrs } : o));
    } catch (e: any) { message.error(e?.response?.data?.detail || "更新 KR 失败"); }
  }, [okrs]);

  const handleDeleteKr = useCallback(async (okrId: string, krId: string) => {
    const okr = okrs.find((o) => o.id === okrId);
    if (!okr) return;
    const keyResults = (okr.keyResults || []).filter((k: KrItem) => k.id !== krId);
    try {
      await okrApi.update(okrId, { keyResults });
      setOkrs((prev) => prev.map((o) => o.id === okrId ? { ...o, keyResults } : o));
      message.success("KR 已删除");
    } catch (e: any) { message.error(e?.response?.data?.detail || "删除 KR 失败"); }
  }, [okrs]);

  // --- AI Generate KRs ---

  const handleAiGenerateKrs = async (okrId: string) => {
    setAiGenerating((prev) => ({ ...prev, [okrId]: true }));
    try {
      const res: any = await okrApi.aiGenerateKrs(okrId, { count: 4 });
      message.success(res.message || `成功生成 ${res.generated_krs?.length || 0} 个 KR`);
      load(); // Reload to get fresh data with new KRs
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "AI 生成 KR 失败，请稍后重试");
    } finally {
      setAiGenerating((prev) => ({ ...prev, [okrId]: false }));
    }
  };

  // --- Render helpers ---

  const getProjectName = (pid: string | null | undefined) => {
    if (!pid) return null;
    const p = projects.find((x) => x.id === pid);
    return p?.name || pid;
  };

  return (
    <div>
      {/* Page header */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>OKR 目标管理</Title>
          <Text type="secondary">将公司战略目标分解为可衡量的关键结果，逐层对齐</Text>
        </div>
        <Space>
          <Select defaultValue="2026-Q3" style={{ width: 130 }} data-tour="okr-quarter"
            options={["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"].map(q => ({ label: q, value: q }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateOkr} data-tour="okr-new">新建 OKR</Button>
        </Space>
      </div>

      {/* Content */}
      <AnimatePresence>
        {loading && okrs.length === 0 ? (
          <div className="enhanced-empty">
            <Empty description="加载中..." />
          </div>
        ) : okrs.length === 0 ? (
          <div className="enhanced-empty">
            <div style={{ fontSize: 60, marginBottom: 16 }}>🎯</div>
            <h3>还没有 OKR</h3>
            <p>设定目标和关键结果，驱动团队聚焦最重要的事情</p>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateOkr}>创建第一个 OKR</Button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {okrs.map((okr, idx) => (
              <motion.div
                key={okr.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1, duration: 0.4 }}
              >
                <Card
                  className="card-hover"
                  style={{ borderRadius: 16, border: "1px solid #E2E8F0" }}
                  styles={{ body: { padding: 20 } }}
                  onClick={() => setExpandedOkr(expandedOkr === okr.id ? null : okr.id)}
                >
                  {/* Card header */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", cursor: "pointer" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <div style={{
                          width: 32, height: 32, borderRadius: 10,
                          background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          color: "#fff", fontSize: 16,
                        }}>
                          <FlagOutlined />
                        </div>
                        <div>
                          <Text strong style={{ fontSize: 15 }}>{okr.objective}</Text>
                          <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                            <Tag style={{ borderRadius: 6 }}>{okr.quarter} {okr.year}</Tag>
                            <Tag style={{ borderRadius: 6, background: "#EEF2FF", border: "none" }}>
                              {typeof okr.owner === 'string' ? okr.owner : okr.owner?.full_name || okr.owner?.name || okr.owner?.username || '--'}
                            </Tag>
                            {okr.project_id && (
                              <Tag style={{ borderRadius: 6, background: "#ECFDF5", border: "none", color: "#059669" }} icon={<LinkOutlined />}>
                                {getProjectName(okr.project_id)}
                              </Tag>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: "center", marginRight: 16 }}>
                      <Progress
                        type="circle"
                        percent={okr.progress}
                        size={56}
                        strokeColor={{ from: "#4F46E5", to: "#7C3AED" }}
                        format={(p) => <span style={{ fontSize: 11, fontWeight: 700 }}>{p}%</span>}
                      />
                    </div>
                  </div>

                  {/* Expanded detail */}
                  {expandedOkr === okr.id && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      style={{ marginTop: 16, borderTop: "1px solid #E2E8F0", paddingTop: 16 }}
                    >
                      {/* KR header + actions */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                        <Text strong style={{ fontSize: 13, color: "#64748B" }}>
                          关键结果 (Key Results) · {(okr.keyResults || []).length} 项
                        </Text>
                        <Space size="small">
                          <Button
                            size="small"
                            type="primary"
                            ghost
                            icon={<RobotOutlined />}
                            loading={aiGenerating[okr.id]}
                            onClick={(e) => { e.stopPropagation(); handleAiGenerateKrs(okr.id); }}
                            disabled={!okr.project_id}
                          >
                            {aiGenerating[okr.id] ? "AI 生成中…" : "AI 生成 KR"}
                          </Button>
                          {!okr.project_id && (
                            <Tooltip title="请先关联项目后再使用 AI 生成">
                              <Text type="secondary" style={{ fontSize: 11 }}>需先关联项目</Text>
                            </Tooltip>
                          )}
                          <Button size="small" type="dashed" icon={<PlusOutlined />}
                            onClick={(e) => { e.stopPropagation(); handleAddKr(okr.id); }}>
                            添加 KR
                          </Button>
                        </Space>
                      </div>

                      {/* KR list */}
                      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        {(okr.keyResults || []).length === 0 ? (
                          <Empty description={
                            <span>
                              暂无 KR · <a onClick={(e) => { e.stopPropagation(); handleAddKr(okr.id); }}>添加第一个 KR</a>
                              {okr.project_id && <> 或 <a onClick={(e) => { e.stopPropagation(); handleAiGenerateKrs(okr.id); }}>让 AI 根据项目自动生成</a></>}
                            </span>
                          } image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : (
                          (okr.keyResults || []).map((kr: KrItem, krIdx: number) => (
                            <KrRow
                              key={kr.id}
                              kr={kr}
                              index={krIdx}
                              onUpdate={(krId, field, value) => handleUpdateKr(okr.id, krId, field, value)}
                              onDelete={(id) => handleDeleteKr(okr.id, id)}
                            />
                          ))
                        )}
                      </div>

                      {/* Bottom actions */}
                      <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                        <Button size="small" icon={<EditOutlined />}
                          onClick={(e) => { e.stopPropagation(); handleEditOkr(okr); }}>编辑</Button>
                        <Button size="small" danger icon={<DeleteOutlined />}
                          onClick={(e) => { e.stopPropagation(); handleDeleteOkr(okr.id); }}>删除</Button>
                      </div>
                    </motion.div>
                  )}
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </AnimatePresence>

      {/* Create/Edit modal */}
      <Modal
        title={editingOkr?.id ? "编辑 OKR" : "新建 OKR"}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditingOkr(null); }}
        footer={null}
        destroyOnClose
        width={560}
      >
        <Form layout="vertical" initialValues={editingOkr || { year: "2026", quarter: "Q3" }} onFinish={handleSaveOkr}>
          <Form.Item label="目标 (Objective)" name="objective" rules={[{ required: true, message: "请输入目标" }]}>
            <Input.TextArea rows={2} placeholder="例如：提升产品用户体验至行业领先水平" />
          </Form.Item>

          <Form.Item label="关联项目" name="project_id" extra="关联项目后可使用 AI 根据项目情况自动生成 KR">
            <Select
              showSearch
              placeholder="选择要关联的项目（可选）"
              allowClear
              optionFilterProp="children"
              filterOption={(input, option) =>
                (option?.children as unknown as string)?.toLowerCase().includes(input.toLowerCase())
              }
              style={{ width: "100%" }}
            >
              {projects.map((p: any) => (
                <Select.Option key={p.id} value={p.id}>{p.name}</Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Space style={{ width: "100%" }} wrap>
            <Form.Item label="年份" name="year" rules={[{ required: true }]}>
              <Select options={["2025", "2026", "2027"].map(y => ({ label: y, value: y }))} style={{ width: 110 }} />
            </Form.Item>
            <Form.Item label="季度" name="quarter" rules={[{ required: true }]}>
              <Select options={QUARTERS.map(q => ({ label: q, value: q }))} style={{ width: 90 }} />
            </Form.Item>
            <Form.Item label="负责人" name="owner">
              <Input placeholder="例如：产品团队 / 张明" style={{ width: 130 }} />
            </Form.Item>
          </Space>

          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              {editingOkr?.id ? "保存" : "创建目标"}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default OKRs;
