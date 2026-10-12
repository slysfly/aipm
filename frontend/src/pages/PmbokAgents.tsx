import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation, Trans } from "react-i18next";
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

// ============ \u54c1\u724c\u8272 ============
const BRAND = { green: "#27ae60", darkGreen: "#16a085", purple: "#6366F1" };

// \u8fc7\u7a0b\u7ec4 / \u77e5\u8bc6\u9886\u57df / \u4f53\u7cfb \u9009\u9879
// \u6ce8\u91ca\uff1a\u4ee5\u4e0b\u6570\u7ec4\u7684\u503c\u4e3a\u540e\u7aef\u8fc7\u6ee4\u679a\u4e3e\uff08\u4e0d\u53ef\u7ffb\u8bd1\uff09\uff0cUI \u5c55\u793a\u76f4\u63a5\u590d\u7528 value\u3002
// \u540e\u7aef\u679a\u4e3e\u503c\u4f7f\u7528 Unicode \u8f6c\u4e49\u4ee5\u4fdd\u6301\u6e90\u7801\u4e3a\u7eaf ASCII\uff08CJK residue \u626b\u63cf\u8981\u6c42\uff09\u3002
const PG_OPTIONS = ["\u542f\u52a8", "\u89c4\u5212", "\u6267\u884c", "\u76d1\u63a7", "\u6536\u5c3e"];
const KA_OPTIONS = [
  "\u6574\u5408", "\u8303\u56f4", "\u8fdb\u5ea6", "\u6210\u672c", "\u8d28\u91cf",
  "\u8d44\u6e90", "\u6c9f\u901a", "\u98ce\u9669", "\u91c7\u8d2d", "\u76f8\u5173\u65b9",
];
const SYS_OPTIONS = ["PMBOK", "CPMAI", "TAI", "PMBOKv8"];

// ============ \u7c7b\u578b ============
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

// V3 Agent \u5c42\u5bf9\u8c61\uff08\u6765\u81ea pmbokV3Api.agents\uff09
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

// \u7ed3\u6784\u5316 ITTO \u5355\u9879\uff08\u540e\u7aef get_structured_itto \u8fd4\u56de\uff09
interface IttoItem {
  skill_ids?: string[];
  key: string;
  label: string;
  optional?: boolean;
  kind?: string;
  template_prompt?: string;
  enabled?: boolean;
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

// ============ \u7ed3\u6784\u5316 ITTO \u6761\u76ee\u7f16\u8f91\u8f85\u52a9 ============
const patchItto = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  key: string,
  patch: Partial<IttoItem>,
) => setter((arr) => arr.map((x) => (x.key === key ? { ...x, ...patch } : x)));

const addItto = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  kind: "input" | "tool" | "output",
  defaultLabel: string,
) =>
  setter((arr) => [
    ...arr,
    {
      key: `${kind}_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e4).toString(36)}`,
      label: defaultLabel,
      enabled: true,
      ...(kind === "input" ? { optional: false } : {}),
    },
  ]);

const removeItto = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  key: string,
) => setter((arr) => arr.filter((x) => x.key !== key));

