/**
 * AIPM 智能工作流编排增强版（测试）
 * 完全对齐 AgentWorkflow 架构，使用统一注册中心 + 后端API
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

const { Text } = Typography;
const PRIMARY = '#4F46E5';

// ─────────────────────────────────────────────────────────────────────────────
// 类型定义
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
// 图标映射
// ─────────────────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, React.ComponentType<any>> = {
  FileTextOutlined, BarChartOutlined, WarningOutlined, RobotOutlined, ThunderboltOutlined,
  SafetyOutlined, AimOutlined, FileDoneOutlined, HeartOutlined, BulbOutlined,
  PartitionOutlined, CompassOutlined, NodeIndexOutlined,
};

const CAT_ICON: Record<string, React.ComponentType<any>> = {
  'PMBOK第6版·49过程': PartitionOutlined,
  'PMBOK第8版·原则': CompassOutlined,
  'PMBOK第8版·绩效域': ApartmentOutlined,
  'PMBOK第8版·裁剪': NodeIndexOutlined,
  'CPMAI·AI项目管理阶段': RobotOutlined,
  'CPMAI·可信AI框架': SafetyOutlined,
  '领域分析': ThunderboltOutlined,
};

const CAT_COLOR: Record<string, string> = {
  'PMBOK第6版·49过程': '#4F46E5',
  'PMBOK第8版·原则': '#10B981',
  'PMBOK第8版·绩效域': '#6366F1',
  'PMBOK第8版·裁剪': '#06B6D4',
  'CPMAI·AI项目管理阶段': '#F59E0B',
  'CPMAI·可信AI框架': '#EF4444',
  '领域分析': '#4F46E5',
};

const STATUS_META: Record<NodeStatus, { color: string; text: string; icon: React.ReactNode }> = {
  idle:    { color: '#94A3B8', text: '待运行', icon: <LoadingOutlined style={{ opacity: 0 }} /> },
  running: { color: '#F59E0B', text: '运行中', icon: <LoadingOutlined spin /> },
  success: { color: '#10B981', text: '成功',   icon: <CheckCircleOutlined /> },
  error:   { color: '#EF4444', text: '失败',   icon: <CloseCircleOutlined /> },
};

// ─────────────────────────────────────────────────────────────────────────────
// 辅助函数
// ─────────────────────────────────────────────────────────────────────────────

let _counter = 0;
const uid = (prefix: string) => `${prefix}_${Date.now()}_${_counter++}`;

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

// ─────────────────────────────────────────────────────────────────────────────
// 自定义节点组件
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
            {data.userInput && <Tag color="blue" style={{ fontSize: 9, padding: '0 4px' }}>输入</Tag>}
            {data.selectedTools.length > 0 && <Tag color="purple" style={{ fontSize: 9, padding: '0 4px' }}>工具</Tag>}
            {Object.keys(data.inputMapping).length > 0 && <Tag color="orange" style={{ fontSize: 9, padding: '0 4px' }}>映射</Tag>}
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
// 内部组件（需要 ReactFlowProvider）
// ─────────────────────────────────────────────────────────────────────────────

const WorkflowInner: React.FC = () => {
  const { message } = App.useApp();
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { screenToFlowPosition } = useReactFlow();
  
  // Agent注册中心
  const [registry, setRegistry] = useState<RegistryAgentItem[]>([]);
  const [regLoading, setRegLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'domain' | 'pmbok'>('all');
  const [catFilter, setCatFilter] = useState('all');
  const [kaFilter, setKaFilter] = useState('all');
  
  // 工作流状态
  const [workflowName, setWorkflowName] = useState('');
  const [currentWfId, setCurrentWfId] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveDesc, setSaveDesc] = useState('');
  
  // 执行状态
  const [executing, setExecuting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [lastRun, setLastRun] = useState<any>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  
  // 节点配置
  const [configNode, setConfigNode] = useState<AgentNode | null>(null);
  const [cfgUserInput, setCfgUserInput] = useState('');
  const [cfgTools, setCfgTools] = useState<string[]>([]);
  const [cfgMapping, setCfgMapping] = useState<Record<string, string>>({});
  const [slotInfo, setSlotInfo] = useState({ inputs: [], tools: [], outputs: [] });
  const [slotLoading, setSlotLoading] = useState(false);
  
  // 工作流库
  const [workflows, setWorkflows] = useState<any[]>([]);
  const [loadingLib, setLoadingLib] = useState(false);
  
  // 运行历史
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyList, setHistoryList] = useState<any[]>([]);
  const [historyDetail, setHistoryDetail] = useState<any>(null);

  // 分类和知识领域
  const categories = useMemo(() => {
    const cats = new Set(registry.map(a => a.category).filter(Boolean));
    return ['all', ...Array.from(cats)];
  }, [registry]);
  
  const knowledgeAreas = useMemo(() => {
    const areas = new Set(
      registry
        .filter(a => a.category === 'PMBOK第6版·49过程')
        .map(a => a.extra?.knowledge_area)
        .filter(Boolean)
    );
    return Array.from(areas);
  }, [registry]);

  // 工具栏过滤后的Agent列表
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

  // 解析Agent元数据
  const resolveMeta = useCallback((a: RegistryAgentItem) => {
    const IconC = ICON_MAP[a.icon] || RobotOutlined;
    const color = a.color || CAT_COLOR[a.category] || PRIMARY;
    return { icon: IconC, color };
  }, []);

  // 加载注册中心
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

  // 加载工作流库
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

  // 添加节点
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

  // 连接处理
  const onConnect = useCallback((params: Connection) => {
    setEdges(eds => addEdge({
      ...params,
      animated: true,
      style: { stroke: PRIMARY, strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: PRIMARY },
    }, eds));
  }, [setEdges]);

  // 载入工作流
  const loadWorkflow = useCallback(async (id: string) => {
    try {
      const wf: any = await workflowApi.get(id);
      const steps = wf?.steps || [];
      
      // 构建节点映射
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
      
      // 重映射 input_mapping
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
      message.success(`已载入「${wf.name || ''}」`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '载入失败');
    }
  }, [setNodes, setEdges, message, workflowName, registry, resolveMeta]);

  // 删除工作流
  const handleDeleteWf = useCallback(async (id: string) => {
    try {
      await workflowApi.remove(id);
      if (currentWfId === id) setCurrentWfId(null);
      message.success('已删除');
      loadLibrary();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败');
    }
  }, [currentWfId, message, loadLibrary]);

  // 节点配置抽屉 useEffect
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

  // 当前节点运行结果
  const currentNodeRun = useMemo(() => {
    if (!configNode || !lastRun?.results) return null;
    return (lastRun.results as any)[configNode.id] || null;
  }, [configNode, lastRun]);

  // 上游选项
  const upstreamOptions = useMemo(() => {
    if (!configNode) return [];
    return nodes
      .filter(n => edges.some(e => e.target === configNode.id && e.source === n.id))
      .map(n => ({ value: n.id, label: n.data.label }));
  }, [configNode, nodes, edges]);

  // 运行工作流
  const handleRun = useCallback(async () => {
    if (nodes.length === 0) { message.warning('请先添加节点'); return; }
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
        // 轮询执行状态
        let pollCount = 0;
        const maxPolls = 300; // 5分钟超时
        
        const poll = async () => {
          try {
            const status: any = await workflowApi.getRunStatus(runId);
            
            // 更新节点状态
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
                message.error('工作流执行失败');
              } else {
                message.success('工作流执行完成');
              }
              return;
            }
            
            pollCount++;
            setTimeout(poll, 2000);
          } catch (e) {
            setExecuting(false);
            message.error('轮询执行状态失败');
          }
        };
        
        poll();
      }
    } catch (e: any) {
      setExecuting(false);
      message.error(e?.response?.data?.detail || e?.message || '执行失败');
    }
  }, [nodes, edges, message]);

  // 保存工作流
  const handleSave = useCallback(async () => {
    if (!workflowName.trim()) { message.warning('请输入工作流名称'); return; }
    if (nodes.length === 0) { message.warning('请至少添加一个节点'); return; }
    
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
        message.success('工作流已更新');
      } else {
        const result: any = await workflowApi.create(payload);
        setCurrentWfId(result?.id);
        message.success('工作流已保存');
      }
      setSaveOpen(false);
      loadLibrary();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '保存失败');
    }
  }, [workflowName, saveDesc, nodes, edges, currentWfId, message, loadLibrary]);

  // 清空画布
  const handleClear = useCallback(() => {
    if (nodes.length === 0) return;
    Modal.confirm({
      title: '清空画布',
      content: '确定要清空所有节点和连线吗？',
      okText: '清空',
      cancelText: '取消',
      onOk: () => {
        setNodes([]);
        setEdges([]);
        setConfigNode(null);
        setLastRun(null);
        setLog([]);
        setCurrentWfId(null);
        message.success('已清空');
      },
    });
  }, [nodes.length, setNodes, setEdges, message]);

  // 自动布局
  const handleAutoLayout = useCallback(() => {
    if (nodes.length === 0) return;
    
    // 简化版：按拓扑顺序排列
    const colWidth = 220;
    const rowHeight = 140;
    const cols = Math.ceil(nodes.length / 3);
    
    const laidOutNodes = nodes.map((n, i) => ({
      ...n,
      position: { x: 100 + (i % 3) * colWidth, y: 100 + Math.floor(i / 3) * rowHeight },
    }));
    
    setNodes(laidOutNodes);
  }, [nodes, setNodes]);

  // 删除选中
  const removeSelected = useCallback(() => {
    // ReactFlow 选中的节点通过 onNodesChange 处理
    message.info('点击节点后按 Delete 键删除');
  }, [message]);

  // 运行历史
  const openHistory = useCallback(async () => {
    if (!currentWfId) { message.warning('请先保存工作流以查看运行历史'); return; }
    setHistoryOpen(true);
    setHistoryDetail(null);
    setHistoryLoading(true);
    try {
      const r: any = await workflowApi.getRuns(currentWfId);
      setHistoryList(r?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '加载历史失败');
    } finally {
      setHistoryLoading(false);
    }
  }, [currentWfId, message]);

  // 初始化
  useEffect(() => {
    loadRegistry();
    loadLibrary();
  }, [loadRegistry, loadLibrary]);

  // ── 渲染 ──
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
              placeholder="工作流名称"
            />
            <div style={{ fontSize: 12, color: '#64748B' }}>
              {nodes.length} 个 Agent 节点 · {edges.length} 条数据流连线
              {currentWfId && <Tag color="blue" style={{ marginLeft: 6 }}>已保存</Tag>}
            </div>
          </div>
        </div>
        <Space>
          <Button icon={<HistoryOutlined />} onClick={openHistory} disabled={!currentWfId}>
            运行历史
          </Button>
          <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)} disabled={nodes.length === 0}>
            {currentWfId ? '更新' : '保存'}
          </Button>
        </Space>
      </div>

      {/* 三栏布局 */}
      <div style={{ display: 'flex', flex: 1, gap: 12, overflow: 'hidden' }}>
        {/* 左栏：Agent 工具箱 + 工作流库 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, width: 260, flexShrink: 0, overflow: 'hidden' }}>
          <Card
            size="small" title={<Space><PlusOutlined /><span>Agent 工具箱</span></Space>}
            style={{ borderRadius: 12, overflow: 'hidden', flexShrink: 0, display: 'flex', flexDirection: 'column', maxHeight: '64%' }}
            bodyStyle={{ padding: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
          >
            <Input
              prefix={<SearchOutlined />} allowClear placeholder="搜索 Agent / 过程 id"
              value={search} onChange={e => setSearch(e.target.value)} size="small" style={{ marginBottom: 8 }}
            />
            <Segmented
              size="small" block style={{ marginBottom: 8 }}
              value={sourceFilter}
              onChange={(v) => { setSourceFilter(v as any); setCatFilter('all'); setKaFilter('all'); }}
              options={[
                { label: '全部', value: 'all' },
                { label: '领域', value: 'domain' },
                { label: 'PMBOK', value: 'pmbok' },
              ]}
            />
            <Select
              size="small" style={{ marginBottom: 8 }} value={catFilter} onChange={(v) => { setCatFilter(v); setKaFilter('all'); }}
              options={categories.map(c => ({ value: c, label: c === 'all' ? '全部体系' : c }))}
            />
            {catFilter === 'PMBOK第6版·49过程' && knowledgeAreas.length > 0 && (
              <Select
                size="small" style={{ marginBottom: 8 }} value={kaFilter} onChange={setKaFilter}
                options={[{ value: 'all', label: '全部知识领域' }, ...knowledgeAreas.map(k => ({ value: k, label: k }))]}
              />
            )}
            <div style={{ fontSize: 11, color: '#94A3B8', marginBottom: 6 }}>点击添加节点（{toolbox.length}）</div>
            <div style={{ overflow: 'auto', flex: 1 }}>
              {regLoading && <div style={{ textAlign: 'center', padding: 16 }}><Spin /></div>}
              {!regLoading && toolbox.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无匹配 Agent" />}
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
            size="small" title={<Space><FolderOpenOutlined /><span>工作流库</span></Space>}
            style={{ borderRadius: 12, overflow: 'auto', flex: 1 }}
            bodyStyle={{ padding: 8 }}
            extra={<Button size="small" type="text" icon={<ReloadOutlined />} loading={loadingLib} onClick={loadLibrary} />}
          >
            {loadingLib && workflows.length === 0 && (
              <div style={{ textAlign: 'center', padding: 16, color: '#94A3B8' }}><LoadingOutlined /> 加载中…</div>
            )}
            {!loadingLib && workflows.length === 0 && (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无工作流" style={{ margin: '12px 0' }} />
            )}
            <List
              size="small" dataSource={workflows}
              renderItem={(w: any) => (
                <List.Item
                  actions={[
                    <Button key="load" type="link" size="small" icon={<FolderOpenOutlined />} onClick={() => loadWorkflow(w.id)}>载入</Button>,
                    <Popconfirm key="del" title="确认删除该工作流？" onConfirm={() => handleDeleteWf(w.id)}>
                      <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={<Text style={{ fontSize: 12 }}>{w.name}</Text>}
                    description={<Text type="secondary" style={{ fontSize: 10 }}>{(w.steps || []).length} 步</Text>}
                  />
                </List.Item>
              )}
            />
          </Card>
        </div>

        {/* 中栏：工具栏 + 画布 */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={executing} onClick={handleRun}>
              运行工作流
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleAutoLayout} disabled={nodes.length === 0}>
              自动布局
            </Button>
            <Button icon={<ClearOutlined />} onClick={handleClear} disabled={nodes.length === 0}>
              清空
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

        {/* 右栏：执行日志 / 进度 */}
        <Card
          size="small" title={<Space><CheckCircleOutlined /><span>执行日志 / 进度</span></Space>}
          style={{ width: 280, flexShrink: 0, borderRadius: 12, overflow: 'auto' }}
          bodyStyle={{ padding: 10 }}
        >
          <Text style={{ fontSize: 11, fontWeight: 600, color: '#6B7280' }}>节点状态</Text>
          <div style={{ marginTop: 6 }}>
            {nodes.length === 0 && <Text type="secondary" style={{ fontSize: 11 }}>暂无节点</Text>}
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
                    <Tooltip title="查看输出摘要">
                      <EyeOutlined style={{ color: '#6366F1', cursor: 'pointer' }} onClick={() => setConfigNode(n)} />
                    </Tooltip>
                  )}
                  <span style={{ color: m.color, fontSize: 11, fontWeight: 600 }}>{m.text}</span>
                </div>
              );
            })}
          </div>

          <div style={{ height: 1, background: '#E2E8F0', margin: '10px 0' }} />

          <Text style={{ fontSize: 11, fontWeight: 600, color: '#6B7280' }}>运行日志</Text>
          <div style={{ marginTop: 6, maxHeight: 260, overflow: 'auto' }}>
            {log.length === 0 && <Text type="secondary" style={{ fontSize: 11 }}>运行后此处显示实时日志</Text>}
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
            <SwapIcon /> 连线即「依赖」：一个节点可连多个上游（扇入合并），也可被多个下游引用（扇出复用）。
          </div>
        </Card>
      </div>

      {/* 节点配置抽屉 */}
      <Drawer
        title={configNode ? (
          <Space>
            <span style={{ color: configNode.data.color }}>{configNode.data.icon}</span>
            <span>{configNode.data.label}</span>
            <Tag color={configNode.data.color}>{configNode.data.agentType}</Tag>
          </Space>
        ) : '节点配置'}
        width={420}
        open={!!configNode}
        onClose={() => setConfigNode(null)}
        extra={<Button type="primary" onClick={() => {
          if (!configNode) return;
          const id = configNode.id;
          setNodes(nds => nds.map(n => n.id === id ? {
            ...n, data: { ...n.data, userInput: cfgUserInput, selectedTools: cfgTools, inputMapping: cfgMapping },
          } : n));
          message.success('节点配置已保存');
          setConfigNode(null);
        }}>保存配置</Button>}
      >
        {configNode && (
          <div>
            <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>补充输入（内联文本）</Text>
            <Input.TextArea
              rows={3} value={cfgUserInput} onChange={e => setCfgUserInput(e.target.value)}
              placeholder="可选：作为该 Agent 的内联补充输入，与上游输出拼接后一起喂入"
            />

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
              工具技术（selected_tools）
            </Text>
            {slotLoading ? <Spin /> : (
              slotInfo.tools.length === 0
                ? <Text type="secondary" style={{ fontSize: 11 }}>该 Agent 无可选工具技术</Text>
                : <Select
                    mode="multiple" allowClear style={{ width: '100%' }}
                    value={cfgTools} onChange={setCfgTools}
                    options={slotInfo.tools.map(t => ({ value: t.key, label: `${t.label}${t.optional ? '（可选）' : ''}` }))}
                    placeholder="勾选工具技术（空=全部）"
                  />
            )}

            <div style={{ height: 12 }} />
            <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
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
                    <div style={{ fontSize: 11, color: '#475569', marginBottom: 2 }}>
                      {slot.label}{slot.optional ? '（可选）' : <Text type="danger" style={{ fontSize: 11 }}>（必填）</Text>}
                    </div>
                    <Select
                      size="small" style={{ width: '100%' }} allowClear
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
            <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>输出槽位</Text>
            {slotLoading ? <Spin /> : (
              slotInfo.outputs.length === 0
                ? <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
                : <div>{slotInfo.outputs.map(o => <Tag key={o.key} color="green" style={{ marginBottom: 4 }}>{o.label}</Tag>)}</div>
            )}

            {currentNodeRun?.output_preview && (
              <>
                <div style={{ height: 12 }} />
                <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>最近运行输出（摘要）</Text>
                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 8, padding: 10, fontSize: 11, maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap', color: '#334155' }}>
                  {currentNodeRun.output_preview}
                </div>
              </>
            )}
          </div>
        )}
      </Drawer>

      {/* 运行历史抽屉 */}
      <Drawer
        title="运行历史" width={460} open={historyOpen}
        onClose={() => { setHistoryOpen(false); setHistoryDetail(null); }}
      >
        {historyLoading ? <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div> : (
          historyDetail ? (
            <div>
              <Button size="small" icon={<ReloadOutlined />} onClick={() => setHistoryDetail(null)} style={{ marginBottom: 8 }}>
                返回列表
              </Button>
              <div style={{ fontSize: 12, marginBottom: 8 }}>
                状态：<Tag color={historyDetail.status === 'completed' ? 'green' : historyDetail.status === 'failed' ? 'red' : 'orange'}>{historyDetail.status}</Tag>
                {' '}创建：{historyDetail.created_at}
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
              locale={{ emptyText: <Empty description="暂无运行历史" /> }}
              renderItem={(h: any) => (
                <List.Item
                  actions={[<Button key="v" type="link" size="small" onClick={() => setHistoryDetail(h)}>查看</Button>]}
                >
                  <List.Item.Meta
                    title={<Space>
                      <Tag color={h.status === 'completed' ? 'green' : h.status === 'failed' ? 'red' : 'orange'}>{h.status}</Tag>
                      <span style={{ fontSize: 12 }}>{h.run_id?.slice(0, 8)}</span>
                    </Space>}
                    description={<Text type="secondary" style={{ fontSize: 10 }}>{h.created_at} · {(h.steps || []).length} 步</Text>}
                  />
                </List.Item>
              )}
            />
          )
        )}
      </Drawer>

      <Modal
        title={currentWfId ? '更新工作流' : '保存工作流'}
        open={saveOpen} onOk={handleSave} onCancel={() => setSaveOpen(false)}
        okText={currentWfId ? '更新' : '保存'} cancelText="取消"
      >
        <div style={{ marginBottom: 12 }}>
          <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>名称 *</Text>
          <Input value={workflowName} onChange={e => setWorkflowName(e.target.value)} placeholder="例如：项目健康检查" />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>描述</Text>
          <Input.TextArea rows={3} value={saveDesc} onChange={e => setSaveDesc(e.target.value)} placeholder="描述工作流用途…" />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {currentWfId ? '将更新当前工作流' : `将保存 ${nodes.length} 个节点的工作流定义`}
          </Text>
        </div>
      </Modal>
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
