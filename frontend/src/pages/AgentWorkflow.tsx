import React, { useState, useCallback, useMemo, useEffect, useRef } from "react";
import {
  Card, Typography, Button, Space, App, Tag, Modal, Input,
  Select, Progress, Empty, Spin, Drawer, Tooltip,
} from "antd";
import {
  PlayCircleOutlined, SaveOutlined, DeleteOutlined,
  ReloadOutlined, ApartmentOutlined, LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ThunderboltOutlined, RobotOutlined, EyeOutlined, SettingOutlined, SearchOutlined,
  PartitionOutlined, CompassOutlined, RocketOutlined, FlagOutlined, SwapOutlined,
  FileTextOutlined, BarChartOutlined, WarningOutlined, SafetyOutlined, AimOutlined,
  FileDoneOutlined, HeartOutlined, BulbOutlined, NodeIndexOutlined, ClearOutlined,
  FullscreenOutlined, FullscreenExitOutlined, ZoomInOutlined, ZoomOutOutlined,
  LeftOutlined, RightOutlined,
} from "@ant-design/icons";
import {
  ReactFlow, Background, MiniMap, ReactFlowProvider,
  useNodesState, useEdgesState, addEdge, Handle, Position,
  useReactFlow, MarkerType,
  type Node, type Edge, type NodeProps, type Connection,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { workflowApi, agentApi, pmbokV3Api } from "../api";

const { Text } = Typography;
const PRIMARY = "#4F46E5";

// ─────────────────────────────────────────────────────────────────────────────
// Type definitions
// ─────────────────────────────────────────────────────────────────────────────

type NodeStatus = "idle" | "running" | "success" | "error";

interface AgentNodeData {
  agentType: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  status: NodeStatus;
  // New: node-level runtime config (supports precise upstream output -> downstream input binding)
  userInput: string;                 // inline supplementary input text
  selectedTools: string[];           // selected tool/technique keys
  inputMapping: Record<string, string>; // {input slot key: upstream node id}
  // New: PMI 3-layer mapping metadata (backward compatible, all optional)
  nodeKind?: "agent" | "skill" | "gate";
  refId?: string;                    // points to agent / skill id
  note?: string;
}

type AgentNode = Node<AgentNodeData>;

interface LogEntry {
  id: string;
  time: string;
  label: string;
  message: string;
  level: "info" | "success" | "error";
}

/** Structured ITTO slots returned by the prepare endpoint */
interface SlotItem {
  key: string;
  label: string;
  optional: boolean;
  enabled: boolean;
  kind: string;
  exists?: boolean;
}

/** PMBOK V3 node panel library entry (agent / skill) */
interface PmbokAgentItem {
  id: string;
  code?: string;
  name_cn?: string;
  name?: string;
  process_group?: string;
  knowledge_area?: string;
  system_label?: string;
  summary?: string;
  description?: string;
  icon?: string;
  color?: string;
}
interface PmbokSkillItem {
  id: string;
  code?: string;
  name_cn?: string;
  name?: string;
  category?: string;
  system_label?: string;
  summary?: string;
  description?: string;
  definition?: string;
  icon?: string;
  color?: string;
}
interface PmbokWorkflowNode {
  seq: number;
  type: "agent" | "skill" | "gate";
  ref?: string;
  ref_id?: string;
  name?: string;
  note?: string;
  is_pending?: boolean;
}
interface PmbokWorkflowItem {
  id: string;
  code?: string;
  name_cn?: string;
  name?: string;
  system_label?: string;
  summary?: string;
  node_count?: number;
  principle_ids?: string[];
  nodes?: PmbokWorkflowNode[];
}

/** Selected node info snapshot (used to fetch ITTO) */
interface Selection {
  id: string;
  kind: "agent" | "skill" | "gate";
  refId: string;
  note?: string;
  type: string;
}
interface NodeDetail {
  kind: "agent" | "skill" | "gate";
  type: string;
  note?: string;
  itto?: { inputs?: any[]; tools?: any[]; outputs?: any[] };
  definition?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Icon / color mapping
// ─────────────────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<any>> = {
  FileTextOutlined, BarChartOutlined, WarningOutlined, RobotOutlined, ThunderboltOutlined,
  SafetyOutlined, AimOutlined, FileDoneOutlined, HeartOutlined, BulbOutlined,
  PartitionOutlined, CompassOutlined, ApartmentOutlined, NodeIndexOutlined,
};

let _counter = 0;
const uid = (prefix: string) => `${prefix}_${Date.now()}_${_counter++}`;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

// ─────────────────────────────────────────────────────────────────────────────
// Custom node (with Handle connection points + framer-motion micro-animations + config indicator)
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_META_COLORS: Record<NodeStatus, { color: string; key: "idle" | "running" | "success" | "error" }> = {
  idle:    { color: "#94A3B8", key: "idle" },
  running: { color: "#F59E0B", key: "running" },
  success: { color: "#10B981", key: "success" },
  error:   { color: "#EF4444", key: "error" },
};

const STATUS_ICONS: Record<NodeStatus, React.ReactNode> = {
  idle: <LoadingOutlined style={{ opacity: 0 }} />,
  running: <LoadingOutlined spin />,
  success: <CheckCircleOutlined />,
  error: <CloseCircleOutlined />,
};

const getStatusMeta = (t: (k: string) => string, status: NodeStatus) => {
  const meta = STATUS_META_COLORS[status];
  return { color: meta.color, text: t(`agentWorkflow.status.${meta.key}`), icon: STATUS_ICONS[status] };
};

const StatusBadge: React.FC<{ status: NodeStatus; t: (k: string) => string }> = ({ status, t }) => {
  const m = getStatusMeta(t, status);
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: 10, color: m.color, fontWeight: 600,
      background: `${m.color}1A`, padding: "2px 6px", borderRadius: 8,
    }}>
      {m.icon}{m.text}
    </span>
  );
};

const hasConfig = (d: AgentNodeData) =>
  !!(d.userInput && d.userInput.trim()) ||
  (d.selectedTools && d.selectedTools.length > 0) ||
  (d.inputMapping && Object.keys(d.inputMapping).length > 0);

