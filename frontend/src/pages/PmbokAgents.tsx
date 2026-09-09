import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Card, Typography, Tag, Button, Select, Space, App, Drawer,
  Spin, Alert, List, Input, Form, Modal,
  Row, Col, Tooltip, Divider, Switch, Avatar, Empty,
} from "antd";
import {
  BookOutlined, PlayCircleOutlined, ProjectOutlined, ExperimentOutlined,
  PartitionOutlined, NodeIndexOutlined, SafetyOutlined,
  CompassOutlined, RobotOutlined, EditOutlined,
  DeleteOutlined, SaveOutlined, ThunderboltOutlined,
  CodeOutlined, ToolOutlined, CloudDownloadOutlined, PlusOutlined,
} from "@ant-design/icons";
import { pmbokV3Api } from "../api";
import { agentApi, projectApi } from "../api";
import { useNavigate } from "react-router-dom";
import AgentRunDialog from "../components/AgentRunDialog";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

// ============ 品牌色 ============
const BRAND = { green: "#27ae60", darkGreen: "#16a085", purple: "#6366F1" };

// 过程组 / 知识领域 / 体系 选项
const PG_OPTIONS = ["启动", "规划", "执行", "监控", "收尾"];
const KA_OPTIONS = ["整合", "范围", "进度", "成本", "质量", "资源", "沟通", "风险", "采购", "相关方"];
const SYS_OPTIONS = ["PMBOK", "CPMAI", "TAI", "PMBOKv8"];

// ============ 类型 ============
interface PmbokProcess {
  id: string;
  name_cn: string;
  name_en: string;
  kind: string;
  category: string;
  process_group: string;
  knowledge_area: string;
  summary: string;
  inputs: string[];
  tools: string[];
  outputs: string[];
  v8: string;
}

// V3 Agent 层对象（来自 pmbokV3Api.agents）
interface V3Agent {
  id: string;
  code: string;
  name_cn: string;
  name_en: string;
  process_group: string;
  process_group_en: string;
  knowledge_area: string;
  knowledge_area_en: string;
  system: string;
  system_label: string;
  summary: string;
  v8_note: string;
  itto: { inputs: string[]; tools: string[]; outputs: string[] };
  itto_size: { I: number; T: number; O: number };
  skill_ids: string[];
  skill_count: number;
  principle_ids: string[];
  persona: string;
  system_prompt: string;
  difficulty: string | number;
}

interface AnyAgent {
  id: string;
  name: string;
  name_en?: string;
  description?: string;
  category?: string;
  type?: string;
  icon?: string;
  color?: string;
  inputHint?: string;
  tags?: string[];
  accuracy?: number;
}

// 结构化 ITTO 单项（后端 get_structured_itto 返回）
interface IttoItem {
  skill_ids?: string[]; // 关联的 Skill ID 列表
  key: string;
  label: string;
  optional?: boolean;
  kind?: string;
  template_prompt?: string;
  enabled?: boolean; // 仅工具技术：是否被勾选使用
}
interface PrepareInput extends IttoItem {
  exists: boolean;
  ref?: string | null;
  title?: string | null;
  source?: string | null;
}
interface PrepareResult {
  agent_id: string;
  project_id?: string | null;
  has_project: boolean;
  inputs: PrepareInput[];
  missing_required: string[];
  tools: IttoItem[];
  outputs: IttoItem[];
}

// ============ 结构化 ITTO 条目编辑辅助 ============
const patchItto = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  key: string,
  patch: Partial<IttoItem>,
) => setter((arr) => arr.map((x) => (x.key === key ? { ...x, ...patch } : x)));

const addItto = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  kind: "input" | "tool" | "output",
) =>
  setter((arr) => [
    ...arr,
    {
      key: `${kind}_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e4).toString(36)}`,
      label: "新条目",
      enabled: true,
      ...(kind === "input" ? { optional: false } : {}),
    },
  ]);

const removeItto = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  key: string,
) => setter((arr) => arr.filter((x) => x.key !== key));

// ============ 组件 ============
const PmbokAgents: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();

