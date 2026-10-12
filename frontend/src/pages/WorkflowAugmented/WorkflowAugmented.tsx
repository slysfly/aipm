/**
 * AIPM \u667a\u80fd\u5de5\u4f5c\u6d41\u7f16\u6392\u589e\u5f3a\u7248\uff08\u6d4b\u8bd5\uff09
 * \u5b8c\u5168\u5bf9\u9f50 AgentWorkflow \u67b6\u6784\uff0c\u4f7f\u7528\u7edf\u4e00\u6ce8\u518c\u4e2d\u5fc3 + \u540e\u7aefAPI
 */

import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  Card, Typography, Button, Space, App, Tag, Modal, Input,
  Select, Progress, Empty, List, Popconfirm, Spin, Segmented, Drawer, Tooltip,
} from 'antd';
import {
  PlayCircleOutlined, SaveOutlined, DeleteOutlined,
  ReloadOutlined, ApartmentOutlined, PlusOutlined,
  LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined,
  FolderOpenOutlined, ThunderboltOutlined,
  BarChartOutlined, WarningOutlined, RobotOutlined, SafetyOutlined,
  AimOutlined, FileTextOutlined, FileDoneOutlined, ClearOutlined,
  PartitionOutlined, CompassOutlined, NodeIndexOutlined,
  HeartOutlined, BulbOutlined, SearchOutlined, SettingOutlined,
  HistoryOutlined, SwapOutlined, EyeOutlined,
  DashboardOutlined, ProjectOutlined, ProfileOutlined, LayoutOutlined,
  FundProjectionScreenOutlined, AlertOutlined, SwapOutlined as SwapIcon,
  DollarOutlined, FlagOutlined, CalendarOutlined, BranchesOutlined,
  ApiOutlined, LinkOutlined, BellOutlined, CloudServerOutlined,
  UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import {
  ReactFlow, Background, Controls, MiniMap, ReactFlowProvider,
  useNodesState, useEdgesState, addEdge, Handle, Position,
  useReactFlow, MarkerType,
  type Node, type Edge, type NodeProps, type Connection,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { motion } from 'framer-motion';
import { workflowApi, agentApi } from '../../api';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;
const PRIMARY = '#4F46E5';

// ─────────────────────────────────────────────────────────────────────────────
// \u7c7b\u578b\u5b9a\u4e49
// ─────────────────────────────────────────────────────────────────────────────

type NodeStatus = 'idle' | 'running' | 'success' | 'error';

interface AgentNodeData {
  agentType: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  status: NodeStatus;
  userInput: string;
  selectedTools: string[];
  inputMapping: Record<string, string>;
}

type AgentNode = Node<AgentNodeData>;

interface RegistryAgentItem {
  id: string;
  name: string;
  name_en: string;
  kind: string;
  category: string;
  source: string;
  type: string;
  icon: string;
  color: string;
  description: string;
  accuracy: number | null;
  tags: string[];
  inputHint: string;
  extra?: {
    process_group?: string;
    knowledge_area?: string;
    inputs?: string[];
    tools?: string[];
    outputs?: string[];
    v8?: string;
  };
}

interface SlotItem {
  key: string;
  label: string;
  optional: boolean;
  enabled: boolean;
  kind: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// \u56fe\u6807\u6620\u5c04
// ─────────────────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<any>> = {
  FileTextOutlined, BarChartOutlined, WarningOutlined, RobotOutlined, ThunderboltOutlined,
  SafetyOutlined, AimOutlined, FileDoneOutlined, HeartOutlined, BulbOutlined,
  PartitionOutlined, CompassOutlined, NodeIndexOutlined,
};

const CAT_ICON: Record<string, React.ComponentType<any>> = {
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0036\u7248\u00b7\u0034\u0039\u8fc7\u7a0b': PartitionOutlined,
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0038\u7248\u00b7\u539f\u5219': CompassOutlined,
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0038\u7248\u00b7\u7ee9\u6548\u57df': ApartmentOutlined,
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0038\u7248\u00b7\u88c1\u526a': NodeIndexOutlined,
  '\u0043\u0050\u004d\u0041\u0049\u00b7\u0041\u0049\u9879\u76ee\u7ba1\u7406\u9636\u6bb5': RobotOutlined,
  '\u0043\u0050\u004d\u0041\u0049\u00b7\u53ef\u4fe1\u0041\u0049\u6846\u67b6': SafetyOutlined,
  '\u9886\u57df\u5206\u6790': ThunderboltOutlined,
};

const CAT_COLOR: Record<string, string> = {
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0036\u7248\u00b7\u0034\u0039\u8fc7\u7a0b': '#4F46E5',
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0038\u7248\u00b7\u539f\u5219': '#10B981',
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0038\u7248\u00b7\u7ee9\u6548\u57df': '#6366F1',
  '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0038\u7248\u00b7\u88c1\u526a': '#06B6D4',
  '\u0043\u0050\u004d\u0041\u0049\u00b7\u0041\u0049\u9879\u76ee\u7ba1\u7406\u9636\u6bb5': '#F59E0B',
  '\u0043\u0050\u004d\u0041\u0049\u00b7\u53ef\u4fe1\u0041\u0049\u6846\u67b6': '#EF4444',
  '\u9886\u57df\u5206\u6790': '#4F46E5',
};

const STATUS_META: Record<NodeStatus, { color: string; text: string; icon: React.ReactNode }> = {
  idle:    { color: '#94A3B8', text: '\u5f85\u8fd0\u884c', icon: <LoadingOutlined style={{ opacity: 0 }} /> },
  running: { color: '#F59E0B', text: '\u8fd0\u884c\u4e2d', icon: <LoadingOutlined spin /> },
  success: { color: '#10B981', text: '\u6210\u529f',   icon: <CheckCircleOutlined /> },
  error:   { color: '#EF4444', text: '\u5931\u8d25',   icon: <CloseCircleOutlined /> },
};

// ─────────────────────────────────────────────────────────────────────────────
// \u8f85\u52a9\u51fd\u6570
// ─────────────────────────────────────────────────────────────────────────────

let _counter = 0;
const uid = (prefix: string) => `${prefix}_${Date.now()}_${_counter++}`;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

// ─────────────────────────────────────────────────────────────────────────────
// \u81ea\u5b9a\u4e49\u8282\u70b9\u7ec4\u4ef6
// ─────────────────────────────────────────────────────────────────────────────

const AgentNodeView: React.FC<NodeProps<AgentNodeData>> = ({ data, selected }) => {
  const status = data.status;
  const ring =
    status === 'idle' ? (selected ? data.color : '#E2E8F0')
      : status === 'running' ? '#F59E0B'
      : status === 'success' ? '#10B981'
      : '#EF4444';

  const hasConfig = !!(data.userInput && data.userInput.trim()) ||
    (data.selectedTools && data.selectedTools.length > 0) ||
    (data.inputMapping && Object.keys(data.inputMapping).length > 0);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{
        opacity: 1,
        scale: status === 'running' ? 1.04 : 1,
        boxShadow:
          status === 'running' ? '0 0 0 4px rgba(245,158,11,0.30)'
          : status === 'success' ? '0 0 0 3px rgba(16,185,129,0.28)'
          : status === 'error' ? '0 0 0 3px rgba(239,68,68,0.28)'
          : '0 2px 10px rgba(0,0,0,0.08)',
      }}
      transition={{ type: 'spring', stiffness: 260, damping: 20 }}
      style={{
        width: 196, borderRadius: 12, background: '#fff',
        border: `1.5px solid ${ring}`,
      }}
    >
      <Handle type="target" position={Position.Left}
        style={{ background: data.color, width: 10, height: 10, border: '2px solid #fff' }} />
      <div style={{ padding: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ color: data.color, fontSize: 18 }}>{data.icon}</span>
          <Text style={{ fontSize: 12, fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {data.label}
          </Text>
          <StatusBadge status={status} />
        </div>
        <Text type="secondary" style={{ fontSize: 10, display: 'block', lineHeight: 1.4 }}>
          {data.description}
        </Text>
        {hasConfig && (
          <div style={{ marginTop: 6, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            {data.userInput && <Tag color="blue" style={{ fontSize: 9, padding: '0 4px' }}>\u8f93\u5165</Tag>}
            {data.selectedTools.length > 0 && <Tag color="purple" style={{ fontSize: 9, padding: '0 4px' }}>\u5de5\u5177</Tag>}
            {Object.keys(data.inputMapping).length > 0 && <Tag color="orange" style={{ fontSize: 9, padding: '0 4px' }}>\u6620\u5c04</Tag>}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right}
        style={{ background: data.color, width: 10, height: 10, border: '2px solid #fff' }} />
    </motion.div>
  );
};

const StatusBadge: React.FC<{ status: NodeStatus }> = ({ status }) => {
  const m = STATUS_META[status];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 10, color: m.color, fontWeight: 600,
      background: `${m.color}1A`, padding: '2px 6px', borderRadius: 8,
    }}>
      {m.icon}{m.text}
    </span>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// \u5185\u90e8\u7ec4\u4ef6\uff08\u9700\u8981 ReactFlowProvider\uff09
// ─────────────────────────────────────────────────────────────────────────────

const WorkflowInner: React.FC = () => {
  const { message } = App.useApp();
  const { t } = useTranslation('workflowAugmented');
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { screenToFlowPosition } = useReactFlow();

  // Agent\u6ce8\u518c\u4e2d\u5fc3
  const [registry, setRegistry] = useState<RegistryAgentItem[]>([]);
  const [regLoading, setRegLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'domain' | 'pmbok'>('all');
  const [catFilter, setCatFilter] = useState('all');
  const [kaFilter, setKaFilter] = useState('all');

  // \u5de5\u4f5c\u6d41\u72b6\u6001
  const [workflowName, setWorkflowName] = useState('');
  const [currentWfId, setCurrentWfId] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDesc, setSaveDesc] = useState('');

  // \u6267\u884c\u72b6\u6001
  const [executing, setExecuting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [lastRun, setLastRun] = useState<any>(null);
  const [log, setLog] = useState<LogEntry[]>([]);

  // \u8282\u70b9\u914d\u7f6e
  const [configNode, setConfigNode] = useState<AgentNode | null>(null);
  const [cfgUserInput, setCfgUserInput] = useState('');
  const [cfgTools, setCfgTools] = useState<string[]>([]);
  const [cfgMapping, setCfgMapping] = useState<Record<string, string>>({});
  const [slotInfo, setSlotInfo] = useState({ inputs: [], tools: [], outputs: [] });
  const [slotLoading, setSlotLoading] = useState(false);

  // \u5de5\u4f5c\u6d41\u5e93
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loadingLib, setLoadingLib] = useState(false);

  // \u8fd0\u884c\u5386\u53f2
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyList, setHistoryList] = useState<any[]>([]);
  const [historyDetail, setHistoryDetail] = useState<any>(null);

  // \u5206\u7c7b\u548c\u77e5\u8bc6\u9886\u57df
  const categories = useMemo(() => {
    const cats = new Set(registry.map(a => a.category).filter(Boolean));
    return ['all', ...Array.from(cats)];
  }, [registry]);

  const knowledgeAreas = useMemo(() => {
    const areas = new Set(
      registry
        .filter(a => a.category === '\u0050\u004d\u0042\u004f\u004b\u7b2c\u0036\u7248\u00b7\u0034\u0039\u8fc7\u7a0b')
        .map(a => a.extra?.knowledge_area)
        .filter(Boolean)
    );
    return Array.from(areas);
  }, [registry]);

  // \u5de5\u5177\u680f\u8fc7\u6ee4\u540e\u7684Agent\u5217\u8868
  const toolbox = useMemo(() => {
    let list = registry;
    if (sourceFilter === 'domain') list = list.filter(a => a.source === 'domain');
    if (sourceFilter === 'pmbok') list = list.filter(a => a.source === 'pmbok');
    if (catFilter !== 'all') list = list.filter(a => a.category === catFilter);
    if (kaFilter !== 'all') list = list.filter(a => a.extra?.knowledge_area === kaFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(a =>
        a.name.toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q) ||
        a.description?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [registry, sourceFilter, catFilter, kaFilter, search]);

  // \u89e3\u6790Agent\u5143\u6570\u636e
  const resolveMeta = useCallback((a: RegistryAgentItem) => {
    const IconC = ICON_MAP[a.icon] || RobotOutlined;
    const color = a.color || CAT_COLOR[a.category] || PRIMARY;
    return { icon: IconC, color };
  }, []);

  // \u52a0\u8f7d\u6ce8\u518c\u4e2d\u5fc3
  const loadRegistry = useCallback(async () => {
    setRegLoading(true);
    try {
      const r: any = await agentApi.registry();
      setRegistry(Array.isArray(r) ? r : (r?.agents || []));
    } catch (e: any) {
      console.error('Failed to load registry:', e);
      setRegistry([]);
    } finally {
      setRegLoading(false);
    }
  }, []);

  // \u52a0\u8f7d\u5de5\u4f5c\u6d41\u5e93
  const loadLibrary = useCallback(async () => {
    setLoadingLib(true);
    try {
      const r: any = await workflowApi.list();
      setWorkflows(r?.items || r || []);
    } catch (e: any) {
      console.error('Failed to load workflows:', e);
      setWorkflows([]);
    } finally {
      setLoadingLib(false);
    }
  }, []);

  // \u6dfb\u52a0\u8282\u70b9
  const addAgentNode = useCallback((agent: RegistryAgentItem) => {
    const { icon, color } = resolveMeta(agent);
    const node: AgentNode = {
      id: uid('node'),
      type: 'workflow',
      position: screenToFlowPosition({ x: 100 + Math.random() * 200, y: 100 + Math.random() * 200 }),
      data: {
        agentType: agent.id,
        label: agent.name,
        description: agent.description || agent.category,
        icon: React.createElement(icon),
        color,
        status: 'idle' as NodeStatus,
        userInput: '',
        selectedTools: [],
        inputMapping: {},
      },
    };
    setNodes(nds => [...nds, node]);
  }, [screenToFlowPosition, resolveMeta, setNodes]);

  // \u8fde\u63a5\u5904\u7406
  const onConnect = useCallback((params: Connection) => {
    setEdges(eds => addEdge({
      ...params,
      animated: true,
      style: { stroke: PRIMARY, strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: PRIMARY },
    }, eds));
  }, [setEdges]);

  // \u8f7d\u5165\u5de5\u4f5c\u6d41
  const loadWorkflow = useCallback(async (id: string) => {
    try {
      const wf: any = await workflowApi.get(id);
      const steps = wf?.steps || [];

      // \u6784\u5efa\u8282\u70b9\u6620\u5c04
      const oldToNew = new Map<string, string>();
      const newNodes: AgentNode[] = steps.map((s: any) => {
        const nid = uid('node');
        oldToNew.set(s.label || s.agent_type, nid);
        const a = registry.find((reg: any) => reg.id === s.agent_type);
        const meta = a ? resolveMeta(a) : { icon: RobotOutlined, color: PRIMARY };
        return {
          id: nid,
          type: 'workflow',
          position: { x: 100 + Math.random() * 600, y: 100 + (steps.indexOf(s)) * 120 },
          data: {
            agentType: s.agent_type,
            label: s.label || (a as any)?.name || s.agent_type,
            description: (a as any)?.description || s.agent_type,
            icon: React.createElement(meta.icon),
            color: meta.color,
            status: 'idle' as NodeStatus,
            userInput: s.user_input || '',
            selectedTools: s.selected_tools || [],
            inputMapping: s.input_mapping || {},
          },
        };
      });

      // \u91cd\u6620\u5c04 input_mapping
      newNodes.forEach(n => {
        const m = n.data.inputMapping || {};
        const nm: Record<string, string> = {};
        Object.entries(m).forEach(([k, v]) => { nm[k] = oldToNew.get(v) || v; });
        n.data.inputMapping = nm;
      });

      const newEdges: Edge[] = [];
      steps.forEach((s: any) => {
        const tid = oldToNew.get(s.label) || oldToNew.get(s.agent_type);
        (s.depends_on || []).forEach((d: string) => {
          const sid = oldToNew.get(d);
          if (sid && tid && sid !== tid) {
            newEdges.push({
              id: uid('e'), source: sid, target: tid,
              animated: true, style: { stroke: PRIMARY, strokeWidth: 2 },
              markerEnd: { type: MarkerType.ArrowClosed, color: PRIMARY },
            });
          }
        });
      });

      setNodes(newNodes);
      setEdges(newEdges);
      setWorkflowName(wf.name || workflowName);
      setSaveDesc(wf.description || '');
      setCurrentWfId(wf.id || id);
      setLastRun(null);
      message.success(t('messageWorkflowLoaded', { name: wf.name || '' }));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || t('messageLoadFailed'));
    }
  }, [setNodes, setEdges, message, workflowName, registry, resolveMeta, t]);

  // \u5220\u9664\u5de5\u4f5c\u6d41
  const handleDeleteWf = useCallback(async (id: string) => {
    try {
      await workflowApi.remove(id);
      if (currentWfId === id) setCurrentWfId(null);
      message.success(t('messageDeleteSuccess'));
      loadLibrary();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || t('messageDeleteFailed'));
    }
  }, [currentWfId, message, loadLibrary, t]);

  // \u8282\u70b9\u914d\u7f6e\u62bd\u5c49 useEffect
  useEffect(() => {
    if (!configNode) { setSlotInfo({ inputs: [], tools: [], outputs: [] }); return; }
    setCfgUserInput(configNode.data.userInput || '');
    setCfgTools(configNode.data.selectedTools || []);
    setCfgMapping(configNode.data.inputMapping || {});
    let cancelled = false;
    setSlotLoading(true);
    (async () => {
      try {
        const r: any = await agentApi.prepare(configNode.data.agentType, {});
        if (!cancelled) {
          const norm = (arr: any[] = []): SlotItem[] =>
            (arr || []).filter((it: any) => it && it.enabled !== false)
              .map((it: any) => ({ key: it.key, label: it.label || it.key, optional: !!it.optional, enabled: it.enabled !== false, kind: it.kind || 'file' }));
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

  // \u5f53\u524d\u8282\u70b9\u8fd0\u884c\u7ed3\u679c
  const currentNodeRun = useMemo(() => {
    if (!configNode || !lastRun?.results) return null;
    return (lastRun.results as any)[configNode.id] || null;
  }, [configNode, lastRun]);

  // \u4e0a\u6e38\u9009\u9879
  const upstreamOptions = useMemo(() => {
    if (!configNode) return [];
    return nodes
      .filter(n => edges.some(e => e.target === configNode.id && e.source === n.id))
      .map(n => ({ value: n.id, label: n.data.label }));
  }, [configNode, nodes, edges]);

  // \u8fd0\u884c\u5de5\u4f5c\u6d41
  const handleRun = useCallback(async () => {
    if (nodes.length === 0) { message.warning(t('messagePleaseAddNodes')); return; }
    setExecuting(true);
    setProgress(0);
    setLog([]);
    setLastRun(null);

    const steps = nodes.map(n => ({
      agent_type: n.data.agentType,
      label: n.data.label,
      depends_on: edges
        .filter(e => e.target === n.id)
        .map(e => nodes.find(nn => nn.id === e.source)?.data.label || e.source),
      user_input: n.data.userInput,
      selected_tools: n.data.selectedTools,
      input_mapping: n.data.inputMapping,
    }));

    try {
      const result: any = await workflowApi.execute({ steps });
      const runId = result?.run_id;

      if (runId) {
        // \u8f6e\u8be2\u6267\u884c\u72b6\u6001
        let pollCount = 0;
        const maxPolls = 300; // \u0035\u5206\u949f\u8d85\u65f6

        const poll = async () => {
          try {
            const status: any = await workflowApi.getRunStatus(runId);

            // \u66f4\u65b0\u8282\u70b9\u72b6\u6001
            if (status?.results) {
              setNodes(nds => nds.map(n => {
                const r = status.results[n.id] || status.results[n.data.label];
                if (r?.status === 'completed') return { ...n, data: { ...n.data, status: 'success' } };
                if (r?.status === 'failed') return { ...n, data: { ...n.data, status: 'error' } };
                if (r?.status === 'running') return { ...n, data: { ...n.data, status: 'running' } };
                return n;
              }));

              setLastRun(status);
              setProgress(Math.round((Object.values(status.results || {}).filter((r: any) => r?.status === 'completed').length / nodes.length) * 100));
            }

            if (status?.status === 'completed' || status?.status === 'failed' || pollCount >= maxPolls) {
              setExecuting(false);
              if (status?.status === 'failed') {
                message.error(t('messageWorkflowExecutionFailed'));
              } else {
                message.success(t('messageWorkflowExecuted'));
              }
              return;
            }

            pollCount++;
            setTimeout(poll, 2000);
          } catch (e) {
            setExecuting(false);
            message.error(t('messagePollingFailed'));
          }
        };

        poll();
      }
    } catch (e: any) {
      setExecuting(false);
      message.error(e?.response?.data?.detail || e?.message || t('messageExecutionFailed'));
    }
  }, [nodes, edges, message, t]);

  // \u4fdd\u5b58\u5de5\u4f5c\u6d41
  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) { message.warning(t('messagePleaseEnterWorkflowName')); return; }
    if (nodes.length === 0) { message.warning(t('messagePleaseAddAtLeastOneNode')); return; }

    const payload = {
      name: workflowName,
      description: saveDesc,
      is_global: false,
      steps: nodes.map(n => ({
        agent_type: n.data.agentType,
        label: n.data.label,
        depends_on: edges
          .filter(e => e.target === n.id)
          .map(e => nodes.find(nn => nn.id === e.source)?.data.label || e.source),
        user_input: n.data.userInput,
        selected_tools: n.data.selectedTools,
        input_mapping: n.data.inputMapping,
      })),
    };

    try {
      if (currentWfId) {
        await workflowApi.update(currentWfId, payload);
        message.success(t('messageWorkflowUpdated'));
      } else {
        const result: any = await workflowApi.create(payload);
        setCurrentWfId(result?.id);
        message.success(t('messageWorkflowSaved'));
      }
      setSaveOpen(false);
      loadLibrary();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || t('messageSaveFailed'));
    }
  }, [workflowName, saveDesc, nodes, edges, currentWfId, message, loadLibrary, t]);

  // \u6e05\u7a7a\u753b\u5e03
  const handleClear = useCallback(() => {
    if (nodes.length === 0) return;
    Modal.confirm({
      title: t('clearCanvas'),
      content: t('areYouSure'),
      okText: t('yes'),
      cancelText: t('no'),
      onOk: () => {
        setNodes([]);
        setEdges([]);
        setConfigNode(null);
        setLastRun(null);
        setLog([]);
        setCurrentWfId(null);
        message.success(t('canvasCleared'));
      },
    });
  }, [nodes.length, setNodes, setEdges, message, t]);

  // \u81ea\u52a8\u5e03\u5c40
  const handleAutoLayout = useCallback(() => {
    if (nodes.length === 0) return;

    // \u7b80\u5316\u7248\uff1a\u6309\u62d3\u6251\u987a\u5e8f\u6392\u5217
    const colWidth = 220;
    const rowHeight = 140;
    const cols = Math.ceil(nodes.length / 3);

    const laidOutNodes = nodes.map((n, i) => ({
      ...n,
      position: { x: 100 + (i % 3) * colWidth, y: 100 + Math.floor(i / 3) * rowHeight },
    }));

    setNodes(laidOutNodes);
  }, [nodes, setNodes, t]);

  // \u5220\u9664\u9009\u4e2d
  const removeSelected = useCallback(() => {
    // ReactFlow \u9009\u4e2d\u7684\u8282\u70b9\u901a\u8fc7 onNodesChange \u5904\u7406
    message.info('\u70b9\u51fb\u8282\u70b9\u540e\u6309\u0020\u0044\u0065\u006c\u0065\u0074\u0065\u0020\u952e\u5220\u9664');
  }, [message]);

  // \u8fd0\u884c\u5386\u53f2
  const openHistory = useCallback(async () => {
    if (!currentWfId) { message.warning(t('messagePleaseSaveWorkflowFirst')); return; }
    setHistoryOpen(true);
    setHistoryDetail(null);
    setHistoryLoading(true);
    try {
      const r: any = await workflowApi.getRuns(currentWfId);
      setHistoryList(r?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || t('messageLoadHistoryFailed'));
    } finally {
      setHistoryLoading(false);
    }
  }, [currentWfId, message, t]);

  // \u521d\u59cb\u5316
  useEffect(() => {
    loadRegistry();
    loadLibrary();
  }, [loadRegistry, loadLibrary]);

  // ── \u6e32\u67d3 ──
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 112px)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <ApartmentOutlined style={{ color: PRIMARY, fontSize: 22 }} />
          <div>
            <Input
              value={workflowName}
              onChange={e => setWorkflowName(e.target.value)}
              variant="borderless"
              style={{ fontSize: 18, fontWeight: 600, padding: 0, height: 28, width: 320 }}
              placeholder={t('workflowName')}
            />
            <div style={{ fontSize: 12, color: '#64748B' }}>
              {nodes.length} {t('agentUnit')} · {edges.length} {t('connectionUnit')}
              {currentWfId && <Tag color="blue" style={{ marginLeft: 6 }}>{t('saved')}</Tag>}
            </div>
          </div>
        </div>
        <Space>
          <Button icon={<HistoryOutlined />} onClick={openHistory} disabled={!currentWfId}>
            {t('historyDrawer')}
          </Button>
          <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)} disabled={nodes.length === 0}>
            {currentWfId ? t('update') : t('save')}
          </Button>
        </Space>
      </div>

      {/* \u4e09\u680f\u5e03\u5c40 */}
      <div style={{ display: 'flex', flex: 1, gap: 12, overflow: 'hidden' }}>
        {/* \u5de6\u680f\uff1a\u005c\u0075\u0030\u0030\u0034\u0031\u005c\u0075\u0030\u0030\u0036\u0037\u005c\u0075\u0030\u0030\u0036\u0035\u005c\u0075\u0030\u0030\u0036\u0065\u005c\u0075\u0030\u0030\u0037\u0034\u005c\u0075\u0030\u0030\u0032\u0030\u005c\u0075\u0035\u0064\u0065\u0035\u005c\u0075\u0035\u0031\u0037\u0037\u005c\u0075\u0037\u0062\u0062\u0031\u005c\u0075\u0030\u0030\u0032\u0030\u005c\u0075\u0030\u0030\u0032\u0062\u005c\u0075\u0030\u0030\u0032\u0030\u005c\u0075\u0035\u0064\u0065\u0035\u005c\u0075\u0034\u0066\u0035\u0063\u005c\u0075\u0036\u0064\u0034\u0031\u005c\u0075\u0035\u0065\u0039\u0033 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, width: 260, flexShrink: 0, overflow: 'hidden' }}>
          <Card
            size="small" title={<Space><PlusOutlined /><span>{t('agentToolbox')}</span></Space>}
            style={{ borderRadius: 12, overflow: 'hidden', flexShrink: 0, display: 'flex', flexDirection: 'column', maxHeight: '64%' }}
            bodyStyle={{ padding: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
          >
            <Input
              prefix={<SearchOutlined />} allowClear placeholder={t('searchAgentProcess')}
              value={search} onChange={e => setSearch(e.target.value)} size="small" style={{ marginBottom: 8 }}
            />
            <Segmented
              size="small" block style={{ marginBottom: 8 }}
              value={sourceFilter}
              onChange={(v) => { setSourceFilter(v as any); setCatFilter('all'); setKaFilter('all'); }}
              options={[
                { label: t('all'), value: 'all' },
                { label: t('domain'), value: 'domain' },
                { label: t('pmbok'), value: 'pmbok' },
              ]}
            />
            <Select
              size="small" style={{ marginBottom: 8 }} value={catFilter} onChange={(v) => { setCatFilter(v); setKaFilter('all'); }}
              options={categories.map(c => ({ value: c, label: c === 'all' ? t('all') : c }))}
            />
            {catFilter === t('categoryPmbokV6Processes') && knowledgeAreas.length > 0 && (
              <Select
                size="small" style={{ marginBottom: 8 }} value={kaFilter} onChange={setKaFilter}
                options={[{ value: 'all', label: t('all') }, ...knowledgeAreas.map(k => ({ value: k, label: k }))]}
              />
            )}
            <div style={{ fontSize: 11, color: '#94A3B8', marginBottom: 6 }}>
              {t('clickToAddNode', { count: toolbox.length })}
            </div>
            <div style={{ overflow: 'auto', flex: 1 }}>
              {regLoading && <div style={{ textAlign: 'center', padding: 16 }}><Spin /></div>}
              {!regLoading && toolbox.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noMatchingAgent')} />}
              {toolbox.map(a => {
                const { icon, color } = resolveMeta(a);
                const IconC = icon;
                return (
                  <div key={a.id} onClick={() => addAgentNode(a)} style={{ cursor: 'grab', marginBottom: 6 }}>
                    <Card size="small" hoverable bodyStyle={{ padding: '6px 8px' }}
                      style={{ borderLeft: `3px solid ${color}`, borderRadius: 8 }}>
                      <Space size={6}>
                        <span style={{ color, fontSize: 15 }}><IconC /></span>
                        <div style={{ minWidth: 0 }}>
                          <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', lineHeight: 1.3 }}>
                            {a.name}
                            <Tag color={color} style={{ marginLeft: 4, fontSize: 9, padding: '0 4px', lineHeight: '14px' }}>{a.id}</Tag>
                          </Text>
                          <Text type="secondary" style={{ fontSize: 10, display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {a.description || a.category}
                          </Text>
                        </div>
                      </Space>
                    </Card>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card
            size="small" title={<Space><FolderOpenOutlined /><span>{t('workflowLibrary')}</span></Space>}
            style={{ borderRadius: 12, overflow: 'auto', flex: 1 }}
            bodyStyle={{ padding: 8 }}
            extra={<Button size="small" type="text" icon={<ReloadOutlined />} loading={loadingLib} onClick={loadLibrary} />}
          >
            {loadingLib && workflows.length === 0 && (
              <div style={{ textAlign: 'center', padding: 16, color: '#94A3B8' }}><LoadingOutlined /> \u52a0\u8f7d\u4e2d\u2026</div>
            )}
            {!loadingLib && workflows.length === 0 && (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noWorkflows')} style={{ margin: '12px 0' }} />
            )}
            <List
              size="small" dataSource={workflows}
              renderItem={(w: any) => (
                <List.Item
                  actions={[
                    <Button key="load" type="link" size="small" icon={<FolderOpenOutlined />} onClick={() => loadWorkflow(w.id)}>{t('loadWorkflow')}</Button>,
                    <Popconfirm key="del" title={t('confirmDeleteWorkflow')} onConfirm={() => handleDeleteWf(w.id)}>
                      <Button type="link" size="small" danger icon={<DeleteOutlined />}>{t('deleteWorkflow')}</Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={<Text style={{ fontSize: 12 }}>{w.name}</Text>}
                    description={<Text type="secondary" style={{ fontSize: 10 }}>{t('steps', { count: (w.steps || []).length })}</Text>}
                  />
                </List.Item>
              )}
            />
          </Card>
        </div>

        {/* \u4e2d\u680f\uff1a\u005c\u0075\u0035\u0064\u0065\u0035\u005c\u0075\u0035\u0031\u0037\u0037\u005c\u0075\u0036\u0038\u0030\u0066\u005c\u0075\u0030\u0030\u0032\u0030\u005c\u0075\u0030\u0030\u0032\u0062\u005c\u0075\u0030\u0030\u0032\u0030\u005c\u0075\u0037\u0035\u0033\u0062\u005c\u0075\u0035\u0065\u0030\u0033 */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={executing} onClick={handleRun}>
              {t('runWorkflow')}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleAutoLayout} disabled={nodes.length === 0}>
              {t('autoLayout')}
            </Button>
            <Button icon={<ClearOutlined />} onClick={handleClear} disabled={nodes.length === 0}>
              {t('clearCanvas')}
            </Button>
            <div style={{ flex: 1 }} />
            <Progress
              percent={progress} size="small" style={{ width: 160 }}
              strokeColor={PRIMARY} status={executing ? 'active' : 'normal'}
            />
          </div>

          <Card
            size="small" style={{ flex: 1, borderRadius: 12, overflow: 'hidden', minHeight: 360 }}
            bodyStyle={{ padding: 0, height: '100%' }}
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              nodeTypes={{ workflow: AgentNodeView }}
              onNodeClick={(_, node) => setConfigNode(node as AgentNode)}
              fitView
              proOptions={{ hideAttribution: true }}
              deleteKeyCode={['Backspace', 'Delete']}
            >
              <Background color="#E2E8F0" gap={16} />
              <Controls />
              <MiniMap
                nodeColor={(n: any) => (n.data?.color as string) || PRIMARY}
                maskColor="rgba(241,245,249,0.6)"
                style={{ borderRadius: 8 }}
              />
            </ReactFlow>
          </Card>
        </div>

        {/* \u5de6\u680f\uff1a\u6267\u884c\u65e5\u5fd7\u0020\u002f\u0020\u8fdb\u5ea6 */}
        <Card
          size="small" title={<Space><CheckCircleOutlined /><span>{t('executionLog')}</span></Space>}
          style={{ width: 280, flexShrink: 0, borderRadius: 12, overflow: 'auto' }}
          bodyStyle={{ padding: 10 }}
        >
          <Text style={{ fontSize: 11, fontWeight: 600, color: '#6B7280' }}>
            {t('nodeStatus')}
          </Text>
          <div style={{ marginTop: 6 }}>
            {nodes.length === 0 && <Text type="secondary" style={{ fontSize: 11 }}>{t('noNodes')}</Text>}
            {nodes.map(n => {
              const m = STATUS_META[n.data.status];
              const run = lastRun?.results?.[n.id];
              return (
                <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ color: n.data.color, fontSize: 14 }}>{n.data.icon}</span>
                  <Text style={{ fontSize: 12, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {n.data.label}
                  </Text>
                  {run?.output_preview && (
                    <Tooltip title={t('viewOutputSummary')}>
                      <EyeOutlined style={{ color: '#6366F1', cursor: 'pointer' }} onClick={() => setConfigNode(n)} />
                    </Tooltip>
                  )}
                  <span style={{ color: m.color, fontSize: 11, fontWeight: 600 }}>{m.text}</span>
                </div>
              );
            })}
          </div>

          <div style={{ height: 1, background: '#E2E8F0', margin: '10px 0' }} />

          <Text style={{ fontSize: 11, fontWeight: 600, color: '#6B7280' }}>
            {t('executionLog')}
          </Text>
          <div style={{ marginTop: 6, maxHeight: 260, overflow: 'auto' }}>
            {log.length === 0 && <Text type="secondary" style={{ fontSize: 11 }}>{t('showRealTimeLog')}</Text>}
            {log.map(l => (
              <div key={l.id} style={{ marginBottom: 6, fontSize: 11 }}>
                <span style={{ color: '#94A3B8' }}>{l.time}</span>{' '}
                <span style={{ color: l.level === 'success' ? '#10B981' : l.level === 'error' ? '#EF4444' : '#1E293B', fontWeight: 600 }}>
                  {l.label}
                </span>
                <div style={{ color: '#64748B' }}>{l.message}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 8, fontSize: 10, color: '#94A3B8' }}>
            <SwapIcon /> {t('connectionExplanation')}
          </div>
        </Card>

        {/* \u8282\u70b9\u914d\u7f6e\u62bd\u5c49 */}
        <Drawer
          title={configNode ? (
            <Space>
              <span style={{ color: configNode.data.color }}>{configNode.data.icon}</span>
              <span>{configNode.data.label}</span>
              <Tag color={configNode.data.color}>{configNode.data.agentType}</Tag>
            </Space>
          ) : t('nodeConfiguration')}
          width={420}
          open={!!configNode}
          onClose={() => setConfigNode(null)}
          extra={<Button type="primary" onClick={() => {
            if (!configNode) return;
            const id = configNode.id;
            setNodes(nds => nds.map(n => n.id === id ? {
              ...n, data: { ...n.data, userInput: cfgUserInput, selectedTools: cfgTools, inputMapping: cfgMapping },
            } : n));
            message.success(t('messageNodeConfigSaved'));
            setConfigNode(null);
          }}>\u4fdd\u5b58\u914d\u7f6e</Button>}
        >
          {configNode && (
            <div>
              <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                {t('supplementaryInput')}
              </Text>
              <Input.TextArea
                rows={3} value={cfgUserInput} onChange={e => setCfgUserInput(e.target.value)}
                placeholder={t('supplementaryInputPlaceholder')}
              />

              <div style={{ height: 12 }} />
              <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                {t('toolsTech')}
              </Text>
              {slotLoading ? <Spin /> : (
                slotInfo.tools.length === 0
                  ? <Text type="secondary" style={{ fontSize: 11 }}>{t('noAvailableTools')}</Text>
                  : <Select
                      mode="multiple" allowClear style={{ width: '100%' }}
                      value={cfgTools} onChange={setCfgTools}
                      options={slotInfo.tools.map(t => ({ value: t.key, label: `${t.label}${t.optional ? '\uff08\u53ef\u9009\uff09' : ''}` }))}
                      placeholder={t('selectTools')}
                    />
              )}

              <div style={{ height: 12 }} />
              <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                {t('inputSlotMapping')}
              </Text>
              {slotLoading ? <Spin /> : (
                <div>
                  {upstreamOptions.length === 0 && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {t('noUpstream')}
                    </Text>
                  )}
                  {upstreamOptions.length > 0 && slotInfo.inputs.length === 0 && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {t('noStructuredInput')}
                    </Text>
                  )}
                  {slotInfo.inputs.map(slot => (
                    <div key={slot.key} style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 11, color: '#475569', marginBottom: 2 }}>
                        {slot.label}{slot.optional ? '\uff08\u53ef\u9009\uff09' : <Text type="danger" style={{ fontSize: 11 }}>{t('required')}</Text>}
                      </div>
                      <Select
                        size="small" style={{ width: '100%' }} allowClear
                        value={cfgMapping[slot.key] || undefined}
                        onChange={(v) => setCfgMapping(prev => {
                          const next = { ...prev };
                          if (v) next[slot.key] = v; else delete next[slot.key];
                          return next;
                        })}
                        options={upstreamOptions.map(o => ({ value: o.value, label: t('bindUpstream', { label: o.label }) }))}
                        placeholder={t('noBinding')}
                      />
                    </div>
                  ))}
                </div>
              )}

              <div style={{ height: 12 }} />
              <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                {t('outputSlot')}
              </Text>
              {slotLoading ? <Spin /> : (
                slotInfo.outputs.length === 0
                  ? <Text type="secondary" style={{ fontSize: 11 }}>{t('outputSlot')}</Text>
                  : <div>{slotInfo.outputs.map(o => <Tag key={o.key} color="green" style={{ marginBottom: 4 }}>{o.label}</Tag>)}</div>
              )}

              {currentNodeRun?.output_preview && (
                <>
                  <div style={{ height: 12 }} />
                  <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                    {t('recentRunOutput')}
                  </Text>
                  <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 8, padding: 10, fontSize: 11, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', color: '#334155' }}>
                    {currentNodeRun.output_preview}
                  </div>
                </>
              )}
            </div>
          )}
        </Drawer>

        {/* \u8fd0\u884c\u5386\u53f2\u62bd\u5c49 */}
        <Drawer
          title={t('historyDrawer')} width={460} open={historyOpen}
          onClose={() => { setHistoryOpen(false); setHistoryDetail(null); }}
        >
          {historyLoading ? <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div> : (
            historyDetail ? (
              <div>
                <Button size="small" icon={<ReloadOutlined />} onClick={() => setHistoryDetail(null)} style={{ marginBottom: 8 }}>
                  {t('returnToList')}
                </Button>
                <div style={{ fontSize: 12, marginBottom: 8 }}>
                  {t('status')}{' '}<Tag color={historyDetail.status === 'completed' ? 'green' : historyDetail.status === 'failed' ? 'red' : 'orange'}>{historyDetail.status}</Tag>
                  {' '}{t('created')}{' '}{historyDetail.created_at}
                </div>
                {Object.entries(historyDetail.results || {}).map(([label, r]: any) => (
                  <Card key={label} size="small" style={{ marginBottom: 8, borderRadius: 8 }}>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>{nodes.find(n => n.id === label)?.data.label || label}</div>
                    <Tag color={r.status === 'completed' ? 'green' : r.status === 'failed' ? 'red' : 'default'} style={{ marginTop: 4 }}>
                      {r.status}
                    </Tag>
                    {r.output_preview && (
                      <div style={{ marginTop: 6, fontSize: 11, background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 6, padding: 8, maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap', color: '#334155' }}>
                        {r.output_preview}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            ) : (
              <List
                dataSource={historyList}
                locale={{ emptyText: <Empty description={t('noHistory')} /> }}
                renderItem={(h: any) => (
                  <List.Item
                    actions={[<Button key="v" type="link" size="small" onClick={() => setHistoryDetail(h)}>{t('viewDetails')}</Button>]}
                  >
                    <List.Item.Meta
                      title={<Space>
                        <Tag color={h.status === 'completed' ? 'green' : h.status === 'failed' ? 'red' : 'orange'}>{h.status}</Tag>
                        <span style={{ fontSize: 12 }}>{h.run_id?.slice(0, 8)}</span>
                      </Space>}
                      description={<Text type="secondary" style={{ fontSize: 10 }}>{t('stepsHistory', { count: (h.steps || []).length })}</Text>}
                    />
                  </List.Item>
                )}
              />
            )
          )}
        </Drawer>

        <Modal
          title={currentWfId ? t('updateWorkflow') : t('saveWorkflow')}
          open={saveOpen} onOk={handleSave} onCancel={() => setSaveOpen(false)}
          okText={currentWfId ? t('update') : t('save')} cancelText={t('cancel')}
        >
          <div style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
              {t('name')}
            </Text>
            <Input value={workflowName} onChange={e => setWorkflowName(e.target.value)} placeholder={t('namePlaceholder')} />
          </div>
          <div style={{ marginBottom: 12 }}>
            <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
              {t('description')}
            </Text>
            <Input.TextArea rows={3} value={saveDesc} onChange={e => setSaveDesc(e.target.value)} placeholder={t('descriptionPlaceholder')} />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {currentWfId ? t('willUpdateCurrent') : t('willSave', { count: nodes.length })}
            </Text>
          </div>
        </Modal>
      </div>
    </div>
  );
};

interface LogEntry {
  id: string;
  time: string;
  label: string;
  message: string;
  level: 'info' | 'success' | 'error';
}

const WorkflowAugmented: React.FC = () => (
  <ReactFlowProvider>
    <WorkflowInner />
  </ReactFlowProvider>
);

export default WorkflowAugmented;