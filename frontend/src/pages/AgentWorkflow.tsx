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
import { workflowApi, agentApi, pmbokV3Api } from "../api";

const { Text } = Typography;
const PRIMARY = "#4F46E5";

// ─────────────────────────────────────────────────────────────────────────────
// 类型定义
// ─────────────────────────────────────────────────────────────────────────────

type NodeStatus = "idle" | "running" | "success" | "error";

interface AgentNodeData {
  agentType: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  status: NodeStatus;
  // 新增：节点级运行配置（支撑上游输出→下游输入的精确绑定）
  userInput: string;                 // 内联补充输入文本
  selectedTools: string[];           // 勾选的工具技术 key
  inputMapping: Record<string, string>; // {输入槽key: 上游节点id}
  // 新增：PMI 三层映射元数据（兼容旧结构，均为可选）
  nodeKind?: "agent" | "skill" | "gate";
  refId?: string;                    // 指向 agent / skill 的 id
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

/** prepare 端点返回的结构化 ITTO 槽位 */
interface SlotItem {
  key: string;
  label: string;
  optional: boolean;
  enabled: boolean;
  kind: string;
  exists?: boolean;
}

/** PMBOK V3 节点面板库条目（agent / skill） */
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

/** 属性面板选中的节点信息（快照，用于拉取 ITTO） */
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
// 图标 / 配色映射
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
// 自定义节点（含 Handle 连接点 + framer-motion 状态微动效 + 配置指示点）
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_META: Record<NodeStatus, { color: string; text: string; icon: React.ReactNode }> = {
  idle:    { color: "#94A3B8", text: "待运行", icon: <LoadingOutlined style={{ opacity: 0 }} /> },
  running: { color: "#F59E0B", text: "运行中", icon: <LoadingOutlined spin /> },
  success: { color: "#10B981", text: "成功",   icon: <CheckCircleOutlined /> },
  error:   { color: "#EF4444", text: "失败",   icon: <CloseCircleOutlined /> },
};

const StatusBadge: React.FC<{ status: NodeStatus }> = ({ status }) => {
  const m = STATUS_META[status];
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
          <StatusBadge status={status} />
        </div>
        <div style={{ fontSize: 10, color: "#64748B", marginTop: 4, lineHeight: 1.4 }}>
          {data.description}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
          <span style={{ fontSize: 9, color: "#94A3B8", fontFamily: "monospace" }}>
            {data.agentType}
          </span>
          {hasConfig(data) && (
            <Tooltip title="已配置输入/工具/槽位映射">
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

/** Gate（判断/分支）节点：橙色菱形风格，作为流程判断节点 */
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

// 通用分组工具
function groupBy<T>(arr: T[], key: (t: T) => string): { key: string; items: T[] }[] {
  const m = new Map<string, T[]>();
  for (const it of arr) {
    const k = key(it);
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(it);
  }
  return Array.from(m.entries()).map(([k, items]) => ({ key: k, items }));
}

// 左侧面板节点项
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

// 属性面板块
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
// 主页面（内层，使用 React Flow hooks）
// ─────────────────────────────────────────────────────────────────────────────

const WorkflowInner: React.FC = () => {
  const { message } = App.useApp();
  const { fitView, zoomIn, zoomOut, getZoom } = useReactFlow();

  const initial = useMemo(() => ({ nodes: [] as AgentNode[], edges: [] as Edge[] }), []);
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNodeData>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);

  const [workflowName, setWorkflowName] = useState("PMI 三层映射 · 工作流编排");
  const [executing, setExecuting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState<LogEntry[]>([]);

  // ── 全屏 / 悬浮展示 ─────────────────────────────────────────────
  // 全屏时整块工作流（节点面板 + 画布 + 属性面板）铺满屏幕，属性面板保持可用
  const rootRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoomPct, setZoomPct] = useState(100);
  // ── 侧栏抽屉（全屏时节点面板/属性面板可收起/展开，也可保持固定）──
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
  // 跟踪当前缩放百分比（节流）
  useEffect(() => {
    let raf = 0;
    const loop = () => { setZoomPct(Math.round(getZoom() * 100)); raf = requestAnimationFrame(loop); };
    if (isFullscreen) raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [isFullscreen, getZoom]);
  const handleZoomIn = useCallback(() => { zoomIn({ duration: 200 }); setZoomPct(Math.min(300, Math.round(getZoom() * 100) + 20)); }, [zoomIn, getZoom]);
  const handleZoomOut = useCallback(() => { zoomOut({ duration: 200 }); setZoomPct(Math.max(20, Math.round(getZoom() * 100) - 20)); }, [zoomOut, getZoom]);
  const handleZoomFit = useCallback(() => { fitView({ duration: 300, padding: 0.15 }); }, [fitView]);

  // 工作流保存（多租户，沿用 workflowApi）
  const [currentWfId, setCurrentWfId] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDesc, setSaveDesc] = useState("");

  // 节点配置抽屉
  const [configNode, setConfigNode] = useState<AgentNode | null>(null);
  const [slotInfo, setSlotInfo] = useState<{ inputs: SlotItem[]; tools: SlotItem[]; outputs: SlotItem[] }>({ inputs: [], tools: [], outputs: [] });
  const [cfgUserInput, setCfgUserInput] = useState("");
  const [cfgTools, setCfgTools] = useState<string[]>([]);
  const [cfgMapping, setCfgMapping] = useState<Record<string, string>>({});
  const [cfgOutputSlots, setCfgOutputSlots] = useState<Record<string, boolean>>({});
  const [slotLoading, setSlotLoading] = useState(false);

  // 运行结果（供节点抽屉展示输出）
  const [lastRun, setLastRun] = useState<any | null>(null);

  // PMBOK V3 节点面板库 + 工作流模板
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

  // 属性面板：当前选中节点 + 拉取的 ITTO 详情
  const [selection, setSelection] = useState<Selection | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);

  const addLog = useCallback((label: string, msg: string, level: LogEntry["level"]) => {
    setLog(prev => [...prev, {
      id: uid("log"), time: new Date().toLocaleTimeString(),
      label, message: msg, level,
    }]);
  }, []);

  // 加载 PMBOK V3 节点面板库 + 工作流模板（try/catch，失败不崩溃）
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
        // 接口异常时保持空列表，画布显示空提示
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

  // 过滤（按搜索词）
  const filteredAgents = useMemo(() => {
    const kw = panelSearch.trim().toLowerCase();
    return pmbokAgents.filter(a =>
      !kw || `${a.name_cn || ""} ${a.name || ""} ${a.code || ""} ${a.summary || ""}`.toLowerCase().includes(kw));
  }, [pmbokAgents, panelSearch]);
  const groupedAgents = useMemo(
    () => groupBy(filteredAgents, a => a.process_group || "未分组过程组"),
    [filteredAgents]);

  const filteredSkills = useMemo(() => {
    const kw = panelSearch.trim().toLowerCase();
    return pmbokSkills.filter(s =>
      !kw || `${s.name_cn || ""} ${s.name || ""} ${s.code || ""} ${s.summary || ""}`.toLowerCase().includes(kw));
  }, [pmbokSkills, panelSearch]);
  const groupedSkills = useMemo(
    () => groupBy(filteredSkills, s => s.category || "未分类"),
    [filteredSkills]);

  // ── 从左侧节点面板点击新增节点 ──
  const addNodeFromPanel = useCallback((item: PmbokAgentItem | PmbokSkillItem, kind: "agent" | "skill") => {
    const meta = resolvePmbokMeta(item, kind);
    const id = uid(kind === "agent" ? "agent" : "skill");
    const idx = nodes.length;
    const position = { x: 40 + (idx % 4) * 250, y: 40 + Math.floor(idx / 4) * 150 };
    const label = (item as any).name_cn || (item as any).name || (item as any).code || "节点";
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
    message.success(`已添加「${label}」节点`);
  }, [nodes.length, setNodes, message, resolvePmbokMeta]);

  // ── 载入工作流模板：把 nodes 渲染成画布节点 + 按 seq 连边 ──
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
              agentType: n.ref || "gate", label: n.name || "判断", description: "",
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
      // 尝试使用ITTO边，如果API没有edges字段则回退到线性连接
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
      // 如果没有匹配到边，使用线性连接作为降级
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
      message.success(`已载入模板「${wf?.name_cn || wf?.name || wf?.code || ""}」`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "载入工作流模板失败");
    }
  }, [setNodes, setEdges, message, fitView, resolvePmbokMeta]);

  // ── 连线（边 = 依赖；支持扇入/扇出）──
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

  // -- 页面加载后自动载入第一个工作流模板 --
  useEffect(() => {
    if (pmbokWorkflows.length > 0 && nodes.length === 0 && !autoLoadedRef.current) {
      autoLoadedRef.current = true;
      setAutoLoaded(true);
      const fullProcess = pmbokWorkflows.find(w => w.id === "pmbok_full_process"); const firstId = fullProcess ? fullProcess.id : pmbokWorkflows[0].id;
      setSelectedTemplateId(firstId);
      loadWorkflowTemplate(firstId);
    }
  }, [pmbokWorkflows, nodes.length]);



  // ── 属性面板：根据 selection 拉取 ITTO / definition ──
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
    message.info("画布已清空");
  }, [setNodes, setEdges, message]);

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
    if (nodes.length === 0) { message.warning("请先添加工作流节点"); return; }
    setExecuting(true);
    setProgress(0);
    setLog([]);
    setLastRun(null);
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, status: "idle" } })));

    const steps = buildSteps();
    const nodeLabelById = new Map(nodes.map(n => [n.id, n.data.label]));
    addLog("工作流", `提交执行，共 ${steps.length} 个节点（异步 DAG 调度）`, "info");

    let runId: string | undefined;
    try {
      const res: any = await workflowApi.execute({ steps });
      runId = res?.run_id;
      if (!runId) throw new Error("后端未返回 run_id");
      addLog("工作流", `已提交，run_id=${runId.slice(0, 8)}…`, "info");
    } catch (e: any) {
      addLog("工作流", `提交失败: ${e?.response?.data?.detail || e?.message}`, "error");
      message.error("提交执行失败");
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
          if ((e as any)?.response?.status === 404) { addLog("工作流", "运行记录已过期（持久化文件可能已被清理）", "error"); break; }
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
            if (rr.status === "failed") { failed++; addLog(disp, `失败: ${rr.error || "未知错误"}`, "error"); }
            else addLog(disp, "执行完成", "success");
            const out = rr.output_preview as string | undefined;
            if (out) addLog(disp, `输出摘要: ${out.slice(0, 160)}${out.length > 160 ? "…" : ""}`, "info");
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
      addLog("工作流", `执行结束，状态: ${fstatus}${failed ? `，失败 ${failed} 步` : ""}`, failed ? "error" : "success");
      message.success(`工作流执行完成（状态：${fstatus}）`);
      setTimeout(() => fitView({ padding: 0.2 }), 60);
    } catch (e: any) {
      addLog("工作流", `轮询异常: ${e?.message || "超时"}`, "error");
      message.error("运行查询失败");
    } finally {
      setExecuting(false);
    }
  }, [nodes, edges, setNodes, message, addLog, fitView, buildSteps, lastRun]);

  // ── 删除选中的边/节点 ──
  const removeSelected = useCallback(() => {
    setNodes(nds => nds.filter(n => !n.selected));
    setEdges(eds => eds.filter(e => !e.selected));
  }, [setNodes, setEdges]);

  // ── 保存 / 更新工作流 ──
  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) { message.warning("请输入工作流名称"); return; }
    const steps = buildSteps();
    const payload = { name: workflowName, description: saveDesc, steps };
    try {
      if (currentWfId) {
        await workflowApi.update(currentWfId, payload);
        message.success("工作流已更新");
      } else {
        const res: any = await workflowApi.create(payload);
        setCurrentWfId(res?.workflow?.id || res?.id || null);
        message.success("工作流已保存");
      }
      setSaveOpen(false);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "保存失败");
    }
  }, [workflowName, saveDesc, currentWfId, message, buildSteps]);

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
      {/* Header：工作流名称 + 保存 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <ApartmentOutlined style={{ color: PRIMARY, fontSize: 22 }} />
          <div>
            <Input
              value={workflowName}
              onChange={e => setWorkflowName(e.target.value)}
              variant="borderless"
              style={{ fontSize: 18, fontWeight: 600, padding: 0, height: 28, width: 360 }}
              placeholder="工作流名称"
            />
            <div style={{ fontSize: 12, color: "#64748B" }}>
              {nodes.length} 个节点 · {edges.length} 条数据流连线
              {currentWfId && <Tag color="blue" style={{ marginLeft: 6 }}>已保存</Tag>}
            </div>
          </div>
        </div>
        <Space>
          <Tooltip title={isFullscreen ? "退出全屏 (Esc)" : "全屏展示（属性面板可用）"}>
            <Button icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={toggleFullscreen}>
              {isFullscreen ? "退出全屏" : "全屏"}
            </Button>
          </Tooltip>
          <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)} disabled={nodes.length === 0}>
            {currentWfId ? "更新" : "保存"}
          </Button>
        </Space>
      </div>

      {/* 三栏布局 */}
      <div style={{ display: "flex", flex: 1, gap: 12, overflow: "hidden", position: "relative" }}>
        {/* 左栏：节点面板（PMBOK Agent 库 + Skill 库） */}
        <div style={{ width: leftPanelOpen ? 260 : 0, flexShrink: 0, overflow: "hidden", transition: "width 0.2s ease", border: leftPanelOpen ? "1px solid #E2E8F0" : "none", borderRadius: 12, background: "#fff" }}>
          <div style={{ width: 260, height: "100%", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "10px 12px", borderBottom: "1px solid #E2E8F0", fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
              <PartitionOutlined style={{ color: PRIMARY }} /> 节点面板
              <div style={{ flex: 1 }} />
              <Tooltip title="收起面板">
                <Button type="text" size="small" icon={<LeftOutlined />} onClick={() => setLeftPanelOpen(false)} />
              </Tooltip>
            </div>
          <div style={{ padding: 8 }}>
            <Input
              prefix={<SearchOutlined />} allowClear placeholder="搜索 Agent / Skill"
              value={panelSearch} onChange={e => setPanelSearch(e.target.value)} size="small"
            />
          </div>
          <div style={{ overflow: "auto", flex: 1, padding: "0 8px 8px" }}>
            {(pmbokAgentsLoading || pmbokSkillsLoading) && (
              <div style={{ textAlign: "center", padding: 16 }}><Spin /></div>
            )}
            {/* ① PMBOK 5 大过程组 · Agent 库 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", margin: "8px 4px 4px" }}>
              <PartitionOutlined /> PMBOK 5 大过程组 · Agent
            </div>
            {groupedAgents.map(g => (
              <div key={g.key} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: "#94A3B8", margin: "4px 0", fontWeight: 600 }}>
                  {g.key}（{g.items.length}）
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
            {/* ② Skill 库（按 category 分组） */}
            <div style={{ fontSize: 12, fontWeight: 600, color: "#475569", margin: "8px 4px 4px" }}>
              <ThunderboltOutlined /> Skill 库
            </div>
            {groupedSkills.map(g => (
              <div key={g.key} style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: "#94A3B8", margin: "4px 0", fontWeight: 600 }}>
                  {g.key}（{g.items.length}）
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
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无可用节点" style={{ margin: "16px 0" }} />
            )}
          </div>
          </div>
        </div>
        {!leftPanelOpen && (
          <Tooltip title="展开节点面板">
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

        {/* 中栏：工具栏（模板下拉）+ 画布 */}
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Select
              style={{ width: 280 }} placeholder="选择工作流模板" loading={pmbokWorkflowsLoading}
              value={selectedTemplateId || undefined}
              onChange={(v) => { setSelectedTemplateId(v); loadWorkflowTemplate(v); }}
              options={pmbokWorkflows.map(w => ({
                value: w.id,
                label: `${w.name_cn || w.name || w.code || w.id}${w.node_count ? `（${w.node_count}）` : ""}`,
              }))}
            />
            <Button type="primary" icon={<PlayCircleOutlined />} loading={executing} onClick={handleRun}>
              运行工作流
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleAutoLayout} disabled={nodes.length === 0}>
              自动布局
            </Button>
            <Button icon={<ClearOutlined />} onClick={handleClear} disabled={nodes.length === 0}>
              清空
            </Button>
            <Button icon={<DeleteOutlined />} onClick={removeSelected} disabled={nodes.length === 0}>
              删除选中
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
                {/* 悬浮控制条：放大/缩小/适应/全屏 + 缩放百分比 */}
                <div
                  style={{
                    position: "absolute", left: 12, bottom: 12, zIndex: 10,
                    display: "flex", alignItems: "center", gap: 4,
                    background: "#fff", boxShadow: "0 4px 16px rgba(15,23,42,0.12)",
                    borderRadius: 10, padding: "4px 8px",
                  }}
                >
                  <Tooltip title="缩小">
                    <Button size="small" type="text" icon={<ZoomOutOutlined />} onClick={handleZoomOut} />
                  </Tooltip>
                  <Text style={{ fontSize: 12, minWidth: 44, textAlign: "center" }} type="secondary">{zoomPct}%</Text>
                  <Tooltip title="放大">
                    <Button size="small" type="text" icon={<ZoomInOutlined />} onClick={handleZoomIn} />
                  </Tooltip>
                  <Tooltip title="适应画布">
                    <Button size="small" type="text" icon={<CompassOutlined />} onClick={handleZoomFit} />
                  </Tooltip>
                  <Tooltip title={leftPanelOpen ? "收起节点面板" : "展开节点面板"}>
                    <Button size="small" type="text" icon={<PartitionOutlined />}
                      style={{ opacity: leftPanelOpen ? 1 : 0.45, color: leftPanelOpen ? undefined : PRIMARY }}
                      onClick={() => setLeftPanelOpen(v => !v)} />
                  </Tooltip>
                  <Tooltip title={rightPanelOpen ? "收起属性面板" : "展开属性面板"}>
                    <Button size="small" type="text" icon={<SettingOutlined />}
                      style={{ opacity: rightPanelOpen ? 1 : 0.45, color: rightPanelOpen ? undefined : PRIMARY }}
                      onClick={() => setRightPanelOpen(v => !v)} />
                  </Tooltip>
                  <Tooltip title={isFullscreen ? "退出全屏 (Esc)" : "全屏展示（属性面板可用）"}>
                    <Button size="small" type="text" icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={toggleFullscreen} />
                  </Tooltip>
                </div>
              </ReactFlow>
              {nodes.length === 0 && (
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                  <Empty description="画布为空：从左侧节点面板添加，或选择上方工作流模板" />
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* 右栏：属性面板（选中节点的 ITTO） */}
        <div style={{ width: rightPanelOpen ? 300 : 0, flexShrink: 0, overflow: "hidden", transition: "width 0.2s ease", border: rightPanelOpen ? "1px solid #E2E8F0" : "none", borderRadius: 12, background: "#fff" }}>
          <div style={{ width: 300, height: "100%", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "10px 12px", borderBottom: "1px solid #E2E8F0", fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
            <SettingOutlined style={{ color: PRIMARY }} /> 属性面板
            <div style={{ flex: 1 }} />
            <Tooltip title="收起面板">
              <Button type="text" size="small" icon={<RightOutlined />} onClick={() => setRightPanelOpen(false)} />
            </Tooltip>
          </div>
          <div style={{ overflow: "auto", flex: 1, padding: 12 }}>
            {!selection && (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击画布节点查看 ITTO 属性" style={{ margin: "24px 0" }} />
            )}
            {selection && nodeDetailLoading && (
              <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
            )}
            {selection && !nodeDetailLoading && nodeDetail && (
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Tag color={nodeDetail.kind === "gate" ? "orange" : nodeDetail.kind === "skill" ? "cyan" : "blue"}>
                    {nodeDetail.kind === "gate" ? "判断节点 Gate" : nodeDetail.kind === "skill" ? "Skill" : "Agent"}
                  </Tag>
                  <Text code style={{ fontSize: 11 }}>{nodeDetail.type}</Text>
                </Space>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                  {selNode?.data.label || nodeDetail.type}
                </div>

                <Section title="备注 Note">
                  {nodeDetail.note
                    ? <div style={{ fontSize: 12, color: "#475569", whiteSpace: "pre-wrap" }}>{nodeDetail.note}</div>
                    : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>}
                </Section>

                {nodeDetail.kind === "skill" ? (
                  <Section title="定义 Definition">
                    {nodeDetail.definition
                      ? <div style={{ fontSize: 12, color: "#475569", whiteSpace: "pre-wrap" }}>{nodeDetail.definition}</div>
                      : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>}
                  </Section>
                ) : nodeDetail.kind === "gate" ? (
                  <Section title="说明">
                    <Text type="secondary" style={{ fontSize: 11 }}>Gate 为流程判断 / 分支节点，连接上下游以控制流向。</Text>
                  </Section>
                ) : (
                  <>
                    <Section title="输入 Inputs">{renderSlot(nodeDetail.itto?.inputs)}</Section>
                    <Section title="工具技术 Tools">{renderSlot(nodeDetail.itto?.tools)}</Section>
                    <Section title="输出 Outputs">{renderSlot(nodeDetail.itto?.outputs)}</Section>
                  </>
                )}

                <Button icon={<SettingOutlined />} style={{ marginTop: 12, width: "100%" }}
                  onClick={() => { if (selNode) setConfigNode(selNode); }}>
                  配置该节点
                </Button>
              </div>
            )}
          </div>
          </div>
        </div>
        {!rightPanelOpen && (
          <Tooltip title="展开属性面板">
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

      {/* 节点配置抽屉 */}
      <Drawer
        title={configNode ? (
          <Space>
            <span style={{ color: configNode.data.color }}>{configNode.data.icon}</span>
            <span>{configNode.data.label}</span>
            <Tag color={configNode.data.color}>{configNode.data.agentType}</Tag>
          </Space>
        ) : "节点配置"}
        width={420}
        open={!!configNode}
        onClose={() => setConfigNode(null)}
        extra={<Button type="primary" onClick={() => {
          if (!configNode) return;
          const id = configNode.id;
          setNodes(nds => nds.map(n => n.id === id ? {
            ...n, data: { ...n.data, userInput: cfgUserInput, selectedTools: cfgTools, inputMapping: cfgMapping },
          } : n));
          message.success("节点配置已保存");
          setConfigNode(null);
        }}>保存配置</Button>}
      >
        {configNode && (
          <div>
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>补充输入（内联文本）</Text>
            <Input.TextArea
              rows={3} value={cfgUserInput} onChange={e => setCfgUserInput(e.target.value)}
              placeholder="可选：作为该 Agent 的内联补充输入，与上游输出拼接后一起喂入"
            />

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
              工具技术（selected_tools）
            </Text>
            {slotLoading ? <Spin /> : (
              slotInfo.tools.length === 0
                ? <Text type="secondary" style={{ fontSize: 11 }}>该 Agent 无可选工具技术</Text>
                : <Select
                    mode="multiple" allowClear style={{ width: "100%" }}
                    value={cfgTools} onChange={setCfgTools}
                    options={slotInfo.tools.map(t => ({ value: t.key, label: `${t.label}${t.optional ? "（可选）" : ""}` }))}
                    placeholder="勾选工具技术（空=全部）"
                  />
            )}

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>
              输入槽位映射（input_mapping）
            </Text>
            {slotLoading ? <Spin /> : (
              <div>
                {upstreamOptions.length === 0 && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    该节点暂无上游（未连线）。不映射时，运行时将自动合并全部上游输出；无上游则仅用内联输入。
                  </Text>
                )}
                {upstreamOptions.length > 0 && slotInfo.inputs.length === 0 && (
                  <Text type="secondary" style={{ fontSize: 11 }}>该 Agent 无结构化输入槽位，无需映射（自动合并全部上游输出）。</Text>
                )}
                {slotInfo.inputs.map(slot => (
                  <div key={slot.key} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 11, color: "#475569", marginBottom: 2 }}>
                      {slot.label}{slot.optional ? "（可选）" : <Text type="danger" style={{ fontSize: 11 }}>（必填）</Text>}
                    </div>
                    <Select
                      size="small" style={{ width: "100%" }} allowClear
                      value={cfgMapping[slot.key] || undefined}
                      onChange={(v) => setCfgMapping(prev => {
                        const next = { ...prev };
                        if (v) next[slot.key] = v; else delete next[slot.key];
                        return next;
                      })}
                      options={upstreamOptions.map(o => ({ value: o.value, label: `绑定上游：${o.label}` }))}
                      placeholder="不绑定（默认：自动合并全部上游输出）"
                    />
                  </div>
                ))}
              </div>
            )}

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>输出槽位</Text>
            <Text type="secondary" style={{ fontSize: 11, display: "block", marginBottom: 8 }}>勾选"必选"表示该输出必须包含在结果中，未勾选则为可选输出。</Text>
            {slotLoading ? <Spin /> : (
              slotInfo.outputs.length === 0
                ? <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
                : <div style={{ maxHeight: 200, overflowY: "auto" }}>
                    {slotInfo.outputs.map((o, idx) => {
                      const isRequired = cfgOutputSlots[o.key] !== false && idx === 0; // 第一个默认必选
                      return (
                        <div key={o.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 8px", marginBottom: 4, background: isRequired ? "#F0FFF4" : "#FFF", border: `1px solid ${isRequired ? "#9AE6B4" : "#E2E8F0"}`, borderRadius: 6 }}>
                          <span style={{ fontSize: 12 }}>{o.label}</span>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            {isRequired && <Tag color="green" style={{ fontSize: 10, margin: 0 }}>必选</Tag>}
                            {!isRequired && idx > 0 && <Tag color="default" style={{ fontSize: 10, margin: 0 }}>可选</Tag>}
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
                <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>最近运行输出（摘要）</Text>
                <div style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 10, fontSize: 11, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap", color: "#334155" }}>
                  {currentNodeRun.output_preview}
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>

      <Modal
        title={currentWfId ? "更新工作流" : "保存工作流"}
        open={saveOpen} onOk={handleSave} onCancel={() => setSaveOpen(false)}
        okText={currentWfId ? "更新" : "保存"} cancelText="取消"
      >
        <div style={{ marginBottom: 12 }}>
          <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>名称 *</Text>
          <Input value={workflowName} onChange={e => setWorkflowName(e.target.value)} placeholder="例如：项目健康检查" />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>描述</Text>
          <Input.TextArea rows={3} value={saveDesc} onChange={e => setSaveDesc(e.target.value)} placeholder="描述工作流用途…" />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {currentWfId ? "将更新当前工作流" : `将保存 ${nodes.length} 个节点的工作流定义`}
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