// 更新 ITTO 项关联的 Skill
const updateIttoSkillIds = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  key: string,
  skillIds: string[],
) => setter((arr) => arr.map((x) => (x.key === key ? { ...x, skill_ids: skillIds } : x)));

  // 顶部项目选择 / 项目列表
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string | undefined>();

  // Agent 网格数据
  const [agents, setAgents] = useState<V3Agent[]>([]);
  const [totalAgents, setTotalAgents] = useState(0);
  const [loading, setLoading] = useState(true);
  // 是否已完成首次加载：首次显示全屏 spinner，后续搜索仅局部提示，避免整页卸载导致输入框失焦
  const [hasLoaded, setHasLoaded] = useState(false);

  // 筛选条件
  const [filterPg, setFilterPg] = useState<string | undefined>();
  const [filterKa, setFilterKa] = useState<string | undefined>();
  const [filterSys, setFilterSys] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const searchInputRef = useRef<any>(null);
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // 派生映射：工作流命中数 / Skill id→name / 原则 id→name
  const [wfCountMap, setWfCountMap] = useState<Record<string, number>>({});
  const [skillMap, setSkillMap] = useState<Record<string, string>>({});
  const [principleMap, setPrincipleMap] = useState<Record<string, string>>({});

  // 角色详情抽屉
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailAgent, setDetailAgent] = useState<V3Agent | null>(null);

  // === Agent 深度编辑器（保留：其它已有区块不动） ===
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<AnyAgent | null>(null);
  const [editOverride, setEditOverride] = useState<any>(null);
  const [, setEditBase] = useState<any>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editForm] = Form.useForm();

  // 结构化 ITTO 编辑态（每项可配 optional / enabled）
  const [ittoInputs, setIttoInputs] = useState<IttoItem[]>([]);
  const [ittoTools, setIttoTools] = useState<IttoItem[]>([]);
  const [ittoOutputs, setIttoOutputs] = useState<IttoItem[]>([]);
  // ITTO 项 Skill 关联选择器
  const [skillSelectOpen, setSkillSelectOpen] = useState(false);
  const [selectedSkillKey, setSelectedSkillKey] = useState<string | null>(null);
  // 统一手动运行对话框（检索 → 工具运用 → Markdown 结果；快慢模式自选）
  const [runDialogAgent, setRunDialogAgent] = useState<{ id: string; name: string; kind: "domain" | "pmbok" } | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);

  // 草稿列表 / 草稿刷新触发
  const [, setDraftTick] = useState(0);

  // 浏览器下载由 AgentRunDialog 内部处理

  // === 一次性加载：工作流（命中数）/ 全部 Skill（id→name）/ 原则（id→name）/ 项目列表 ===
  useEffect(() => {
    (async () => {
      try {
        const [wfRes, skRes, prRes, pjRes] = await Promise.all([
          pmbokV3Api.workflows().catch(() => ({ items: [] })),
          pmbokV3Api.skills().catch(() => ({ items: [] })),
          pmbokV3Api.principles().catch(() => ({ items: [] })),
          projectApi.list({ page: 1, size: 200 }).catch(() => ({ items: [] })),
        ]);

        // 命中工作流数：统计各 workflow.nodes[].ref 含该 agent id 的次数
        const wfs: any[] = wfRes.items || [];
        const wfCount: Record<string, number> = {};
        for (const wf of wfs) {
          const nodes: any[] = wf?.nodes || wf?.steps || [];
          for (const n of nodes) {
            const ref = n?.ref;
            if (!ref) continue;
            wfCount[String(ref)] = (wfCount[String(ref)] || 0) + 1;
          }
        }
        setWfCountMap(wfCount);

        // Skill id → name 映射
        const skMap: Record<string, string> = {};
        for (const s of (skRes.items || [])) {
          skMap[s.id] = s.name_cn || s.name || s.id;
        }
        setSkillMap(skMap);

        // 原则 id → name 映射
        const prMap: Record<string, string> = {};
        for (const p of (prRes.items || [])) {
          prMap[p.id] = p.name_cn || p.name || p.id;
        }
        setPrincipleMap(prMap);

        const arr = (pjRes.items || pjRes.data?.items || []).filter((p: any) => !p.is_deleted);
        setProjects(arr);
      } catch {
        // 失败不崩溃：映射保持空，网格仍可渲染
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // === 防抖搜索：延迟500ms后执行搜索 ===
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 500);
    return () => clearTimeout(timer);
  }, [search]);

  // === 按筛选条件加载 Agent（pmbokV3Api.agents） ===
  useEffect(() => {
    (async () => {
      setLoading(true);
      // 记录抓取前搜索框是否持有焦点，数据到达后恢复，避免DOM替换导致失焦
      const inputEl = searchInputRef.current?.input as HTMLInputElement | undefined;
      const wasFocused = !!(inputEl && document.activeElement === inputEl);
      try {
        const params: any = {};
        if (filterPg) params.process_group = filterPg;
        if (filterKa) params.knowledge_area = filterKa;
        if (filterSys) params.system = filterSys;
        if (debouncedSearch.trim()) params.search = debouncedSearch.trim();
        const res = await pmbokV3Api.agents(params);
        const items: V3Agent[] = res.items || [];
        setAgents(items);
        setTotalAgents(typeof res.total === "number" ? res.total : items.length);
      } catch (e: any) {
        setAgents([]);
        setTotalAgents(0);
        message.error(e?.message || "加载角色库失败");
      } finally {
        setLoading(false);
        setHasLoaded(true);
        if (wasFocused) {
          requestAnimationFrame(() => {
            const el = searchInputRef.current?.input as HTMLInputElement | undefined;
            if (el && document.activeElement !== el) {
              el.focus();
              const len = el.value.length;
              try { el.setSelectionRange(len, len); } catch { /* ignore */ }
            }
          });
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterPg, filterKa, filterSys, debouncedSearch]);

  const handleRun = (a: V3Agent) => {
    setRunDialogAgent({ id: a.id, name: a.name_cn, kind: "domain" });
    setRunDialogOpen(true);
  };

  const openDetail = (a: V3Agent) => {
    setDetailAgent(a);
    setDetailOpen(true);
  };

  // V3 Agent → AnyAgent（供深度编辑器复用）
  const toAnyAgent = (a: V3Agent): AnyAgent => ({
    id: a.id,
    name: a.name_cn,
    name_en: a.name_en,
    description: a.summary,
    category: a.process_group,
    type: a.knowledge_area,
    icon: "RobotOutlined",
    color: BRAND.green,
    inputHint: "",
    tags: [],
  });

  // ============ 深度编辑器逻辑（保留） ============
  const openEditor = async (agent: AnyAgent | PmbokProcess, kind: "domain" | "pmbok") => {
    const id = (agent as any).id;
    const baseAgent: AnyAgent = {
      id,
      name: kind === "domain"
        ? (agent as AnyAgent).name
        : (agent as PmbokProcess).name_cn,
      name_en: (agent as any).name_en,
      description: kind === "domain"
        ? (agent as AnyAgent).description
        : (agent as PmbokProcess).summary,
      category: kind === "domain"
        ? (agent as AnyAgent).category
        : (agent as PmbokProcess).category,
      type: kind === "domain"
        ? (agent as AnyAgent).type
        : (agent as PmbokProcess).knowledge_area,
      icon: (agent as any).icon || "RobotOutlined",
      color: (agent as any).color || BRAND.purple,
      inputHint: (agent as any).inputHint || (agent as any).input_hint || "",
      tags: (agent as any).tags || [],
    };

    setEditing(baseAgent);
    setEditOverride(null);
    setEditBase(null);
    setEditOpen(true);
    setEditLoading(true);
    try {
      const res = await agentApi.getOverride(id);
      setEditOverride(res.override || {});
      setEditBase(res.base || null);
      const ov = res.override || {};
      const base = res.base || {};
      
      // 优先从 slots API 加载 ITTO（PMBOK Agent 标准数据）
      if (kind === "pmbok") {
        try {
          const slotsRes = await pmbokV3Api.slots(id);
          const slots = slotsRes || {};
          const formatSlot = (items: any[]) => items.map((it: any) => ({
            label: it.label || it.name || it.key,
            optional: it.optional || false,
          }));
          setIttoInputs(formatSlot(slots.inputs || []));
          setIttoTools(formatSlot(slots.tools || []));
          setIttoOutputs(formatSlot(slots.outputs || []));
        } catch (slotErr) {
          // Fallback to override/base data
          setIttoInputs(ov.inputs_struct ?? base.inputs_struct ?? []);
          setIttoTools(ov.tools_struct ?? base.tools_struct ?? []);
          setIttoOutputs(ov.outputs_struct ?? base.outputs_struct ?? []);
        }
      } else {
        setIttoInputs(ov.inputs_struct ?? base.inputs_struct ?? []);
        setIttoTools(ov.tools_struct ?? base.tools_struct ?? []);
        setIttoOutputs(ov.outputs_struct ?? base.outputs_struct ?? []);
      }


      const draftKey = `agent_override_draft_${id}`;
      let draft: any = {};
      try { draft = JSON.parse(localStorage.getItem(draftKey) || "{}"); } catch {}

      const cur = {
        name: res.override?.name ?? baseAgent.name ?? "",
        description: res.override?.description ?? baseAgent.description ?? "",
        input_hint: res.override?.input_hint ?? baseAgent.inputHint ?? "",
        inputs: res.override?.inputs ?? (agent as any).inputs ?? [],
        tools: res.override?.tools ?? (agent as any).tools ?? [],
        outputs: res.override?.outputs ?? (agent as any).outputs ?? [],
        process: res.override?.process ?? (kind === "pmbok" ? (agent as PmbokProcess).v8 : "") ?? "",
        system_prompt: res.override?.system_prompt ?? "",
        note: draft.note || res.override?.note || "",
      };

      editForm.setFieldsValue({
        name: cur.name,
        description: cur.description,
        input_hint: cur.input_hint,
        process: cur.process || "",
        system_prompt: cur.system_prompt || "",
        note: cur.note || "",
      });
    } catch (e: any) {
      message.error(e?.message || "读取 Agent 配置失败");
    } finally {
      setEditLoading(false);
    }
  };

  const saveOverride = async () => {
    if (!editing) return;
    try {
      const v = await editForm.validateFields();
      setEditSaving(true);
      const payload = {
        name: v.name,
        description: v.description,
        input_hint: v.input_hint,
        inputs_struct: ittoInputs,
        tools_struct: ittoTools,
        outputs_struct: ittoOutputs,
        inputs: ittoInputs.map((i) => i.label).filter(Boolean),
        tools: ittoTools.map((t) => t.label).filter(Boolean),
        outputs: ittoOutputs.map((o) => o.label).filter(Boolean),
        process: v.process,
        system_prompt: v.system_prompt,
        note: v.note
      };
      const res = await agentApi.putOverride(editing.id, payload);
      try { localStorage.setItem(`agent_override_draft_${editing.id}`, JSON.stringify({ note: v.note })); } catch {}
      message.success(`已保存 ${editing.name} 的个性化覆盖（${res.saved_at}）`);
      setDraftTick(t => t + 1);
    } catch (e: any) {
      if (e?.errorFields) {
        message.warning("请补齐必填字段");
      } else {
        message.error(e?.message || "保存失败");
      }
    } finally {
      setEditSaving(false);
    }
  };

  const resetOverride = async () => {
    if (!editing) return;
    Modal.confirm({
      title: "恢复内置默认值",
      content: `将删除 "${editing.name}" 的所有个性化覆盖，恢复为内置"完整可用"版本。继续吗？`,
      okType: "danger",
      onOk: async () => {
        try {
          await agentApi.deleteOverride(editing.id);
          try { localStorage.removeItem(`agent_override_draft_${editing.id}`); } catch {}
          message.success("已恢复内置默认值");
          setEditOpen(false);
        } catch (e: any) {
          message.error(e?.message || "恢复失败");
        }
      },
    });
  };

  // ============ 统一渲染一组 ITTO（深度编辑器用） ============
  const renderIttoCol = (
    kind: "input" | "tool" | "output",
    titleNode: React.ReactNode,
    desc: string,
    items: IttoItem[],
    setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  ) => (
    <Col span={8}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Text strong>{titleNode}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          已选用 {items.filter((i) => i.enabled !== false).length}/{items.length}
        </Text>
      </div>
      <Paragraph type="secondary" style={{ fontSize: 12, margin: "4px 0" }}>{desc}</Paragraph>
      <Space direction="vertical" style={{ width: "100%" }} size={6}>
        {items.length === 0 && <Text type="secondary">无</Text>}
        {items.map((it) => (
            <div
            key={it.key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              opacity: it.enabled === false ? 0.5 : 1,
              background: "#FAFAFA",
              borderRadius: 6,
              padding: "4px 6px",
            }}
          >
            <Tooltip title="选用：关闭则该项不参与物料运行">
              <Switch
                size="small"
                checked={it.enabled !== false}
                onChange={(v) => patchItto(setter, it.key, { enabled: v })}
              />
            </Tooltip>
            <Input
              size="small"
              value={it.label}
              onChange={(e) => patchItto(setter, it.key, { label: e.target.value })}
              style={{ flex: 1 }}
              placeholder="条目名称"
            />
            {kind === "input" && (
              <Tooltip title="关闭=必需（缺失则阻塞运行）；开启=可选">
                <Space size={2}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{it.optional ? "可选" : "必需"}</Text>
                  <Switch
                    size="small"
                    checked={!!it.optional}
                    onChange={(v) => patchItto(setter, it.key, { optional: v })}
                  />
                </Space>
              </Tooltip>
            )}
            <Tooltip title="关联 Skill（全部可选，来自 Skill 库）">
              <Button
                size="small"
                type="text"
                icon={<ToolOutlined />}
                style={{ color: "#27ae60", padding: "0 4px" }}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedSkillKey(it.key);
                  setSkillSelectOpen(prev => !prev);
                }}
              />
            </Tooltip>
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              onClick={() => removeItto(setter, it.key)}
            />
          {skillSelectOpen && selectedSkillKey === it.key && (
            <div style={{ position: "absolute", zIndex: 1000, background: "#fff", border: "1px solid #D9D9D9", borderRadius: 6, padding: 8, minWidth: 220, boxShadow: "0 4px 12px rgba(0,0,0,0.15)", marginTop: 4 }}>
              <Text strong style={{ fontSize: 12, display: "block", marginBottom: 6 }}>关联 Skill（全部可选）</Text>
              <div style={{ maxHeight: 200, overflowY: "auto" }}>
                {Object.entries(skillMap).map(([sid, sname]) => {
                  const current = it.skill_ids || [];
                  const checked = current.includes(sid);
                  return (
                    <div
                      key={sid}
                      onClick={(e) => {
                        e.stopPropagation();
                        const next = checked
                          ? current.filter(x => x !== sid)
                          : [...current, sid];
                        updateIttoSkillIds(setter, it.key, next);
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "4px 6px",
                        borderRadius: 4,
                        cursor: "pointer",
                        background: checked ? "#F0FFF4" : "transparent",
                      }}
                    >
                      <span style={{ fontSize: 11, color: checked ? "#27ae60" : "#ccc", width: 16 }}>{checked ? "✓" : ""}</span>
                      <Text style={{ fontSize: 12 }}>{sname || sid}</Text>
                    </div>
                  );
                })}
              </div>
              <Button size="small" type="text" style={{ float: "right", marginTop: 4 }} onClick={(e) => { e.stopPropagation(); setSkillSelectOpen(false); }}>关闭</Button>
              <div style={{ clear: "both" }} />
            </div>
          )}
          </div>
        ))}
      </Space>
      <Button
        size="small"
        type="dashed"
        block
        icon={<PlusOutlined />}
        style={{ marginTop: 8 }}
        onClick={() => addItto(setter, kind)}
      >新增条目</Button>
    </Col>
  );

  // ITTO 文本列表渲染（详情抽屉用）
  const renderItList = (items: string[] | undefined) =>
    items && items.length ? (
      <List
        size="small"
        dataSource={items}
        renderItem={(x) => (
          <List.Item style={{ padding: "3px 0", border: "none" }}>
            <Text style={{ fontSize: 12 }}>• {x}</Text>
          </List.Item>
        )}
      />
    ) : <Text type="secondary" style={{ fontSize: 12 }}>—</Text>;

  if (loading && !hasLoaded) {
    return <div style={{ padding: 48, textAlign: "center" }}><Spin /><p style={{ marginTop: 12 }}>加载角色库…</p></div>;
  }

  return (
    <div style={{ padding: 8 }}>
      {/* 顶部：标题 + 项目选择（保留） */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <BookOutlined style={{ marginRight: 8, color: BRAND.green }} />
            PMBOK 智能角色库
          </Title>
          <Text type="secondary">
            每个 Agent 都是一位虚拟项目经理，整合若干 Skill 与一条工作流。
          </Text>
        </div>
        <Space>
          <Select
            style={{ width: 240 }}
            placeholder="选择目标项目（可选）"
            allowClear
            value={projectId}
            onChange={setProjectId}
            options={projects.map((p: any) => ({ value: p.id, label: p.name }))}
          />
          {projectId && (
            <Button icon={<ProjectOutlined />} onClick={() => navigate(`/projects/${projectId}`)}>
              打开项目
            </Button>
          )}
        </Space>
      </div>

      {/* 筛选条 */}
      <Card size="small" style={{ marginBottom: 16, borderRadius: 12 }} bodyStyle={{ padding: 12 }}>
        <Space wrap size={12} style={{ width: "100%", justifyContent: "space-between" }}>
          <Space wrap size={8}>
            <Select
              allowClear
              placeholder="过程组"
              style={{ width: 130 }}
              value={filterPg}
              onChange={setFilterPg}
              options={PG_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
            <Select
              allowClear
              placeholder="知识领域"
              style={{ width: 140 }}
              value={filterKa}
              onChange={setFilterKa}
              options={KA_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
            <Select
              allowClear
              placeholder="体系"
              style={{ width: 140 }}
              value={filterSys}
              onChange={setFilterSys}
              options={SYS_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
            <Input.Search
              ref={searchInputRef}
              allowClear
              placeholder="搜索名称 / 编码 / 摘要"
              style={{ width: 240 }}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={(v) => setSearch(v)}
            />
          </Space>
          <Space size={6}>
            {loading && hasLoaded && <Spin size="small" />}
            <Text type="secondary">共 {totalAgents} 个角色</Text>
          </Space>
        </Space>
      </Card>

      {/* Agent 角色卡片网格 */}
      {agents.length === 0 ? (
        <Empty description="未找到匹配的角色" style={{ padding: 48 }} />
      ) : (
        <Row gutter={[16, 16]}>
          {agents.map((a) => (
            <Col key={a.id} xs={24} sm={12} md={8} lg={8} xl={6}>
              <Card
                hoverable
                style={{ borderRadius: 12, height: "100%", borderTop: `3px solid ${BRAND.green}` }}
                onClick={() => openDetail(a)}
                title={
                  <Space align="center" style={{ width: "100%" }}>
                    <Avatar style={{ background: BRAND.green, flexShrink: 0 }} icon={<RobotOutlined />} />
                    <div style={{ overflow: "hidden" }}>
                      <div style={{ fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {a.name_cn}
                      </div>
                      <div style={{ fontSize: 11, color: "#8c8c8c", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {a.code} · {a.name_en}
                      </div>
                    </div>
                  </Space>
                }
              >
                <Space wrap size={4} style={{ marginBottom: 8 }}>
                  <Tag color="purple">{a.process_group}</Tag>
                  <Tag color="blue">{a.knowledge_area}</Tag>
                  <Tag color="green">{a.system_label || a.system}</Tag>
                </Space>
                <Paragraph
                  type="secondary"
                  style={{ fontSize: 12, marginBottom: 10, minHeight: 36 }}
                  ellipsis={{ rows: 2 }}
                >
                  {a.summary || "—"}
                </Paragraph>
                <Space size={16} style={{ marginBottom: 10 }}>
                  <Tooltip title="调度 Skill 数">
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <ToolOutlined style={{ color: BRAND.darkGreen }} /> {a.skill_count ?? a.skill_ids?.length ?? 0} Skill
                    </Text>
                  </Tooltip>
                  <Tooltip title="命中工作流数">
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <NodeIndexOutlined style={{ color: BRAND.purple }} /> {wfCountMap[a.id] || 0} 工作流
                    </Text>
                  </Tooltip>
                </Space>
                <Button
                  type="primary"
                  block
                  icon={<PlayCircleOutlined />}
                  onClick={(e) => { e.stopPropagation(); handleRun(a); }}
                >
                  试运行
                </Button>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* ============ 角色详情 Drawer ============ */}
      <Drawer
        title={
          <Space>
            <RobotOutlined style={{ color: BRAND.green }} />
            <span>角色详情 · {detailAgent?.name_cn || ""}</span>
            {detailAgent && <Tag color="purple" style={{ marginLeft: 4 }}>{detailAgent.code}</Tag>}
          </Space>
        }
        placement="right"
        width={720}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        destroyOnClose
        footer={
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Button onClick={() => setDetailOpen(false)}>关闭</Button>
            <Space>
              <Button
                icon={<PlayCircleOutlined />}
                onClick={() => { if (detailAgent) { setDetailOpen(false); handleRun(detailAgent); } }}
              >
                试运行
              </Button>
              <Button
                type="primary"
                icon={<EditOutlined />}
                onClick={() => { if (detailAgent) { setDetailOpen(false); openEditor(toAnyAgent(detailAgent), "domain"); } }}
              >
                深度编辑
              </Button>
            </Space>
          </Space>
        }
      >
        {detailAgent && (
          <>
            <Space wrap style={{ marginBottom: 12 }}>
              <Tag color="purple">{detailAgent.process_group}</Tag>
              <Tag color="blue">{detailAgent.knowledge_area}</Tag>
              <Tag color="green">{detailAgent.system_label || detailAgent.system}</Tag>
              {detailAgent.difficulty != null && detailAgent.difficulty !== "" && (
                <Tag>{detailAgent.difficulty}</Tag>
              )}
            </Space>

            <Paragraph>{detailAgent.summary || "—"}</Paragraph>

            {detailAgent.v8_note && (
              <Alert type="info" showIcon message={detailAgent.v8_note} style={{ marginBottom: 12 }} />
            )}

            {/* ITTO 三段 */}
            <Card type="inner" size="small" title={<><NodeIndexOutlined /> 输入 / 工具 / 输出（ITTO）</>} style={{ marginBottom: 12 }}>
              <Row gutter={12}>
                <Col span={8}>
                  <Text strong style={{ fontSize: 12 }}><PartitionOutlined /> 输入</Text>
                  <div style={{ marginTop: 4 }}>{renderItList(detailAgent.itto?.inputs)}</div>
                </Col>
                <Col span={8}>
                  <Text strong style={{ fontSize: 12 }}><ExperimentOutlined /> 工具 / 技术</Text>
                  <div style={{ marginTop: 4 }}>{renderItList(detailAgent.itto?.tools)}</div>
                </Col>
                <Col span={8}>
                  <Text strong style={{ fontSize: 12 }}><PartitionOutlined /> 输出</Text>
                  <div style={{ marginTop: 4 }}>{renderItList(detailAgent.itto?.outputs)}</div>
                </Col>
              </Row>
            </Card>

            {/* 调度 Skill 列表 */}
            <Card type="inner" size="small" title={<><ToolOutlined /> 调度 Skill（{detailAgent.skill_ids?.length || 0}）</>} style={{ marginBottom: 12 }}>
              {detailAgent.skill_ids && detailAgent.skill_ids.length ? (
                <Space wrap size={4}>
                  {detailAgent.skill_ids.map((sid) => (
                    <Tag key={sid} color="geekblue">{skillMap[sid] || sid}</Tag>
                  ))}
                </Space>
              ) : <Text type="secondary">—</Text>}
            </Card>

            {/* 注入原则 */}
            <Card type="inner" size="small" title={<><SafetyOutlined /> 注入原则（{detailAgent.principle_ids?.length || 0}）</>} style={{ marginBottom: 12 }}>
              {detailAgent.principle_ids && detailAgent.principle_ids.length ? (
                <Space wrap size={4}>
                  {detailAgent.principle_ids.map((pid) => (
                    <Tag key={pid} color="purple">{principleMap[pid] || pid}</Tag>
                  ))}
                </Space>
              ) : <Text type="secondary">—</Text>}
            </Card>

            {/* Persona / System Prompt 摘要 */}
            <Card type="inner" size="small" title={<><CompassOutlined /> Persona / System Prompt</>} style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 12 }}>Persona</Text>
              <Paragraph style={{ fontSize: 12, whiteSpace: "pre-wrap", marginTop: 4 }}>
                {detailAgent.persona || "—"}
              </Paragraph>
              <Divider style={{ margin: "10px 0" }} />
              <Text strong style={{ fontSize: 12 }}>System Prompt</Text>
              <Paragraph style={{ fontSize: 12, whiteSpace: "pre-wrap", marginTop: 4 }}>
                {detailAgent.system_prompt || "—"}
              </Paragraph>
            </Card>
          </>
        )}
      </Drawer>

      {/* ============ Agent 深度编辑 Drawer（保留） ============ */}
      <Drawer
        title={
          <Space>
            <EditOutlined style={{ color: BRAND.purple }} />
            <span>深度编辑 · {editing?.name || ""}</span>
            {editing && (
              <Tag color="purple" style={{ marginLeft: 4 }}>{editing.id}</Tag>
            )}
          </Space>
        }
        placement="right"
        width={680}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        destroyOnClose
        footer={
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Space>
                <Tooltip title="运行此 Agent（检索输入 → 运用工具技术 → 输出 Markdown 结果）">
                  <Button
                    icon={<CloudDownloadOutlined />}
                    onClick={() => { setEditOpen(false); if (editing) { setRunDialogAgent({ id: editing.id, name: editing.name, kind: "domain" }); setRunDialogOpen(true); } }}
                  >
                    运行
                  </Button>
                </Tooltip>
              <Tooltip title="删除覆盖文件，恢复为内置默认（完整可用）">
                <Button danger icon={<DeleteOutlined />} onClick={resetOverride}>
                  恢复默认
                </Button>
              </Tooltip>
            </Space>
            <Space>
              <Button onClick={() => setEditOpen(false)}>关闭</Button>
              <Button type="primary" icon={<SaveOutlined />} loading={editSaving} onClick={saveOverride}>
                保存覆盖
              </Button>
            </Space>
          </Space>
        }
      >
        {editLoading ? (
          <div style={{ padding: 48, textAlign: "center" }}><Spin /></div>
        ) : (
          <>
            <Alert
              type="info"
              showIcon
              message="每个 Agent 默认完整可用"
              description={
                <span>
                  编辑修改输入 / 工具 / 输出 / 过程 / 系统提示词后，会以"覆盖"形式持久化到
                  <code style={{ padding: "0 4px" }}>backend/data/agent_overrides.json</code>，
                  不影响内置默认；可点底部「恢复默认」清空。
                </span>
              }
              style={{ marginBottom: 16 }}
            />

            {/* 基础信息 */}
            <Card type="inner" size="small" title={<><CodeOutlined /> 基础信息</>} style={{ marginBottom: 12 }}>
              <Form form={editForm} layout="vertical">
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label="Agent 名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
                      <Input prefix={<RobotOutlined />} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label="输入提示" name="input_hint" tooltip="用户在『运行』面板填写的输入字段说明">
                      <Input placeholder="例：项目 ID / 时间范围 / 风险关键词" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="描述" name="description">
                  <TextArea autoSize={{ minRows: 2, maxRows: 4 }} placeholder="Agent 用途的一句话总结" />
                </Form.Item>
              </Form>
            </Card>

            {/* ITTO（结构化 · 可配置） */}
            <Card
              type="inner"
              size="small"
              title={<><NodeIndexOutlined /> 输入 / 工具 / 输出（ITTO · 逐项选用 / 编辑）</>}
              style={{ marginBottom: 12 }}
              extra={<Text type="secondary" style={{ fontSize: 12 }}>每项可开关选用、编辑标签、增删</Text>}
            >
              <Row gutter={16}>
                {renderIttoCol(
                  "input",
                  <><NodeIndexOutlined /> 输入（材料）</>,
                  "每项可「选用」；勾选「可选」则该输入缺失也不阻塞运行（默认必需）。",
                  ittoInputs,
                  setIttoInputs,
                )}
                {renderIttoCol(
                  "tool",
                  <><ToolOutlined /> 工具 / 技术</>,
                  "勾选要参与本次信息处理的工具技术（默认全选）。",
                  ittoTools,
                  setIttoTools,
                )}
                {renderIttoCol(
                  "output",
                  <><PartitionOutlined /> 输出（指定文件）</>,
                  "勾选需在运行时由 AI 生成并落盘的输出文件。",
                  ittoOutputs,
                  setIttoOutputs,
                )}
              </Row>
            </Card>

            {/* 过程展示 */}
            <Card type="inner" size="small" title={<><ExperimentOutlined /> 过程展示</>} style={{ marginBottom: 12 }}>
              <Form form={editForm} layout="vertical">
                <Form.Item
                  label="过程步骤 / PMBOK v8 对应说明"
                  name="process"
                  tooltip="Agent 实际执行的过程说明，或 PMBOK 第 8 版对应的描述"
                >
                  <TextArea autoSize={{ minRows: 3, maxRows: 8 }} placeholder="例：按照 PMBOK 第 8 版『规划』绩效域的『工作计划』原则 → 1. 启动 → 2. 分析 …" />
                </Form.Item>
              </Form>
            </Card>


            {/* 高级 system_prompt */}
            <Card type="inner" size="small" title={<><ThunderboltOutlined /> 高级 · System Prompt（可选）</>} style={{ marginBottom: 12 }}>
              <Form form={editForm} layout="vertical">
                <Form.Item
                  label="完整 system_prompt（覆盖后会拼接到 Agent 默认 prompt 之后）"
                  name="system_prompt"
                  tooltip="留空表示使用内置默认。"
                >
                  <TextArea
                    autoSize={{ minRows: 4, maxRows: 12 }}
                    placeholder={`例：\n你是「${editing?.name || '某Agent'}」专家。请基于项目上下文输出结构化建议，使用 Markdown 格式，按以下结构：\n- 结论\n- 输入依据\n- 风险与建议`}
                    style={{ fontFamily: "monospace", fontSize: 12 }}
                  />
                </Form.Item>
                <Form.Item label="本次编辑说明（仅本地草稿，不会上传）" name="note">
                  <Input placeholder="例：根据复盘调整输出格式" />
                </Form.Item>
              </Form>
            </Card>

            <Divider />
            <Text type="secondary" style={{ fontSize: 12 }}>
              已覆盖次数：{editOverride?.updated_at ? 1 : 0}（{editOverride?.updated_at || "尚未保存"} · {editOverride?.updated_by || "—"}）
            </Text>
          </>
        )}
      </Drawer>

      {/* ============ 统一手动运行对话框 ============ */}
      <AgentRunDialog
        open={runDialogOpen}
        onClose={() => setRunDialogOpen(false)}
        agent={runDialogAgent}
        projectId={projectId}
        projects={projects}
      />
    </div>
  );
};

export default PmbokAgents;