const AgentNodeView: React.FC<NodeProps<AgentNodeData>> = ({ data, selected }) => {
  const { t } = useTranslation("agentWorkflow");
  const status = data.status;
  const ring =
    status === "idle" ? (selected ? data.color : "#E2E8F0")
      : status === "running" ? "#F59E0B"
      : status === "success" ? "#10B981"
      : "#EF4444";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{
        opacity: 1,
        scale: status === "running" ? 1.04 : 1,
        boxShadow:
          status === "running" ? "0 0 0 4px rgba(245,158,11,0.30)"
          : status === "success" ? "0 0 0 3px rgba(16,185,129,0.28)"
          : status === "error" ? "0 0 0 3px rgba(239,68,68,0.28)"
          : "0 2px 10px rgba(0,0,0,0.08)",
      }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
      style={{
        width: 196, borderRadius: 12, background: "#fff",
        border: `1.5px solid ${ring}`,
      }}
    >
      <Handle type="target" position={Position.Left}
        style={{ background: data.color, width: 10, height: 10, border: "2px solid #fff" }} />
      <div style={{ padding: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: data.color, fontSize: 18 }}>{data.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 12, lineHeight: 1.3, color: "#1E293B" }}>
              {data.label}
            </div>
          </div>
          <StatusBadge status={status} t={t} />
        </div>
        <div style={{ fontSize: 10, color: "#64748B", marginTop: 4, lineHeight: 1.4 }}>
          {data.description}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
          <span style={{ fontSize: 9, color: "#94A3B8", fontFamily: "monospace" }}>
            {data.agentType}
          </span>
          {hasConfig(data) && (
            <Tooltip title={t("agentWorkflow.configTooltip")}>
              <span style={{ color: "#6366F1", fontSize: 11 }}><SettingOutlined /></span>
            </Tooltip>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Right}
        style={{ background: data.color, width: 10, height: 10, border: "2px solid #fff" }} />
    </motion.div>
  );
};

/** Gate (decision/branch) node: orange diamond style, used as a flow decision node */
const GateNodeView: React.FC<NodeProps<AgentNodeData>> = ({ data, selected }) => (
  <div style={{
    width: 168, borderRadius: 10, background: "#FFF7ED",
    border: `1.5px solid ${selected ? "#F59E0B" : "#FED7AA"}`,
    padding: 10, display: "flex", alignItems: "center", gap: 8,
  }}>
    <Handle type="target" position={Position.Left}
      style={{ background: "#F59E0B", width: 10, height: 10, border: "2px solid #fff" }} />
    <span style={{ color: "#F59E0B", fontSize: 18 }}>{data.icon}</span>
    <div style={{ fontWeight: 600, fontSize: 12, color: "#9A3412", minWidth: 0 }}>{data.label}</div>
    <Handle type="source" position={Position.Right}
      style={{ background: "#F59E0B", width: 10, height: 10, border: "2px solid #fff" }} />
  </div>
);

const nodeTypes = { agent: AgentNodeView, gate: GateNodeView };

// Generic grouping utility
function groupBy<T>(arr: T[], key: (t: T) => string): { key: string; items: T[] }[] {
  const m = new Map<string, T[]>();
  for (const it of arr) {
    const k = key(it);
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(it);
  }
  return Array.from(m.entries()).map(([k, items]) => ({ key: k, items }));
}