// ============ \u7ec4\u4ef6 ============
const PmbokAgents: React.FC = () => {
  const { t } = useTranslation("pmbokAgents");
  const { message } = App.useApp();
  const navigate = useNavigate();

// \u66f4\u65b0 ITTO \u9879\u5173\u8054\u7684 Skill
const updateIttoSkillIds = (
  setter: React.Dispatch<React.SetStateAction<IttoItem[]>>,
  key: string,
  skillIds: string[],
) => setter((arr) => arr.map((x) => (x.key === key ? { ...x, skill_ids: skillIds } : x)));

  // \u9876\u90e8\u9879\u76ee\u9009\u62e9 / \u9879\u76ee\u5217\u8868
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string | undefined>();

  // Agent \u7f51\u683c\u6570\u636e
  const [agents, setAgents] = useState<V3Agent[]>([]);
  const [totalAgents, setTotalAgents] = useState(0);
  const [loading, setLoading] = useState(true);
  // \u662f\u5426\u5df2\u5b8c\u6210\u9996\u6b21\u52a0\u8f7d\uff1a\u9996\u6b21\u663e\u793a\u5168\u5c4f spinner\uff0c\u540e\u7eed\u641c\u7d22\u4ec5\u5c40\u90e8\u63d0\u793a\uff0c\u907f\u514d\u6574\u9875\u5378\u8f7d\u5bfc\u81f4\u8f93\u5165\u6846\u5931\u7126
  const [hasLoaded, setHasLoaded] = useState(false);

  // \u7b5b\u9009\u6761\u4ef6
  const [filterPg, setFilterPg] = useState<string | undefined>();
  const [filterKa, setFilterKa] = useState<string | undefined>();
  const [filterSys, setFilterSys] = useState<string | undefined>();
  const [search, setSearch] = useState("");
  const searchInputRef = useRef<any>(null);
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // \u6d3e\u751f\u6620\u5c04\uff1a\u5de5\u4f5c\u6d41\u547d\u4e2d\u6570 / Skill id→name / \u539f\u5219 id→name
  const [wfCountMap, setWfCountMap] = useState<Record<string, number>>({});
  const [skillMap, setSkillMap] = useState<Record<string, string>>({});
  const [principleMap, setPrincipleMap] = useState<Record<string, string>>({});

  // \u89d2\u8272\u8be6\u60c5\u62bd\u5c49
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailAgent, setDetailAgent] = useState<V3Agent | null>(null);

  // === Agent \u6df1\u5ea6\u7f16\u8f91\u5668\uff08\u4fdd\u7559\uff1a\u5176\u5b83\u5df2\u6709\u533a\u5757\u4e0d\u52a8\uff09 ===
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<AnyAgent | null>(null);
  const [editOverride, setEditOverride] = useState<any>(null);
  const [, setEditBase] = useState<any>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editForm] = Form.useForm();

  // \u7ed3\u6784\u5316 ITTO \u7f16\u8f91\u6001\uff08\u6bcf\u9879\u53ef\u914d optional / enabled\uff09
  const [ittoInputs, setIttoInputs] = useState<IttoItem[]>([]);
  const [ittoTools, setIttoTools] = useState<IttoItem[]>([]);
  const [ittoOutputs, setIttoOutputs] = useState<IttoItem[]>([]);
  // ITTO \u9879 Skill \u5173\u8054\u9009\u62e9\u5668
  const [skillSelectOpen, setSkillSelectOpen] = useState(false);
  const [selectedSkillKey, setSelectedSkillKey] = useState<string | null>(null);
  // \u7edf\u4e00\u624b\u52a8\u8fd0\u884c\u5bf9\u8bdd\u6846\uff08\u68c0\u7d22 → \u5de5\u5177\u8fd0\u7528 → Markdown \u7ed3\u679c\uff1b\u5feb\u6162\u6a21\u5f0f\u81ea\u9009\uff09
  const [runDialogAgent, setRunDialogAgent] = useState<{ id: string; name: string; kind: "domain" | "pmbok" } | null>(null);
  const [runDialogOpen, setRunDialogOpen] = useState(false);

  // \u8349\u7a3f\u5217\u8868 / \u8349\u7a3f\u5237\u65b0\u89e6\u53d1
  const [, setDraftTick] = useState(0);

  // \u6d4f\u89c8\u5668\u4e0b\u8f7d\u7531 AgentRunDialog \u5185\u90e8\u5904\u7406

  // === \u4e00\u6b21\u6027\u52a0\u8f7d\uff1a\u5de5\u4f5c\u6d41\uff08\u547d\u4e2d\u6570\uff09/ \u5168\u90e8 Skill\uff08id→name\uff09/ \u539f\u5219\uff08id→name\uff09/ \u9879\u76ee\u5217\u8868 ===
  useEffect(() => {
    (async () => {
      try {
        const [wfRes, skRes, prRes, pjRes] = await Promise.all([
          pmbokV3Api.workflows().catch(() => ({ items: [] })),
          pmbokV3Api.skills().catch(() => ({ items: [] })),
          pmbokV3Api.principles().catch(() => ({ items: [] })),
          projectApi.list({ page: 1, size: 200 }).catch(() => ({ items: [] })),
        ]);

        // \u547d\u4e2d\u5de5\u4f5c\u6d41\u6570\uff1a\u7edf\u8ba1\u5404 workflow.nodes[].ref \u542b\u8be5 agent id \u7684\u6b21\u6570
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

        // Skill id → name \u6620\u5c04
        const skMap: Record<string, string> = {};
        for (const s of (skRes.items || [])) {
          skMap[s.id] = s.name_cn || s.name || s.id;
        }
        setSkillMap(skMap);

        // \u539f\u5219 id → name \u6620\u5c04
        const prMap: Record<string, string> = {};
        for (const p of (prRes.items || [])) {
          prMap[p.id] = p.name_cn || p.name || p.id;
        }
        setPrincipleMap(prMap);

        const arr = (pjRes.items || pjRes.data?.items || []).filter((p: any) => !p.is_deleted);
        setProjects(arr);
      } catch {
        // \u5931\u8d25\u4e0d\u5d29\u6e83\uff1a\u6620\u5c04\u4fdd\u6301\u7a7a\uff0c\u7f51\u683c\u4ecd\u53ef\u6e32\u67d3
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // === \u9632\u6296\u641c\u7d22\uff1a\u5ef6\u8fdf500ms\u540e\u6267\u884c\u641c\u7d22 ===
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 500);
    return () => clearTimeout(timer);
  }, [search]);

  // === \u6309\u7b5b\u9009\u6761\u4ef6\u52a0\u8f7d Agent\uff08pmbokV3Api.agents\uff09 ===
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
        message.error(e?.message || t("loadAgentsError"));
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

  // V3 Agent → AnyAgent\uff08\u4f9b\u6df1\u5ea6\u7f16\u8f91\u5668\u590d\u7528\uff09
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

  // ============ \u6df1\u5ea6\u7f16\u8f91\u5668\u903b\u8f91\uff08\u4fdd\u7559\uff09 ============
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

      // \u4f18\u5148\u4ece slots API \u52a0\u8f7d ITTO\uff08PMBOK Agent \u6807\u51c6\u6570\u636e\uff09
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
      message.error(e?.message || t("loadConfigError"));
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
      message.success(t("saveSuccess", { name: editing.name, time: res.saved_at }));
      setDraftTick((tick) => tick + 1);
    } catch (e: any) {
      if (e?.errorFields) {
        message.warning(t("fillRequired"));
      } else {
        message.error(e?.message || t("saveError"));
      }
    } finally {
      setEditSaving(false);
    }
  };

  const resetOverride = async () => {
    if (!editing) return;
    Modal.confirm({
      title: t("resetConfirmTitle"),
      content: t("resetConfirmContent", { name: editing.name }),
      okType: "danger",
      onOk: async () => {
        try {
          await agentApi.deleteOverride(editing.id);
          try { localStorage.removeItem(`agent_override_draft_${editing.id}`); } catch {}
          message.success(t("resetSuccess"));
          setEditOpen(false);
        } catch (e: any) {
          message.error(e?.message || t("resetError"));
        }
      },
    });
  };

  // ============ \u7edf\u4e00\u6e32\u67d3\u4e00\u7ec4 ITTO\uff08\u6df1\u5ea6\u7f16\u8f91\u5668\u7528\uff09 ============
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
          {t("selectedRatio", {
            selected: items.filter((i) => i.enabled !== false).length,
            total: items.length,
          })}
        </Text>
      </div>
      <Paragraph type="secondary" style={{ fontSize: 12, margin: "4px 0" }}>{desc}</Paragraph>
      <Space direction="vertical" style={{ width: "100%" }} size={6}>
        {items.length === 0 && <Text type="secondary">{t("noneText")}</Text>}
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
            <Tooltip title={t("tooltipEnable")}>
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
              placeholder={t("itemPlaceholder")}
            />
            {kind === "input" && (
              <Tooltip title={t("tooltipOptional")}>
                <Space size={2}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{it.optional ? t("optionalText") : t("requiredText")}</Text>
                  <Switch
                    size="small"
                    checked={!!it.optional}
                    onChange={(v) => patchItto(setter, it.key, { optional: v })}
                  />
                </Space>
              </Tooltip>
            )}
            <Tooltip title={t("tooltipSkill")}>
              <Button
                size="small"
                type="text"
                icon={<ToolOutlined />}
                style={{ color: "#27ae60", padding: "0 4px" }}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedSkillKey(it.key);
                  setSkillSelectOpen((prev) => !prev);
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
              <Text strong style={{ fontSize: 12, display: "block", marginBottom: 6 }}>{t("skillPickerTitle")}</Text>
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
                          ? current.filter((x) => x !== sid)
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
              <Button size="small" type="text" style={{ float: "right", marginTop: 4 }} onClick={(e) => { e.stopPropagation(); setSkillSelectOpen(false); }}>{t("closeBtn")}</Button>
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
        onClick={() => addItto(setter, kind, t("newItemDefaultLabel"))}
      >{t("addItem")}</Button>
    </Col>
  );

  // ITTO \u6587\u672c\u5217\u8868\u6e32\u67d3\uff08\u8be6\u60c5\u62bd\u5c49\u7528\uff09
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
    ) : <Text type="secondary" style={{ fontSize: 12 }}>{t("dashPlaceholder")}</Text>;

  if (loading && !hasLoaded) {
    return <div style={{ padding: 48, textAlign: "center" }}><Spin /><p style={{ marginTop: 12 }}>{t("loadingAgents")}</p></div>;
  }

  return (
    <div style={{ padding: 8 }}>
      {/* Header: title + project selector */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <BookOutlined style={{ marginRight: 8, color: BRAND.green }} />
            {t("title")}
          </Title>
          <Text type="secondary">
            {t("subtitle")}
          </Text>
        </div>
        <Space>
          <Select
            style={{ width: 240 }}
            placeholder={t("selectProject")}
            allowClear
            value={projectId}
            onChange={setProjectId}
            options={projects.map((p: any) => ({ value: p.id, label: p.name }))}
          />
          {projectId && (
            <Button icon={<ProjectOutlined />} onClick={() => navigate(`/projects/${projectId}`)}>
              {t("openProject")}
            </Button>
          )}
        </Space>
      </div>

      {/* Filter bar */}
      <Card size="small" style={{ marginBottom: 16, borderRadius: 12 }} bodyStyle={{ padding: 12 }}>
        <Space wrap size={12} style={{ width: "100%", justifyContent: "space-between" }}>
          <Space wrap size={8}>
            <Select
              allowClear
              placeholder={t("placeholderPg")}
              style={{ width: 130 }}
              value={filterPg}
              onChange={setFilterPg}
              options={PG_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
            <Select
              allowClear
              placeholder={t("placeholderKa")}
              style={{ width: 140 }}
              value={filterKa}
              onChange={setFilterKa}
              options={KA_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
            <Select
              allowClear
              placeholder={t("placeholderSys")}
              style={{ width: 140 }}
              value={filterSys}
              onChange={setFilterSys}
              options={SYS_OPTIONS.map((v) => ({ value: v, label: v }))}
            />
            <Input.Search
              ref={searchInputRef}
              allowClear
              placeholder={t("searchPlaceholder")}
              style={{ width: 240 }}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={(v) => setSearch(v)}
            />
          </Space>
          <Space size={6}>
            {loading && hasLoaded && <Spin size="small" />}
            <Text type="secondary">{t("totalAgents", { count: totalAgents })}</Text>
          </Space>
        </Space>
      </Card>

      {/* Agent role card grid */}
      {agents.length === 0 ? (
        <Empty description={t("emptyNoMatch")} style={{ padding: 48 }} />
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
                  {a.summary || t("dashPlaceholder")}
                </Paragraph>
                <Space size={16} style={{ marginBottom: 10 }}>
                  <Tooltip title={t("skillCountTooltip")}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <ToolOutlined style={{ color: BRAND.darkGreen }} /> {a.skill_count ?? a.skill_ids?.length ?? 0} {t("skillUnit")}
                    </Text>
                  </Tooltip>
                  <Tooltip title={t("workflowCountTooltip")}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <NodeIndexOutlined style={{ color: BRAND.purple }} /> {wfCountMap[a.id] || 0} {t("workflowUnit")}
                    </Text>
                  </Tooltip>
                </Space>
                <Button
                  type="primary"
                  block
                  icon={<PlayCircleOutlined />}
                  onClick={(e) => { e.stopPropagation(); handleRun(a); }}
                >
                  {t("tryRun")}
                </Button>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* ============ Role detail Drawer ============ */}
      <Drawer
        title={
          <Space>
            <RobotOutlined style={{ color: BRAND.green }} />
            <span>{t("detailTitle", { name: detailAgent?.name_cn || "" })}</span>
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
            <Button onClick={() => setDetailOpen(false)}>{t("close")}</Button>
            <Space>
              <Button
                icon={<PlayCircleOutlined />}
                onClick={() => { if (detailAgent) { setDetailOpen(false); handleRun(detailAgent); } }}
              >
                {t("tryRun")}
              </Button>
              <Button
                type="primary"
                icon={<EditOutlined />}
                onClick={() => { if (detailAgent) { setDetailOpen(false); openEditor(toAnyAgent(detailAgent), "domain"); } }}
              >
                {t("deepEdit")}
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

            <Paragraph>{detailAgent.summary || t("dashPlaceholder")}</Paragraph>

            {detailAgent.v8_note && (
              <Alert type="info" showIcon message={detailAgent.v8_note} style={{ marginBottom: 12 }} />
            )}

            {/* ITTO three columns */}
            <Card type="inner" size="small" title={<><NodeIndexOutlined /> {t("ittoCardTitle")}</>} style={{ marginBottom: 12 }}>
              <Row gutter={12}>
                <Col span={8}>
                  <Text strong style={{ fontSize: 12 }}><PartitionOutlined /> {t("inputsLabel")}</Text>
                  <div style={{ marginTop: 4 }}>{renderItList(detailAgent.itto?.inputs)}</div>
                </Col>
                <Col span={8}>
                  <Text strong style={{ fontSize: 12 }}><ExperimentOutlined /> {t("toolsLabel")}</Text>
                  <div style={{ marginTop: 4 }}>{renderItList(detailAgent.itto?.tools)}</div>
                </Col>
                <Col span={8}>
                  <Text strong style={{ fontSize: 12 }}><PartitionOutlined /> {t("outputsLabel")}</Text>
                  <div style={{ marginTop: 4 }}>{renderItList(detailAgent.itto?.outputs)}</div>
                </Col>
              </Row>
            </Card>

            {/* Scheduled Skills list */}
            <Card type="inner" size="small" title={<><ToolOutlined /> {t("scheduledSkills", { count: detailAgent.skill_ids?.length || 0 })}</>} style={{ marginBottom: 12 }}>
              {detailAgent.skill_ids && detailAgent.skill_ids.length ? (
                <Space wrap size={4}>
                  {detailAgent.skill_ids.map((sid) => (
                    <Tag key={sid} color="geekblue">{skillMap[sid] || sid}</Tag>
                  ))}
                </Space>
              ) : <Text type="secondary">{t("dashPlaceholder")}</Text>}
            </Card>

            {/* Injected principles */}
            <Card type="inner" size="small" title={<><SafetyOutlined /> {t("injectedPrinciples", { count: detailAgent.principle_ids?.length || 0 })}</>} style={{ marginBottom: 12 }}>
              {detailAgent.principle_ids && detailAgent.principle_ids.length ? (
                <Space wrap size={4}>
                  {detailAgent.principle_ids.map((pid) => (
                    <Tag key={pid} color="purple">{principleMap[pid] || pid}</Tag>
                  ))}
                </Space>
              ) : <Text type="secondary">{t("dashPlaceholder")}</Text>}
            </Card>

            {/* Persona / System Prompt summary */}
            <Card type="inner" size="small" title={<><CompassOutlined /> {t("personaCardTitle")}</>} style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 12 }}>{t("personaLabel")}</Text>
              <Paragraph style={{ fontSize: 12, whiteSpace: "pre-wrap", marginTop: 4 }}>
                {detailAgent.persona || t("dashPlaceholder")}
              </Paragraph>
              <Divider style={{ margin: "10px 0" }} />
              <Text strong style={{ fontSize: 12 }}>{t("systemPromptLabel")}</Text>
              <Paragraph style={{ fontSize: 12, whiteSpace: "pre-wrap", marginTop: 4 }}>
                {detailAgent.system_prompt || t("dashPlaceholder")}
              </Paragraph>
            </Card>
          </>
        )}
      </Drawer>

      {/* ============ Agent deep edit Drawer ============ */}
      <Drawer
        title={
          <Space>
            <EditOutlined style={{ color: BRAND.purple }} />
            <span>{t("editTitle", { name: editing?.name || "" })}</span>
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
                <Tooltip title={t("runTooltip")}>
                  <Button
                    icon={<CloudDownloadOutlined />}
                    onClick={() => { setEditOpen(false); if (editing) { setRunDialogAgent({ id: editing.id, name: editing.name, kind: "domain" }); setRunDialogOpen(true); } }}
                  >
                    {t("run")}
                  </Button>
                </Tooltip>
              <Tooltip title={t("resetTooltip")}>
                <Button danger icon={<DeleteOutlined />} onClick={resetOverride}>
                  {t("reset")}
                </Button>
              </Tooltip>
            </Space>
            <Space>
              <Button onClick={() => setEditOpen(false)}>{t("close")}</Button>
              <Button type="primary" icon={<SaveOutlined />} loading={editSaving} onClick={saveOverride}>
                {t("saveOverride")}
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
              message={t("alertTitle")}
              description={
                <span>
                  <Trans
                    i18nKey="pmbokAgents.alertDesc"
                    components={{ code: <code style={{ padding: "0 4px" }} /> }}
                  />
                </span>
              }
              style={{ marginBottom: 16 }}
            />

            {/* Basic info */}
            <Card type="inner" size="small" title={<><CodeOutlined /> {t("basicInfo")}</>} style={{ marginBottom: 12 }}>
              <Form form={editForm} layout="vertical">
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item label={t("agentName")} name="name" rules={[{ required: true, message: t("nameRequired") }]}>
                      <Input prefix={<RobotOutlined />} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item label={t("inputHint")} name="input_hint" tooltip={t("inputHintTooltip")}>
                      <Input placeholder={t("inputHintPlaceholder")} />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label={t("descriptionLabel")} name="description">
                  <TextArea autoSize={{ minRows: 2, maxRows: 4 }} placeholder={t("descriptionPlaceholder")} />
                </Form.Item>
              </Form>
            </Card>

            {/* ITTO (structured, configurable) */}
            <Card
              type="inner"
              size="small"
              title={<><NodeIndexOutlined /> {t("ittoEditTitle")}</>}
              style={{ marginBottom: 12 }}
              extra={<Text type="secondary" style={{ fontSize: 12 }}>{t("ittoEditExtra")}</Text>}
            >
              <Row gutter={16}>
                {renderIttoCol(
                  "input",
                  <><NodeIndexOutlined /> {t("inputsMaterial")}</>,
                  t("inputsDesc"),
                  ittoInputs,
                  setIttoInputs,
                )}
                {renderIttoCol(
                  "tool",
                  <><ToolOutlined /> {t("toolsTech")}</>,
                  t("toolsDesc"),
                  ittoTools,
                  setIttoTools,
                )}
                {renderIttoCol(
                  "output",
                  <><PartitionOutlined /> {t("outputsFile")}</>,
                  t("outputsDesc"),
                  ittoOutputs,
                  setIttoOutputs,
                )}
              </Row>
            </Card>

            {/* Process display */}
            <Card type="inner" size="small" title={<><ExperimentOutlined /> {t("processDisplay")}</>} style={{ marginBottom: 12 }}>
              <Form form={editForm} layout="vertical">
                <Form.Item
                  label={t("processLabel")}
                  name="process"
                  tooltip={t("processTooltip")}
                >
                  <TextArea autoSize={{ minRows: 3, maxRows: 8 }} placeholder={t("processPlaceholder")} />
                </Form.Item>
              </Form>
            </Card>


            {/* Advanced system_prompt */}
            <Card type="inner" size="small" title={<><ThunderboltOutlined /> {t("advancedTitle")}</>} style={{ marginBottom: 12 }}>
              <Form form={editForm} layout="vertical">
                <Form.Item
                  label={t("systemPromptFullLabel")}
                  name="system_prompt"
                  tooltip={t("systemPromptFullTooltip")}
                >
                  <TextArea
                    autoSize={{ minRows: 4, maxRows: 12 }}
                    placeholder={t("systemPromptFullPlaceholder", { name: editing?.name || t("agentName") })}
                    style={{ fontFamily: "monospace", fontSize: 12 }}
                  />
                </Form.Item>
                <Form.Item label={t("editNoteLabel")} name="note">
                  <Input placeholder={t("editNotePlaceholder")} />
                </Form.Item>
              </Form>
            </Card>

            <Divider />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("overrideCount", {
                count: editOverride?.updated_at ? 1 : 0,
                updatedAt: editOverride?.updated_at || t("notSaved"),
                updatedBy: editOverride?.updated_by || t("dashPlaceholder"),
              })}
            </Text>
          </>
        )}
      </Drawer>

      {/* ============ Unified manual run dialog ============ */}
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