// Left panel node item
const PanelItem: React.FC<{
  label: string; sub?: string; desc?: string; color: string;
  icon: React.ComponentType<any>; onClick: () => void;
}> = ({ label, sub, desc, color, icon, onClick }) => {
  const IconC = icon;
  return (
    <div onClick={onClick} style={{ cursor: "grab", marginBottom: 6 }}>
      <div style={{
        borderLeft: `3px solid ${color}`, borderRadius: 8, padding: "6px 8px",
        background: "#fff", border: "1px solid #F1F5F9", display: "flex", gap: 8, alignItems: "center",
      }}>
        <span style={{ color, fontSize: 15 }}><IconC /></span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 600, lineHeight: 1.3, color: "#1E293B" }}>
            {label}
            {sub && <span style={{ fontSize: 9, color: "#94A3B8", marginLeft: 4 }}>{sub}</span>}
          </div>
          {desc && (
            <div style={{ fontSize: 10, color: "#64748B", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {desc}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// t("agentWorkflow.rightPanel.title")块
const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div style={{ marginBottom: 12 }}>
    <div style={{ fontSize: 11, fontWeight: 600, color: "#6B7280", marginBottom: 4, letterSpacing: 0.5 }}>
      {title}
    </div>
    {children}
  </div>
);

function renderSlot(items?: any[]): React.ReactNode {
  if (!items || items.length === 0) return <Text type="secondary" style={{ fontSize: 11 }}>—</Text>;
  return (
    <div>
      {items.map((it, idx) => {
        const label = typeof it === "string"
          ? it
          : (it?.label || it?.key || it?.name || it?.title || String(it));
        return <Tag key={idx} color="blue" style={{ marginBottom: 4 }}>{label}</Tag>;
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page (inner, uses React Flow hooks)
// ─────────────────────────────────────────────────────────────────────────────

const WorkflowInner: React.FC = () => {
  const { message } = App.useApp();
  const { t } = useTranslation("agentWorkflow");
  const { fitView, zoomIn, zoomOut, getZoom } = useReactFlow();

  const initial = useMemo(() => ({ nodes: [] as AgentNode[], edges: [] as Edge[] }), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNodeData>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);

  const [workflowName, setWorkflowName] = useState(t("agentWorkflow.defaultName"));
  const [executing, setExecuting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState<LogEntry[]>([]);

  // ── 全屏 / 悬浮展示 ─────────────────────────────────────────────
  // 全屏时整块工作流（节点面板 + 画布 + t("agentWorkflow.rightPanel.title")）铺满屏幕，t("agentWorkflow.rightPanel.title")保持可用
  const rootRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoomPct, setZoomPct] = useState(100);
  // ── 侧栏抽屉（全屏时节点面板/t("agentWorkflow.rightPanel.title")可收起/展开，也可保持固定）──
  const [leftPanelOpen, setLeftPanelOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const toggleFullscreen = useCallback(() => {
    const el = rootRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  }, []);
  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  // Esc 退出全屏的兜底（部分浏览器 fullscreenchange 已覆盖，此处置顶）
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setIsFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isFullscreen]);
  // Track current zoom percentage (throttled)
  useEffect(() => {
    let raf = 0;
    const loop = () => { setZoomPct(Math.round(getZoom() * 100)); raf = requestAnimationFrame(loop); };
    if (isFullscreen) raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [isFullscreen, getZoom]);
  const handleZoomIn = useCallback(() => { zoomIn({ duration: 200 }); setZoomPct(Math.min(300, Math.round(getZoom() * 100) + 20)); }, [zoomIn, getZoom]);
  const handleZoomOut = useCallback(() => { zoomOut({ duration: 200 }); setZoomPct(Math.max(20, Math.round(getZoom() * 100) - 20)); }, [zoomOut, getZoom]);
  const handleZoomFit = useCallback(() => { fitView({ duration: 300, padding: 0.15 }); }, [fitView]);

  // Workflow save (multi-tenant, uses workflowApi)
  const [currentWfId, setCurrentWfId] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDesc, setSaveDesc] = useState("");

  // Node configuration drawer
  const [configNode, setConfigNode] = useState<AgentNode | null>(null);
  const [slotInfo, setSlotInfo] = useState<{ inputs: SlotItem[]; tools: SlotItem[]; outputs: SlotItem[] }>({ inputs: [], tools: [], outputs: [] });
  const [cfgUserInput, setCfgUserInput] = useState("");
  const [cfgTools, setCfgTools] = useState<string[]>([]);
  const [cfgMapping, setCfgMapping] = useState<Record<string, string>>({});
  const [cfgOutputSlots, setCfgOutputSlots] = useState<Record<string, boolean>>({});
  const [slotLoading, setSlotLoading] = useState(false);

  // Run results (for node drawer to display output)
  const [lastRun, setLastRun] = useState<any | null>(null);

  // PMBOK V3 node panel library + workflow templates
  const [pmbokAgents, setPmbokAgents] = useState<PmbokAgentItem[]>([]);
  const [pmbokAgentsLoading, setPmbokAgentsLoading] = useState(true);
  const [pmbokSkills, setPmbokSkills] = useState<PmbokSkillItem[]>([]);
  const [pmbokSkillsLoading, setPmbokSkillsLoading] = useState(true);
  const [pmbokWorkflows, setPmbokWorkflows] = useState<PmbokWorkflowItem[]>([]);
  const [pmbokWorkflowsLoading, setPmbokWorkflowsLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [autoLoaded, setAutoLoaded] = useState(false);
  const autoLoadedRef = React.useRef(false);
  const [panelSearch, setPanelSearch] = useState("");

  // t("agentWorkflow.rightPanel.title")：当前选中节点 + 拉取的 ITTO 详情
  const [selection, setSelection] = useState<Selection | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);

  const addLog = useCallback((label: string, msg: string, level: LogEntry["level"]) => {
    setLog(prev => [...prev, {
      id: uid("log"), time: new Date().toLocaleTimeString(),
      label, message: msg, level,
    }]);
  }, []);

  // Load PMBOK V3 node panel library + workflow templates (try/catch, don't crash on failure)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPmbokAgentsLoading(true); setPmbokSkillsLoading(true); setPmbokWorkflowsLoading(true);
      try {
        const [a, s, w] = await Promise.all([
          pmbokV3Api.agents().catch(() => ({ items: [] })),
          pmbokV3Api.skills().catch(() => ({ items: [] })),
          pmbokV3Api.workflows().catch(() => ({ items: [] })),
        ]);
        if (cancelled) return;
        setPmbokAgents((a as any)?.items || (a as any) || []);
        setPmbokSkills((s as any)?.items || (s as any) || []);
        setPmbokWorkflows((w as any)?.items || (w as any) || []);
      } catch {
        // Keep empty list on API errors, show empty hint in canvas
      } finally {
        if (!cancelled) {
          setPmbokAgentsLoading(false);
          setPmbokSkillsLoading(false);
          setPmbokWorkflowsLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const resolvePmbokMeta = useCallback((item: any, kind: "agent" | "skill") => {
    const iconName = item?.icon;
    const icon = (iconName && ICON_MAP[iconName])
      ? ICON_MAP[iconName]
      : (kind === "skill" ? ThunderboltOutlined : RobotOutlined);
    const color = item?.color || (kind === "skill" ? "#0EA5E9" : PRIMARY);
    return { icon, color };
  }, []);

  // Filter (by search keyword)
  const filteredAgents = useMemo(() => {
    const kw = panelSearch.trim().toLowerCase();
    return pmbokAgents.filter(a =>
      !kw || `${a.name_cn || ""} ${a.name || ""} ${a.code || ""} ${a.summary || ""}`.toLowerCase().includes(kw));
  }, [pmbokAgents, panelSearch]);
  const groupedAgents = useMemo(
    () => groupBy(filteredAgents, a => a.process_group || t("agentWorkflow.leftPanel.defaultGroup")),
    [filteredAgents, t]);

  const filteredSkills = useMemo(() => {
    const kw = panelSearch.trim().toLowerCase();
    return pmbokSkills.filter(s =>
      !kw || `${s.name_cn || ""} ${s.name || ""} ${s.code || ""} ${s.summary || ""}`.toLowerCase().includes(kw));
  }, [pmbokSkills, panelSearch]);
  const groupedSkills = useMemo(
    () => groupBy(filteredSkills, s => s.category || t("agentWorkflow.leftPanel.defaultCategory")),
    [filteredSkills, t]);

  // Add a new node by clicking from the left panel
  const addNodeFromPanel = useCallback((item: PmbokAgentItem | PmbokSkillItem, kind: "agent" | "skill") => {
    const meta = resolvePmbokMeta(item, kind);
    const id = uid(kind === "agent" ? "agent" : "skill");
    const idx = nodes.length;
    const position = { x: 40 + (idx % 4) * 250, y: 40 + Math.floor(idx / 4) * 150 };
    const label = (item as any).name_cn || (item as any).name || (item as any).code || t("agentWorkflow.leftPanel.untitledNode");
    const desc = (item as any).summary || (item as any).description || "";
    const newNode: AgentNode = {
      id, type: "agent", position,
      data: {
        agentType: (item as any).id, label, description: desc,
        icon: React.createElement(meta.icon), color: meta.color, status: "idle",
        userInput: "", selectedTools: [], inputMapping: {},
        nodeKind: kind, refId: (item as any).id, note: "",
      },
    };
    setNodes(nds => [...nds, newNode]);
    message.success(t("agentWorkflow.leftPanel.addNodeSuccess", { name: label }));
  }, [nodes.length, setNodes, message, resolvePmbokMeta, t]);

  // Load workflow template: render nodes to canvas + connect edges by seq
  const loadWorkflowTemplate = useCallback(async (id: string) => {
    try {
      console.log('[Workflow] Loading template:', id);
      const res: any = await pmbokV3Api.workflow(id);
      console.log('[Workflow] API response:', res);
      const wf = res; // API returns workflow object directly
      const wfNodes: PmbokWorkflowNode[] = (wf?.nodes || []).slice().sort((a: PmbokWorkflowNode, b: PmbokWorkflowNode) => a.seq - b.seq);
      const newNodes: AgentNode[] = wfNodes.map((n, i) => {
        const position = { x: 40 + (i % 3) * 260, y: 40 + Math.floor(i / 3) * 170 };
        if (n.type === "gate") {
          return {
            id: uid("gate"), type: "gate", position,
            data: {
              agentType: n.ref || "gate", label: n.name || t("agentWorkflow.loadTemplate.defaultGate"), description: "",
              icon: React.createElement(SwapOutlined), color: "#F59E0B", status: "idle",
              userInput: "", selectedTools: [], inputMapping: {},
              nodeKind: "gate", refId: n.ref_id || n.ref || "", note: n.note || "",
            },
          };
        }
        const isSkill = n.type === "skill";
        const meta = resolvePmbokMeta({ icon: isSkill ? "ThunderboltOutlined" : "RobotOutlined" }, isSkill ? "skill" : "agent");
        return {
          id: uid(isSkill ? "skill" : "agent"), type: "agent", position,
          data: {
            agentType: n.ref_id || n.ref || "", label: n.name || "", description: "",
            icon: React.createElement(meta.icon), color: meta.color, status: "idle",
            userInput: "", selectedTools: [], inputMapping: {},
            nodeKind: isSkill ? "skill" : "agent", refId: n.ref_id || n.ref || "", note: n.note || "",
          },
        };
      });
      const newEdges: Edge[] = [];
      // Try ITTO edges, fall back to linear connection if API has no edges field
      const ittoEdges = (wf as any).edges;
      if (ittoEdges && ittoEdges.length > 0) {
        const nodeMap = new Map<string, AgentNode>();
        newNodes.forEach(n => nodeMap.set(n.data.refId, n));
        ittoEdges.forEach((e: any) => {
          const srcNode = nodeMap.get(e.source);
          const tgtNode = nodeMap.get(e.target);
          if (srcNode && tgtNode) {
            newEdges.push({
              id: uid("e"), source: srcNode.id, target: tgtNode.id,
              animated: true, style: { stroke: PRIMARY, strokeWidth: 2 },
              markerEnd: { type: MarkerType.ArrowClosed, color: PRIMARY },
            });
          }
        });
      }
      // If no edges matched, use linear connection as fallback
      if (newEdges.length === 0 && newNodes.length > 1) {
        for (let i = 0; i < newNodes.length - 1; i++) {
          newEdges.push({
            id: uid("e"), source: newNodes[i].id, target: newNodes[i + 1].id,
            animated: true, style: { stroke: PRIMARY, strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: PRIMARY },
          });
        }
      }
      console.log('[Workflow] Setting nodes:', newNodes.length, 'edges:', newEdges.length);
      setNodes(newNodes);
      setEdges(newEdges);
      setSelection(null);
      setTimeout(() => fitView({ padding: 0.2 }), 60);
      message.success(t("agentWorkflow.loadTemplate.success", { name: wf?.name_cn || wf?.name || wf?.code || "" }));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || t("agentWorkflow.loadTemplate.fail"));
    }
  }, [setNodes, setEdges, message, fitView, resolvePmbokMeta, t]);

  // Connect (edge = dependency; supports fan-in/fan-out)
  const onConnect = useCallback((connection: Connection) => {
    setEdges(eds => addEdge({
      ...connection, animated: true,
      style: { stroke: PRIMARY, strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: PRIMARY },
    }, eds));
  }, [setEdges]);

  const onNodeClick = useCallback((_: any, node: Node) => {
    const n = node as AgentNode;
    setSelection({
      id: n.id,
      kind: n.data.nodeKind || "agent",
      refId: n.data.refId || n.data.agentType,
      note: n.data.note,
      type: n.data.agentType,
    });
  }, []);
  const onPaneClick = useCallback(() => setSelection(null), []);

  // -- Auto-load the first workflow template after page load --
  useEffect(() => {
    if (pmbokWorkflows.length > 0 && nodes.length === 0 && !autoLoadedRef.current) {
      autoLoadedRef.current = true;
      setAutoLoaded(true);
      const fullProcess = pmbokWorkflows.find(w => w.id === "pmbok_full_process"); const firstId = fullProcess ? fullProcess.id : pmbokWorkflows[0].id;
      setSelectedTemplateId(firstId);
      loadWorkflowTemplate(firstId);
    }
  }, [pmbokWorkflows, nodes.length]);



  // ── t("agentWorkflow.rightPanel.title")：根据 selection 拉取 ITTO / definition ──
  useEffect(() => {
    if (!selection) { setNodeDetail(null); return; }
    if (selection.kind === "gate") {
      setNodeDetail({ kind: "gate", type: selection.type, note: selection.note });
      return;
    }
    let cancelled = false;
    setNodeDetailLoading(true);
    (async () => {
      try {
        if (selection.kind === "skill") {
          const r: any = await pmbokV3Api.skill(selection.refId).catch(() => null);
          if (!cancelled) setNodeDetail({ kind: "skill", type: selection.type, note: selection.note, definition: r?.definition || r?.summary || "" });
        } else {
          const r: any = await pmbokV3Api.agent(selection.refId).catch(() => null);
          const itto = r?.itto || { inputs: r?.inputs, tools: r?.tools, outputs: r?.outputs };
          if (!cancelled) setNodeDetail({
            kind: "agent", type: selection.type, note: selection.note,
            itto: itto || { inputs: [], tools: [], outputs: [] },
          });
        }
      } catch {
        if (!cancelled) setNodeDetail({ kind: selection.kind, type: selection.type, note: selection.note });
      } finally {
        if (!cancelled) setNodeDetailLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selection]);

  // ── 清空 ──
  const handleClear = useCallback(() => {
    setNodes([]);
    setEdges([]);
    setLog([]);
    setProgress(0);
    setLastRun(null);
    setSelection(null);
    message.info(t("agentWorkflow.clear"));
  }, [setNodes, setEdges, message, t]);

  // ── 自动布局：按 DAG 分层 ──
  const handleAutoLayout = useCallback(() => {
    if (nodes.length === 0) return;
    const adj = new Map<string, string[]>();
    edges.forEach(e => { if (!adj.has(e.source)) adj.set(e.source, []); adj.get(e.source)!.push(e.target); });
    const layer = new Map<string, number>();
    const calc = (id: string, stack: Set<string>): number => {
      if (layer.has(id)) return layer.get(id)!;
      if (stack.has(id)) return 0;
      stack.add(id);
      let l = 0;
      for (const t of adj.get(id) || []) l = Math.max(l, calc(t, stack) + 1);
      stack.delete(id);
      layer.set(id, l);
      return l;
    };
    nodes.forEach(n => calc(n.id, new Set()));
    const byLayer: Record<number, string[]> = {};
    nodes.forEach(n => { const l = layer.get(n.id) || 0; (byLayer[l] = byLayer[l] || []).push(n.id); });
    const pos: Record<string, { x: number; y: number }> = {};
    Object.keys(byLayer).forEach(k => {
      const l = Number(k);
      byLayer[l].forEach((id, i) => { pos[id] = { x: 60 + l * 270, y: 60 + i * 150 }; });
    });
    setNodes(nds => nds.map(n => ({ ...n, position: pos[n.id] || n.position })));
    setTimeout(() => fitView({ padding: 0.2 }), 60);
  }, [nodes, edges, setNodes, fitView]);

  // ── 由节点/边构建后端步骤 ──
  const buildSteps = useCallback((): any[] => {
    return nodes.map(n => ({
      agent_type: n.data.agentType,
      label: n.id,
      depends_on: edges.filter(e => e.target === n.id).map(e => e.source),
      user_input: n.data.userInput || "",
      selected_tools: n.data.selectedTools || [],
      input_mapping: n.data.inputMapping || {},
      output_slot_config: n.data.outputSlotConfig || {},
    }));
  }, [nodes, edges]);

  // ── 运行工作流（异步调度）──
  const handleRun = useCallback(async () => {
    if (nodes.length === 0) { message.warning(t("agentWorkflow.run.needNodes")); return; }
    setExecuting(true);
    setProgress(0);
    setLog([]);
    setLastRun(null);
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, status: "idle" } })));

    const steps = buildSteps();
    const nodeLabelById = new Map(nodes.map(n => [n.id, n.data.label]));
    addLog(t("agentWorkflow.log.workflow"), t("agentWorkflow.run.submit", { count: steps.length }), "info");

    let runId: string | undefined;
    try {
      const res: any = await workflowApi.execute({ steps });
      runId = res?.run_id;
      if (!runId) throw new Error(t("agentWorkflow.run.noRunId"));
      addLog(t("agentWorkflow.log.workflow"), t("agentWorkflow.run.submitted", { id: runId.slice(0, 8) }), "info");
    } catch (e: any) {
      addLog(t("agentWorkflow.log.workflow"), t("agentWorkflow.run.submitFail", { error: e?.response?.data?.detail || e?.message }), "error");
      message.error(t("agentWorkflow.run.submitError"));
      setExecuting(false);
      return;
    }

    const seen = new Set<string>();
    const total = steps.length;
    let failed = 0;
    try {
      while (true) {
        let st: any;
        try {
          st = await workflowApi.getRunStatus(runId!);
        } catch (e: any) {
          if ((e as any)?.response?.status === 404) { addLog(t("agentWorkflow.log.workflow"), t("agentWorkflow.run.runExpired"), "error"); break; }
          await sleep(1500); continue;
        }
        const results = st?.results || {};
        for (const [label, r] of Object.entries(results)) {
          const rr = r as any;
          const disp = nodeLabelById.get(label) || label;
          let st2: NodeStatus = "idle";
          if (rr.status === "running") st2 = "running";
          else if (rr.status === "completed") st2 = "success";
          else if (rr.status === "failed") st2 = "error";
          setNodes(nds => nds.map(n => n.id === label ? { ...n, data: { ...n.data, status: st2 } } : n));

          if ((rr.status === "completed" || rr.status === "failed") && !seen.has(label)) {
            seen.add(label);
            if (rr.status === "failed") { failed++; addLog(disp, t("agentWorkflow.run.nodeFail", { error: rr.error || t("agentWorkflow.run.unknownError") }), "error"); }
            else addLog(disp, t("agentWorkflow.run.completed"), "success");
            const out = rr.output_preview as string | undefined;
            if (out) addLog(disp, t("agentWorkflow.run.output", { text: out.slice(0, 160) + (out.length > 160 ? "…" : "") }), "info");
          }
        }
        const finished = Object.values(results).filter((r: any) => r.status === "completed" || r.status === "failed").length;
        setProgress(Math.round((finished / total) * 100));

        const status = st?.status;
        if (status === "completed" || status === "partial_failure" || status === "failed") {
          setLastRun(st);
          break;
        }
        await sleep(1500);
      }
      const finalSt: any = await workflowApi.getRunStatus(runId!).catch(() => lastRun);
      const fstatus = finalSt?.status || "unknown";
      addLog(t("agentWorkflow.log.workflow"), t("agentWorkflow.run.finished", { status: fstatus }) + (failed ? t("agentWorkflow.run.failedCount", { count: failed }) : ""), failed ? "error" : "success");
      message.success(t("agentWorkflow.run.runSuccess", { status: fstatus }));
      setTimeout(() => fitView({ padding: 0.2 }), 60);
    } catch (e: any) {
      addLog(t("agentWorkflow.log.workflow"), t("agentWorkflow.run.pollError", { error: e?.message || t("agentWorkflow.run.unknownError") }), "error");
      message.error(t("agentWorkflow.run.queryError"));
    } finally {
      setExecuting(false);
    }
  }, [nodes, edges, setNodes, message, addLog, fitView, buildSteps, lastRun, t]);

  // ── 删除选中的边/节点 ──
  const removeSelected = useCallback(() => {
    setNodes(nds => nds.filter(n => !n.selected));
    setEdges(eds => eds.filter(e => !e.selected));
  }, [setNodes, setEdges]);

  // ── 保存 / 更新工作流 ──
  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) { message.warning(t("agentWorkflow.save.needName")); return; }
    const steps = buildSteps();
    const payload = { name: workflowName, description: saveDesc, steps };
    try {
      if (currentWfId) {
        await workflowApi.update(currentWfId, payload);
        message.success(t("agentWorkflow.save.updated"));
      } else {
        const res: any = await workflowApi.create(payload);
        setCurrentWfId(res?.workflow?.id || res?.id || null);
        message.success(t("agentWorkflow.save.created"));
      }
      setSaveOpen(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || t("agentWorkflow.save.fail"));
    }
  }, [workflowName, saveDesc, currentWfId, message, buildSteps, t]);

  // ── 节点配置抽屉：打开时拉取结构化 ITTO 槽位 ──
  useEffect(() => {
    if (!configNode) { setSlotInfo({ inputs: [], tools: [], outputs: [] }); return; }
    setCfgUserInput(configNode.data.userInput || "");
    setCfgTools(configNode.data.selectedTools || []);
    setCfgMapping(configNode.data.inputMapping || {});
    setCfgOutputSlots(configNode.data.outputSlotConfig || {});
    let cancelled = false;
    setSlotLoading(true);
    (async () => {
      try {
        const r: any = await agentApi.prepare(configNode.data.agentType, {});
        if (!cancelled) {
          const norm = (arr: any[] = []): SlotItem[] =>
            (arr || []).filter((it: any) => it && it.enabled !== false)
              .map((it: any) => ({ key: it.key, label: it.label || it.key, optional: !!it.optional, enabled: it.enabled !== false, kind: it.kind || "file" }));
          setSlotInfo({ inputs: norm(r?.inputs), tools: norm(r?.tools), outputs: norm(r?.outputs) });
        }
      } catch {
        if (!cancelled) setSlotInfo({ inputs: [], tools: [], outputs: [] });
      } finally {
        if (!cancelled) setSlotLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [configNode]);

  // 当前节点在最近一次运行中的结果
  const currentNodeRun = useMemo(() => {
    if (!configNode || !lastRun?.results) return null;
    return (lastRun.results as any)[configNode.id] || null;
  }, [configNode, lastRun]);

  const upstreamOptions = useMemo(() => {
    if (!configNode) return [];
    return nodes
      .filter(n => edges.some(e => e.target === configNode.id && e.source === n.id))
      .map(n => ({ value: n.id, label: n.data.label }));
  }, [configNode, nodes, edges]);

  const selNode = selection ? nodes.find(n => n.id === selection.id) || null : null;

  // ── 渲染 ──
  return (
    <div ref={rootRef} style={{ display: "flex", flexDirection: "column", height: isFullscreen ? "100vh" : "calc(100vh - 112px)", background: isFullscreen ? "#F8FAFC" : "transparent", position: isFullscreen ? "relative" : "static", overflow: "hidden" }}>
      {/* Header: workflow name + save */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <ApartmentOutlined style={{ color: PRIMARY, fontSize: 22 }} />
          <div>
            <Input
              value={workflowName}
              onChange={e => setWorkflowName(e.target.value)}
              variant="borderless"
              style={{ fontSize: 18, fontWeight: 600, padding: 0, height: 28, width: 360 }}
              placeholder={t("agentWorkflow.saveModal.name")}
            />
            <div style={{ fontSize: 12, color: "#64748B" }}>
              {t("agentWorkflow.header.nodesEdges", { nodes: nodes.length, edges: edges.length })}
              {currentWfId && <Tag color="blue" style={{ marginLeft: 6 }}>{t("agentWorkflow.header.saved")}</Tag>}
            </div>
          </div>
        </div>
        <Space>
          <Tooltip title={isFullscreen ? t("agentWorkflow.header.fullscreenTooltipActive") : t("agentWorkflow.header.fullscreenTooltip")}>
            <Button icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={toggleFullscreen}>
              {isFullscreen ? t("agentWorkflow.header.exitFullscreen") : t("agentWorkflow.header.fullscreen")}
            </Button>
          </Tooltip>
          <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)} disabled={nodes.length === 0}>
            {currentWfId ? t("agentWorkflow.header.update") : t("agentWorkflow.header.save")}
          </Button>
        </Space>
      </div>

      {/* Three-column layout */}
      <div style={{ display: "flex", flex: 1, gap: 12, overflow: "hidden", position: "relative" }}>
        {/* Left column: node panel (PMBOK Agent library + Skill library) */}
        <div style={{ width: leftPanelOpen ? 260 : 0, flexShrink: 0, overflow: "hidden", transition: "width 0.2s ease", border: leftPanelOpen ? "1px solid #E2E8F0" : "none", borderRadius: 12, background: "#fff" }}>
          <div style={{ width: 260, height: "100%", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "10px 12px", borderBottom: "1px solid #E2E8F0", fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
              <PartitionOutlined style={{ color: PRIMARY }} /> {t("agentWorkflow.leftPanel.title")}
              <div style={{ flex: 1 }} />
              <Tooltip title={t("agentWorkflow.leftPanel.collapse")}>
                <Button type="text" size="small" icon={<LeftOutlined />} onClick={() => setLeftPanelOpen(false)} />
              </Tooltip>
            </div>
          <div style={{ padding: 8 }}>
            <Input
              prefix={<SearchOutlined />} allowClear placeholder={t("agentWorkflow.leftPanel.searchPlaceholder")}
              value={panelSearch} onChange={e => setPanelSearch(e.target.value)} size="small"
            />
          </div>
          <div style={{ overflow: "auto", flex: 1, padding: "0 8px 8px" }}>
            {(pmbokAgentsLoading || pmbokSkillsLoading) && (
              <div style={{ textAlign: "center", padding: 16 }}><Spin /></div>
            )}
            {/* ① PMBOK 5 process groups · Agent library */}
            <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", margin: "8px 4px 4px" }}>
              <PartitionOutlined /> {t("agentWorkflow.leftPanel.agentsTitle")}
            </div>
            {groupedAgents.map(g => (
              <div key={g.key} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: "#94A3B8", margin: "4px 0", fontWeight: 600 }}>
                  {t("agentWorkflow.leftPanel.groupCount", { group: g.key, count: g.items.length })}
                </div>
                {g.items.map(a => {
                  const m = resolvePmbokMeta(a, "agent");
                  return (
                    <PanelItem
                      key={a.id} label={a.name_cn || a.name || a.code || a.id} sub={a.code}
                      desc={a.summary} color={m.color} icon={m.icon}
                      onClick={() => addNodeFromPanel(a, "agent")}
                    />
                  );
                })}
              </div>
            ))}
            {/* ② Skill library (grouped by category) */}
            <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", margin: "8px 4px 4px" }}>
              <ThunderboltOutlined /> {t("agentWorkflow.leftPanel.skillsTitle")}
            </div>
            {groupedSkills.map(g => (
              <div key={g.key} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: "#94A3B8", margin: "4px 0", fontWeight: 600 }}>
                  {t("agentWorkflow.leftPanel.groupCount", { group: g.key, count: g.items.length })}
                </div>
                {g.items.map(s => {
                  const m = resolvePmbokMeta(s, "skill");
                  return (
                    <PanelItem
                      key={s.id} label={s.name_cn || s.name || s.code || s.id} sub={s.code}
                      desc={s.summary} color={m.color} icon={m.icon}
                      onClick={() => addNodeFromPanel(s, "skill")}
                    />
                  );
                })}
              </div>
            ))}
            {!pmbokAgentsLoading && !pmbokSkillsLoading && groupedAgents.length === 0 && groupedSkills.length === 0 && (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("agentWorkflow.leftPanel.noNodes")} style={{ margin: "16px 0" }} />
            )}
          </div>
          </div>
        </div>
        {!leftPanelOpen && (
          <Tooltip title={t("agentWorkflow.zoom.expandLeft")}>
            <div
              onClick={() => setLeftPanelOpen(true)}
              style={{ position: "absolute", top: 88, left: 8, zIndex: 5, cursor: "pointer",
                width: 26, height: 84, borderRadius: 10, background: "#fff", border: "1px solid #E2E8F0",
                boxShadow: "0 4px 14px rgba(15,23,42,0.12)", display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <RightOutlined style={{ color: PRIMARY, fontSize: 14 }} />
            </div>
          </Tooltip>
        )}

        {/* Middle column: toolbar (template dropdown) + canvas */}
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Select
              style={{ width: 280 }} placeholder={t("agentWorkflow.toolbar.templatePlaceholder")} loading={pmbokWorkflowsLoading}
              value={selectedTemplateId || undefined}
              onChange={(v) => { setSelectedTemplateId(v); loadWorkflowTemplate(v); }}
              options={pmbokWorkflows.map(w => ({
                value: w.id,
                label: `${w.name_cn || w.name || w.code || w.id}${w.node_count ? `（${w.node_count}）` : ""}`,
              }))}
            />
            <Button type="primary" icon={<PlayCircleOutlined />} loading={executing} onClick={handleRun}>
              {t("agentWorkflow.toolbar.run")}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleAutoLayout} disabled={nodes.length === 0}>
              {t("agentWorkflow.toolbar.autoLayout")}
            </Button>
            <Button icon={<ClearOutlined />} onClick={handleClear} disabled={nodes.length === 0}>
              {t("agentWorkflow.toolbar.clear")}
            </Button>
            <Button icon={<DeleteOutlined />} onClick={removeSelected} disabled={nodes.length === 0}>
              {t("agentWorkflow.toolbar.deleteSelected")}
            </Button>
            <div style={{ flex: 1 }} />
            <Progress percent={progress} size="small" style={{ width: 160 }}
              strokeColor={PRIMARY} status={executing ? "active" : "normal"} />
          </div>

          <Card
            size="small" style={{ flex: 1, borderRadius: 12, overflow: "hidden", minHeight: 360 }}
            bodyStyle={{ padding: 0, height: "100%" }}
          >
            <div style={{ position: "relative", width: "100%", height: "100%" }}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                nodeTypes={nodeTypes}
                onNodeClick={onNodeClick}
                onPaneClick={onPaneClick}
                onMove={(_e, z) => setZoomPct(Math.round(z * 100))}
                fitView
                minZoom={0.15}
                maxZoom={3}
                zoomOnScroll
                zoomOnDoubleClick
                proOptions={{ hideAttribution: true }}
                deleteKeyCode={["Backspace", "Delete"]}
              >
                <Background color="#E2E8F0" gap={16} />
                <MiniMap
                  nodeColor={(n: any) => (n.data?.color as string) || PRIMARY}
                  maskColor="rgba(241,245,249,0.6)"
                  style={{ borderRadius: 8 }}
                />
                {/* Floating control bar: zoom in/out/fit/fullscreen + zoom percent */}
                <div
                  style={{
                    position: "absolute", left: 12, bottom: 12, zIndex: 10,
                    display: "flex", alignItems: "center", gap: 4,
                    background: "#fff", boxShadow: "0 4px 16px rgba(15,23,42,0.12)",
                    borderRadius: 10, padding: "4px 8px",
                  }}
                >
                  <Tooltip title={t("agentWorkflow.zoom.out")}>
                    <Button size="small" type="text" icon={<ZoomOutOutlined />} onClick={handleZoomOut} />
                  </Tooltip>
                  <Text style={{ fontSize: 12, minWidth: 44, textAlign: "center" }} type="secondary">{zoomPct}%</Text>
                  <Tooltip title={t("agentWorkflow.zoom.in")}>
                    <Button size="small" type="text" icon={<ZoomInOutlined />} onClick={handleZoomIn} />
                  </Tooltip>
                  <Tooltip title={t("agentWorkflow.zoom.fit")}>
                    <Button size="small" type="text" icon={<CompassOutlined />} onClick={handleZoomFit} />
                  </Tooltip>
                  <Tooltip title={leftPanelOpen ? t("agentWorkflow.zoom.collapseLeft") : t("agentWorkflow.zoom.expandLeft")}>
                    <Button size="small" type="text" icon={<PartitionOutlined />}
                      style={{ opacity: leftPanelOpen ? 1 : 0.45, color: leftPanelOpen ? undefined : PRIMARY }}
                      onClick={() => setLeftPanelOpen(v => !v)} />
                  </Tooltip>
                  <Tooltip title={rightPanelOpen ? t("agentWorkflow.zoom.collapseRight") : t("agentWorkflow.zoom.expandRight")}>
                    <Button size="small" type="text" icon={<SettingOutlined />}
                      style={{ opacity: rightPanelOpen ? 1 : 0.45, color: rightPanelOpen ? undefined : PRIMARY }}
                      onClick={() => setRightPanelOpen(v => !v)} />
                  </Tooltip>
                  <Tooltip title={isFullscreen ? t("agentWorkflow.zoom.fullscreenOff") : t("agentWorkflow.zoom.fullscreenOn")}>
                    <Button size="small" type="text" icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={toggleFullscreen} />
                  </Tooltip>
                </div>
              </ReactFlow>
              {nodes.length === 0 && (
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                  <Empty description={t("agentWorkflow.canvas.empty")} />
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Right column: properties panel (ITTO of selected node) */}
        <div style={{ width: rightPanelOpen ? 300 : 0, flexShrink: 0, overflow: "hidden", transition: "width 0.2s ease", border: rightPanelOpen ? "1px solid #E2E8F0" : "none", borderRadius: 12, background: "#fff" }}>
          <div style={{ width: 300, height: "100%", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "10px 12px", borderBottom: "1px solid #E2E8F0", fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
            <SettingOutlined style={{ color: PRIMARY }} /> {t("agentWorkflow.rightPanel.title")}
            <div style={{ flex: 1 }} />
            <Tooltip title={t("agentWorkflow.rightPanel.collapse")}>
              <Button type="text" size="small" icon={<RightOutlined />} onClick={() => setRightPanelOpen(false)} />
            </Tooltip>
          </div>
          <div style={{ overflow: "auto", flex: 1, padding: 12 }}>
            {!selection && (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("agentWorkflow.rightPanel.empty")} style={{ margin: "24px 0" }} />
            )}
            {selection && nodeDetailLoading && (
              <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
            )}
            {selection && !nodeDetailLoading && nodeDetail && (
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Tag color={nodeDetail.kind === "gate" ? "orange" : nodeDetail.kind === "skill" ? "cyan" : "blue"}>
                    {nodeDetail.kind === "gate" ? t("agentWorkflow.rightPanel.kindGate") : nodeDetail.kind === "skill" ? t("agentWorkflow.rightPanel.kindSkill") : t("agentWorkflow.rightPanel.kindAgent")}
                  </Tag>
                  <Text code style={{ fontSize: 11 }}>{nodeDetail.type}</Text>
                </Space>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                  {selNode?.data.label || nodeDetail.type}
                </div>

                <Section title={t("agentWorkflow.rightPanel.note")}>
                  {nodeDetail.note
                    ? <div style={{ fontSize: 12, color: "#475569", whiteSpace: "pre-wrap" }}>{nodeDetail.note}</div>
                    : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>}
                </Section>

                {nodeDetail.kind === "skill" ? (
                  <Section title={t("agentWorkflow.rightPanel.definition")}>
                    {nodeDetail.definition
                      ? <div style={{ fontSize: 12, color: "#475569", whiteSpace: "pre-wrap" }}>{nodeDetail.definition}</div>
                      : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>}
                  </Section>
                ) : nodeDetail.kind === "gate" ? (
                  <Section title={t("agentWorkflow.rightPanel.description")}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{t("agentWorkflow.rightPanel.gateDesc")}</Text>
                  </Section>
                ) : (
                  <>
                    <Section title={t("agentWorkflow.rightPanel.inputs")}>{renderSlot(nodeDetail.itto?.inputs)}</Section>
                    <Section title={t("agentWorkflow.rightPanel.tools")}>{renderSlot(nodeDetail.itto?.tools)}</Section>
                    <Section title={t("agentWorkflow.rightPanel.outputs")}>{renderSlot(nodeDetail.itto?.outputs)}</Section>
                  </>
                )}

                <Button icon={<SettingOutlined />} style={{ marginTop: 12, width: "100%" }}
                  onClick={() => { if (selNode) setConfigNode(selNode); }}>
                  {t("agentWorkflow.rightPanel.config")}
                </Button>
              </div>
            )}
          </div>
          </div>
        </div>
        {!rightPanelOpen && (
          <Tooltip title={t("agentWorkflow.rightPanel.expand")}>
            <div
              onClick={() => setRightPanelOpen(true)}
              style={{ position: "absolute", top: 88, right: 8, zIndex: 5, cursor: "pointer",
                width: 26, height: 84, borderRadius: 10, background: "#fff", border: "1px solid #E2E8F0",
                boxShadow: "0 4px 14px rgba(15,23,42,0.12)", display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <LeftOutlined style={{ color: PRIMARY, fontSize: 14 }} />
            </div>
          </Tooltip>
        )}
      </div>

      {/* Node configuration drawer */}
      <Drawer
        title={configNode ? (
          <Space>
            <span style={{ color: configNode.data.color }}>{configNode.data.icon}</span>
            <span>{configNode.data.label}</span>
            <Tag color={configNode.data.color}>{configNode.data.agentType}</Tag>
          </Space>
        ) : t("agentWorkflow.config.title")}
        width={420}
        open={!!configNode}
        onClose={() => setConfigNode(null)}
        extra={<Button type="primary" onClick={() => {
          if (!configNode) return;
          const id = configNode.id;
          setNodes(nds => nds.map(n => n.id === id ? {
            ...n, data: { ...n.data, userInput: cfgUserInput, selectedTools: cfgTools, inputMapping: cfgMapping },
          } : n));
          message.success(t("agentWorkflow.config.saved"));
          setConfigNode(null);
        }}>{t("agentWorkflow.config.save")}</Button>}
      >
        {configNode && (
          <div>
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>{t("agentWorkflow.config.extraInput")}</Text>
            <Input.TextArea
              rows={3} value={cfgUserInput} onChange={e => setCfgUserInput(e.target.value)}
              placeholder={t("agentWorkflow.config.extraInputPlaceholder")}
            />

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
              {t("agentWorkflow.config.tools")}
            </Text>
            {slotLoading ? <Spin /> : (
              slotInfo.tools.length === 0
                ? <Text type="secondary" style={{ fontSize: 11 }}>{t("agentWorkflow.config.noTools")}</Text>
                : <Select
                    mode="multiple" allowClear style={{ width: "100%" }}
                    value={cfgTools} onChange={setCfgTools}
                    options={slotInfo.tools.map(tool => ({ value: tool.key, label: `${tool.label}${tool.optional ? t("agentWorkflow.config.optional") : ""}` }))}
                    placeholder={t("agentWorkflow.config.toolsPlaceholder")}
                  />
            )}

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
              {t("agentWorkflow.config.mapping")}
            </Text>
            {slotLoading ? <Spin /> : (
              <div>
                {upstreamOptions.length === 0 && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    t("agentWorkflow.config.noUpstream")
                  </Text>
                )}
                {upstreamOptions.length > 0 && slotInfo.inputs.length === 0 && (
                  <Text type="secondary" style={{ fontSize: 11 }}>{t("agentWorkflow.config.noSlots")}</Text>
                )}
                {slotInfo.inputs.map(slot => (
                  <div key={slot.key} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "#475569", marginBottom: 2 }}>
                      {slot.label}{slot.optional ? t("agentWorkflow.config.optional") : <Text type="danger" style={{ fontSize: 11 }}>{t("agentWorkflow.config.required")}</Text>}
                    </div>
                    <Select
                      size="small" style={{ width: "100%" }} allowClear
                      value={cfgMapping[slot.key] || undefined}
                      onChange={(v) => setCfgMapping(prev => {
                        const next = { ...prev };
                        if (v) next[slot.key] = v; else delete next[slot.key];
                        return next;
                      })}
                      options={upstreamOptions.map(o => ({ value: o.value, label: t("agentWorkflow.config.bindUpstream", { name: o.label }) }))}
                      placeholder={t("agentWorkflow.config.mappingPlaceholder")}
                    />
                  </div>
                ))}
              </div>
            )}

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>{t("agentWorkflow.config.outputs")}</Text>
            <Text type="secondary" style={{ fontSize: 11, display: "block", marginBottom: 8 }}>{t("agentWorkflow.config.outputsHint")}</Text>
            {slotLoading ? <Spin /> : (
              slotInfo.outputs.length === 0
                ? <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
                : <div style={{ maxHeight: 200, overflowY: "auto" }}>
                    {slotInfo.outputs.map((o, idx) => {
                      const isRequired = cfgOutputSlots[o.key] !== false && idx === 0; // First slot defaults to required
                      return (
                        <div key={o.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 8px", marginBottom: 4, background: isRequired ? "#F0FFF4" : "#FFF", border: `1px solid ${isRequired ? "#9AE6B4" : "#E2E8F0"}`, borderRadius: 6 }}>
                          <span style={{ fontSize: 12 }}>{o.label}</span>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            {isRequired && <Tag color="green" style={{ fontSize: 10, margin: 0 }}>{t("agentWorkflow.config.requiredTag")}</Tag>}
                            {!isRequired && idx > 0 && <Tag color="default" style={{ fontSize: 10, margin: 0 }}>{t("agentWorkflow.config.optionalTag")}</Tag>}
                            <Switch
                              size="small"
                              checked={isRequired}
                              onChange={(checked) => setCfgOutputSlots(prev => ({ ...prev, [o.key]: checked }))}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
            )}

            {currentNodeRun?.output_preview && (
              <>
                <div style={{ height: 12 }} />
                <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>{t("agentWorkflow.config.lastRun")}</Text>
                <div style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 10, fontSize: 11, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap", color: "#334155" }}>
                  {currentNodeRun.output_preview}
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>

      <Modal
        title={currentWfId ? t("agentWorkflow.saveModal.titleUpdate") : t("agentWorkflow.saveModal.titleCreate")}
        open={saveOpen} onOk={handleSave} onCancel={() => setSaveOpen(false)}
        okText={currentWfId ? t("agentWorkflow.saveModal.okUpdate") : t("agentWorkflow.saveModal.okCreate")} cancelText={t("common.cancel")}
      >
        <div style={{ marginBottom: 12 }}>
          <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>{t("agentWorkflow.saveModal.name")}</Text>
          <Input value={workflowName} onChange={e => setWorkflowName(e.target.value)} placeholder={t("agentWorkflow.saveModal.namePlaceholder")} />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>{t("agentWorkflow.saveModal.description")}</Text>
          <Input.TextArea rows={3} value={saveDesc} onChange={e => setSaveDesc(e.target.value)} placeholder={t("agentWorkflow.saveModal.descPlaceholder")} />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {currentWfId ? t("agentWorkflow.saveModal.willUpdate") : t("agentWorkflow.saveModal.willCreate", { count: nodes.length })}
          </Text>
        </div>
      </Modal>
    </div>
  );
};

const AgentWorkflow: React.FC = () => (
  <ReactFlowProvider>
    <WorkflowInner />
  </ReactFlowProvider>
);

export default AgentWorkflow;
