/**
 * NetworkDiagram — AON 紧前逻辑关系图（PDM/Precedence Diagramming Method）
 *
 * 严格按 PMBOK 第 6 章 6.3.2.2 紧前绘图法绘制：
 *  - 节点 = 活动（Task）
 *  - 边   = 紧前逻辑关系（FS / FF / SS / SF）+ 延隔
 *  - 节点显示 任务名 / WBS / 工期 / ES·EF / LS·LF / TF·FF
 *  - 关键路径节点：红色脉冲 + 浅红底
 *  - 支持 hover 高亮紧前/紧后、整图缩放/平移、点击查看活动详情
 */

import React, { useMemo, useState, useRef, useEffect, useCallback } from "react";
import { Tooltip, Button, Space, Tag, Card, Empty, Alert } from "antd";
import {
  ZoomInOutlined, ZoomOutOutlined, ExpandOutlined, ReloadOutlined,
  AimOutlined, FullscreenOutlined, PrinterOutlined, FireOutlined,
} from "@ant-design/icons";

/* ═══════════ 类型定义 ═══════════ */

export interface NetworkNode {
  id: string;
  name: string;
  shortName: string;
  x: number;          // 节点左上角 x（后端给定）
  y: number;          // 节点左上角 y
  es: number; ef: number; ls: number; lf: number;
  tf: number; ff: number;
  isCritical: boolean;
  duration: number;
  level: number;
  progress: number;
  status: string;
  wbsCode?: string;
  dependencyIds: string[];
}

export interface NetworkEdge {
  source: string;
  target: string;
  label: string;   // "FS" / "FS+2d" / "FF-1d" ...
  type: string;    // "FS" | "FF" | "SS" | "SF"
  lag: number;
}

export interface NetworkLayout {
  width: number;
  height: number;
  levels: number;
  nodeSize?: { w: number; h: number };
}

interface NetworkDiagramProps {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  layout: NetworkLayout;
  /** 节点点击回调（用于跳转任务详情） */
  onNodeClick?: (node: NetworkNode) => void;
  /** 加载态 */
  loading?: boolean;
}

/* ═══════════ 节点盒尺寸（自适应） ═══════════ */

const NODE_W_BASE = 188;   // 最小节点宽
const NODE_W_MAX  = 280;   // 最大节点宽（防止撑爆画布）
const NODE_H      = 116;   // 节点高
const CHAR_PX     = 13;    // 估算每个字符像素
const COL_GAP     = 72;    // 节点水平间距
const ROW_GAP     = 78;    // 节点垂直间距
const PAD         = 56;    // 画布内边距

/* ═══════════ 工具函数 ═══════════ */

/** 按字符宽度估算显示宽度（中英混合按 1.0 字符宽度） */
const estimateTextWidth = (s: string, charPx = CHAR_PX, maxChars = 18) => {
  const chars = [...s].slice(0, maxChars).join("");
  return Math.max(NODE_W_BASE, Math.min(NODE_W_MAX, Math.ceil(chars.length * charPx) + 64));
};

/** 自适应计算所有节点的最终宽度，并按层居中 */
const reLayout = (nodes: NetworkNode[], hasDependencies: boolean): {
  sized: NetworkNode[];
  width: number;
  height: number;
  colMap: Map<number, NetworkNode[]>;
} => {
  if (!nodes.length) return { sized: [], width: 0, height: 0, colMap: new Map() };

  // 按 level 分组
  const byLevel: Map<number, NetworkNode[]> = new Map();
  for (const n of nodes) {
    if (!byLevel.has(n.level)) byLevel.set(n.level, []);
    byLevel.get(n.level)!.push(n);
  }

  // 当无依赖关系时（hasDependencies=false），所有任务 ES=0 → 后端把它们都放在 level=0
  // 此时用"伪 level"重新分桶：按 WBS code 前缀（'1','1.1','2','2.1'...）分组，让图形呈矩阵排列
  if (!hasDependencies && byLevel.size === 1 && byLevel.get(0)!.length > 6) {
    byLevel.clear();
    for (const n of nodes) {
      const wbs = (n.wbsCode || "").trim();
      // 取第一段数字作为"组"（"1.1.2"→1，"2.3"→2，无 wbs→0）
      const m = wbs.match(/^(\d+)/);
      const group = m ? parseInt(m[1], 10) : 0;
      const fakeLevel = group;
      // 改写 level
      n.level = fakeLevel;
      if (!byLevel.has(fakeLevel)) byLevel.set(fakeLevel, []);
      byLevel.get(fakeLevel)!.push(n);
    }
  }

  // 每层排序：关键路径优先、其次按 ES/WBS、再次按名称
  for (const arr of byLevel.values()) {
    arr.sort((a, b) => {
      if (a.isCritical !== b.isCritical) return a.isCritical ? -1 : 1;
      // WBS 自然排序（"1.1" < "1.2" < "10"）
      const wa = (a.wbsCode || "").split(".").map((s) => parseInt(s, 10) || 999);
      const wb = (b.wbsCode || "").split(".").map((s) => parseInt(s, 10) || 999);
      for (let i = 0; i < Math.max(wa.length, wb.length); i++) {
        const da = wa[i] ?? 999, db = wb[i] ?? 999;
        if (da !== db) return da - db;
      }
      if (a.es !== b.es) return a.es - b.es;
      return a.name.localeCompare(b.name);
    });
  }

  // 自适应节点宽度 + 按层重新居中
  const sized: NetworkNode[] = [];
  const maxRowWidths: number[] = [];
  const levels = Array.from(byLevel.keys()).sort((a, b) => a - b);

  for (const lv of levels) {
    const arr = byLevel.get(lv)!;
    // 取每节点自适应宽
    const widths = arr.map((n) => estimateTextWidth(n.name));
    arr.forEach((n, idx) => (n as any).__w = widths[idx]);
    // 行总宽 = sum(widths) + (n-1)*COL_GAP
    const rowW = widths.reduce((a, b) => a + b, 0) + (arr.length - 1) * COL_GAP;
    maxRowWidths.push(rowW);
  }

  const maxRowW = Math.max(...maxRowWidths, NODE_W_BASE);
  const totalH = levels.length * NODE_H + (levels.length - 1) * ROW_GAP;

  // 写回 x（按 maxRowW 居中）+ y
  levels.forEach((lv, li) => {
    const arr = byLevel.get(lv)!;
    const rowW = maxRowWidths[li];
    let cursorX = PAD + (maxRowW - rowW) / 2;
    const y = PAD + li * (NODE_H + ROW_GAP);
    for (const n of arr) {
      const w = (n as any).__w as number;
      n.x = cursorX;
      n.y = y;
      cursorX += w + COL_GAP;
      sized.push(n);
    }
  });

  return {
    sized,
    width: maxRowW + 2 * PAD,
    height: totalH + 2 * PAD,
    colMap: byLevel,
  };
};

/** 关键路径 ID 集合（便于把整条关键路径描红） */
const buildCriticalIds = (nodes: NetworkNode[]) =>
  new Set(nodes.filter((n) => n.isCritical).map((n) => n.id));

/* ═══════════ 节点内部 SVG 组件 ═══════════ */

interface NodeBoxProps {
  node: NetworkNode;
  w: number;
  isHighlighted: boolean;
  isDimmed: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  todo: "#94A3B8", doing: "#3B82F6", in_progress: "#3B82F6",
  done: "#10B981", blocked: "#EF4444", review: "#8B5CF6", testing: "#F59E0B",
};

const NodeBox: React.FC<NodeBoxProps> = ({
  node, w, isHighlighted, isDimmed, onClick, onMouseEnter, onMouseLeave,
}) => {
  const critical = node.isCritical;
  const stroke = isHighlighted ? "#3B82F6" : (critical ? "#FF4D4F" : "#94A3B8");
  const strokeW = isHighlighted ? 3 : (critical ? 2.2 : 1.2);
  const fill = critical ? "#FFF1F0" : "#FFFFFF";
  const nameColor = critical ? "#CF1322" : "#0F172A";

  // 头部 30px：WBS + 任务名
  const headerH = 32;
  // 主体 56px：ES/EF LS/LF + 进度
  // 底部 28px：工期 + TF/FF
  const bodyY = headerH;
  const footY = NODE_H - 28;
  const midY = bodyY + (footY - bodyY) / 2;

  const opacity = isDimmed ? 0.25 : 1;

  // 截断任务名（按宽度估算字符数）
  const maxNameChars = Math.max(8, Math.floor((w - 90) / CHAR_PX));
  const displayName = node.name.length > maxNameChars
    ? node.name.slice(0, maxNameChars) + "…"
    : node.name;

  return (
    <g
      transform={`translate(${node.x}, ${node.y})`}
      style={{ cursor: "pointer", opacity, transition: "opacity .15s" }}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* 阴影 */}
      <rect
        x={0} y={2} width={w} height={NODE_H}
        rx={10} ry={10}
        fill="rgba(15,23,42,.06)"
      />
      {/* 主体 */}
      <rect
        x={0} y={0} width={w} height={NODE_H}
        rx={10} ry={10}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeW}
        className={critical ? "aon-critical-node" : undefined}
      />
      {/* 头部背景条 */}
      <rect
        x={0} y={0} width={w} height={headerH}
        rx={10} ry={10}
        fill={critical ? "linear-gradient(90deg,#FFE7E5,#FFF1F0)" : "#F8FAFC"}
        style={{ fill: critical ? "url(#aonCritHeader)" : "#F8FAFC" }}
      />
      {/* 头部底线 */}
      <line x1={0} y1={headerH} x2={w} y2={headerH} stroke="#E2E8F0" strokeWidth={1} />

      {/* WBS 标签 */}
      {node.wbsCode && (
        <g transform={`translate(8, ${headerH / 2})`}>
          <rect x={0} y={-9} width={Math.max(28, node.wbsCode.length * 7 + 10)} height={18} rx={4}
            fill={critical ? "#FF4D4F" : "#475569"} opacity={0.9} />
          <text
            x={Math.max(28, node.wbsCode.length * 7 + 10) / 2} y={4}
            textAnchor="middle" fontSize={10} fontWeight={600} fill="#fff"
            fontFamily="ui-monospace, SFMono-Regular, monospace"
          >
            {node.wbsCode}
          </text>
        </g>
      )}

      {/* 任务名 */}
      <text
        x={node.wbsCode ? Math.max(28, node.wbsCode.length * 7 + 10) + 18 : 12}
        y={headerH / 2 + 4}
        fontSize={13} fontWeight={700} fill={nameColor}
        style={{ pointerEvents: "none" }}
      >
        {displayName}
      </text>

      {/* 关键路径闪电标识 */}
      {critical && (
        <g transform={`translate(${w - 18}, 16)`}>
          <circle r={9} fill="#FF4D4F" />
          <text textAnchor="middle" y={3.5} fontSize={11} fill="#fff" fontWeight="bold">⚡</text>
        </g>
      )}

      {/* 主体左：ES · EF */}
      <g transform="translate(12, 20)">
        <text y={bodyY + 6} fontSize={10} fill="#94A3B8" fontFamily="ui-monospace,monospace">最早</text>
        <text y={bodyY + 22} fontSize={11} fontWeight={600} fill="#0F172A" fontFamily="ui-monospace,monospace">
          ES <tspan fill="#3B82F6">{node.es}</tspan>
        </text>
        <text y={bodyY + 36} fontSize={11} fontWeight={600} fill="#0F172A" fontFamily="ui-monospace,monospace">
          EF <tspan fill="#3B82F6">{node.ef}</tspan>
        </text>
      </g>

      {/* 主体右：LS · LF */}
      <g transform="translate(96, 20)">
        <text y={bodyY + 6} fontSize={10} fill="#94A3B8" fontFamily="ui-monospace,monospace">最晚</text>
        <text y={bodyY + 22} fontSize={11} fontWeight={600} fill="#0F172A" fontFamily="ui-monospace,monospace">
          LS <tspan fill="#F59E0B">{node.ls}</tspan>
        </text>
        <text y={bodyY + 36} fontSize={11} fontWeight={600} fill="#0F172A" fontFamily="ui-monospace,monospace">
          LF <tspan fill="#F59E0B">{node.lf}</tspan>
        </text>
      </g>

      {/* 进度条（贴在主体右内侧） */}
      {node.progress > 0 && (
        <g transform={`translate(154, ${bodyY + 8})`}>
          <rect x={0} y={0} width={Math.max(20, w - 168)} height={6} rx={3} fill="#E2E8F0" />
          <rect
            x={0} y={0} width={(Math.max(20, w - 168)) * Math.min(100, node.progress) / 100}
            height={6} rx={3}
            fill={critical ? "#FF4D4F" : "#3B82F6"}
          />
          <text x={Math.max(20, w - 168) + 6} y={6} fontSize={10} fill="#475569" fontWeight={600}>
            {Math.round(node.progress)}%
          </text>
        </g>
      )}

      {/* 底部底线 */}
      <line x1={0} y1={footY} x2={w} y2={footY} stroke="#E2E8F0" strokeWidth={1} />

      {/* 底部：工期 + TF/FF */}
      <g transform={`translate(12, ${footY + 18})`}>
        <text fontSize={11} fontWeight={600} fill="#475569">
          工期 <tspan fontWeight={700} fill={critical ? "#FF4D4F" : "#0F172A"}>{node.duration}</tspan>d
        </text>
      </g>
      <g transform={`translate(${w - 110}, ${footY + 18})`}>
        <text fontSize={10} fill="#64748B" fontFamily="ui-monospace,monospace">
          TF <tspan fontWeight={700} fill={critical ? "#EF4444" : (node.tf > 0 ? "#F59E0B" : "#94A3B8")}>{node.tf}</tspan>d
        </text>
        <text x={48} fontSize={10} fill="#64748B" fontFamily="ui-monospace,monospace">
          FF <tspan fontWeight={700} fill={node.ff > 0 ? "#06B6D4" : "#94A3B8"}>{node.ff}</tspan>d
        </text>
      </g>

      {/* 状态点 */}
      {node.status && STATUS_COLOR[node.status] && (
        <circle
          cx={w - 8} cy={8} r={4}
          fill={STATUS_COLOR[node.status]}
          stroke="#fff" strokeWidth={1.5}
        />
      )}
    </g>
  );
};

/* ═══════════ 边（依赖关系）连接点计算 ═══════════ */

interface Point { x: number; y: number; }

const getNodeRect = (n: NetworkNode) => {
  const w = (n as any).__w || NODE_W_BASE;
  return { x: n.x, y: n.y, w, h: NODE_H };
};

const getAnchor = (n: NetworkNode, side: "left" | "right" | "top" | "bottom"): Point => {
  const r = getNodeRect(n);
  switch (side) {
    case "left":   return { x: r.x,         y: r.y + r.h / 2 };
    case "right":  return { x: r.x + r.w,   y: r.y + r.h / 2 };
    case "top":    return { x: r.x + r.w/2, y: r.y };
    case "bottom": return { x: r.x + r.w/2, y: r.y + r.h };
  }
};

/** 根据依赖类型选 anchor 边 */
const pickAnchors = (source: NetworkNode, target: NetworkNode, type: string): [Point, Point] => {
  // 同列 / 同行特殊处理
  const sr = getNodeRect(source);
  const tr = getNodeRect(target);
  if (target.level > source.level) {
    // 后继：默认右 → 左
    if (type === "SS") {
      // 开始→开始：source.left → target.left
      return [getAnchor(source, "left"), getAnchor(target, "left")];
    }
    if (type === "FF") {
      // 完成→完成：source.right → target.right
      return [getAnchor(source, "right"), getAnchor(target, "right")];
    }
    if (type === "SF") {
      // 开始→完成：source.left → target.right
      return [getAnchor(source, "left"), getAnchor(target, "right")];
    }
    return [getAnchor(source, "right"), getAnchor(target, "left")];
  }
  // 同行 / 回边：顶/底
  if (tr.y >= sr.y + sr.h) return [getAnchor(source, "bottom"), getAnchor(target, "top")];
  if (sr.y >= tr.y + tr.h) return [getAnchor(source, "top"), getAnchor(target, "bottom")];
  // 同行兜底：左 / 右
  return [getAnchor(source, sr.x < tr.x ? "right" : "left"), getAnchor(target, tr.x < sr.x ? "right" : "left")];
};

/** 三次贝塞尔曲线路径（水平主导，自动弯折） */
const cubicPath = (s: Point, t: Point): string => {
  const dx = t.x - s.x;
  const dy = t.y - s.y;
  const horizontalDominant = Math.abs(dx) > Math.abs(dy) * 1.4;
  let c1: Point, c2: Point;
  if (horizontalDominant) {
    const off = Math.max(40, Math.abs(dx) * 0.45);
    c1 = { x: s.x + (dx > 0 ? off : -off), y: s.y };
    c2 = { x: t.x + (dx > 0 ? -off : off), y: t.y };
  } else {
    const off = Math.max(30, Math.abs(dy) * 0.45);
    c1 = { x: s.x, y: s.y + (dy > 0 ? off : -off) };
    c2 = { x: t.x, y: t.y + (dy > 0 ? -off : off) };
  }
  return `M ${s.x} ${s.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${t.x} ${t.y}`;
};

/** 计算曲线中点（用于放置 label） */
const cubicMid = (s: Point, t: Point) => {
  // 取 0.5 处：Bezier 三次中点 = (S + 3C1 + 3C2 + T) / 8
  const path = cubicPath(s, t).match(/[MC]/g) || [];
  // 解析 s, t 再算
  const dx = t.x - s.x;
  const dy = t.y - s.y;
  const horizontalDominant = Math.abs(dx) > Math.abs(dy) * 1.4;
  let c1: Point, c2: Point;
  if (horizontalDominant) {
    const off = Math.max(40, Math.abs(dx) * 0.45);
    c1 = { x: s.x + (dx > 0 ? off : -off), y: s.y };
    c2 = { x: t.x + (dx > 0 ? -off : off), y: t.y };
  } else {
    const off = Math.max(30, Math.abs(dy) * 0.45);
    c1 = { x: s.x, y: s.y + (dy > 0 ? off : -off) };
    c2 = { x: t.x, y: t.y + (dy > 0 ? -off : off) };
  }
  return {
    x: (s.x + 3 * c1.x + 3 * c2.x + t.x) / 8,
    y: (s.y + 3 * c1.y + 3 * c2.y + t.y) / 8,
  };
};

/* ═══════════ 边组件 ═══════════ */

interface EdgeProps {
  edge: NetworkEdge;
  source: NetworkNode;
  target: NetworkNode;
  isCriticalEdge: boolean;
  isHighlighted: boolean;
  isDimmed: boolean;
}

const EdgeView: React.FC<EdgeProps> = ({ edge, source, target, isCriticalEdge, isHighlighted, isDimmed }) => {
  const [s, t] = pickAnchors(source, target, edge.type);
  const d = cubicPath(s, t);
  const mid = cubicMid(s, t);
  const stroke = isCriticalEdge
    ? "#FF4D4F"
    : (isHighlighted ? "#3B82F6" : "#94A3B8");
  const strokeW = isCriticalEdge ? 2.4 : (isHighlighted ? 2.2 : 1.4);
  const dash = isDimmed ? "4 4" : undefined;
  const opacity = isDimmed ? 0.2 : 1;
  const labelBg = isCriticalEdge ? "#FFE7E5" : "#FFFFFF";

  return (
    <g style={{ opacity, transition: "opacity .15s" }} pointerEvents="none">
      {/* 箭头标记 */}
      <defs>
        <marker
          id={`arrow-${isCriticalEdge ? "c" : isHighlighted ? "h" : "n"}-${edge.source}-${edge.target}`}
          viewBox="0 0 10 10"
          refX={9} refY={5}
          markerWidth={7} markerHeight={7}
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={stroke} />
        </marker>
      </defs>

      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeW}
        strokeDasharray={dash}
        markerEnd={`url(#arrow-${isCriticalEdge ? "c" : isHighlighted ? "h" : "n"}-${edge.source}-${edge.target})`}
      />

      {/* 依赖类型 label */}
      <g transform={`translate(${mid.x}, ${mid.y})`}>
        <rect
          x={-26} y={-11} width={52} height={20} rx={4}
          fill={labelBg} stroke={stroke} strokeWidth={1}
          opacity={0.95}
        />
        <text
          textAnchor="middle" y={4} fontSize={11} fontWeight={700}
          fill={stroke} fontFamily="ui-monospace, SFMono-Regular, monospace"
        >
          {edge.label}
        </text>
      </g>
    </g>
  );
};

/* ═══════════ 主组件 ═══════════ */

const NetworkDiagram: React.FC<NetworkDiagramProps> = ({ nodes, edges, layout, onNodeClick, loading }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState<{ x: number; y: number } | null>(null);
  const [fitTrigger, setFitTrigger] = useState(0);

  // 重新布局（自适应宽度 + 居中）
  const { sized, width, height, colMap } = useMemo(
    () => reLayout([...nodes], !!edges?.length),
    [nodes, edges, fitTrigger],
  );

  // 关键 ID 集合
  const criticalIds = useMemo(() => buildCriticalIds(sized), [sized]);

  // 邻接关系（用于 hover 高亮）
  const adj = useMemo(() => {
    const out = new Map<string, Set<string>>();
    for (const e of edges) {
      if (!out.has(e.source)) out.set(e.source, new Set());
      if (!out.has(e.target)) out.set(e.target, new Set());
      out.get(e.source)!.add(e.target);
      out.get(e.target)!.add(e.source);
    }
    return out;
  }, [edges]);

  // 关键路径上的边
  const criticalEdgeSet = useMemo(() => {
    const s = new Set<string>();
    for (const e of edges) {
      if (criticalIds.has(e.source) && criticalIds.has(e.target)) s.add(`${e.source}->${e.target}`);
    }
    return s;
  }, [edges, criticalIds]);

  // 容器宽度响应式：自动 fit
  const svgContainerRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState<number>(1000);
  const [autoFit, setAutoFit] = useState<boolean>(true);
  useEffect(() => {
    const el = svgContainerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const w = e.contentRect.width;
        if (w > 0) {
          setContainerW(w);
          if (autoFit) {
            // 自动 fit 到容器宽度
            // 延后到 width 更新后再 fit
            setTimeout(() => {
              setPan({ x: 0, y: 0 });
              if (width > 0) {
                const z = Math.min(2.5, Math.max(0.3, (w - 8) / width));
                setZoom(z);
              }
            }, 30);
          }
        }
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [autoFit, width]);

  // 适应窗口
  const fitToView = useCallback(() => {
    setAutoFit(true);
    setPan({ x: 0, y: 0 });
    if (containerW > 0 && width > 0) {
      const z = Math.min(2.5, Math.max(0.3, (containerW - 8) / width));
      setZoom(z);
    } else {
      setZoom(1);
    }
    setFitTrigger((t) => t + 1);
  }, [containerW, width]);

  // 滚轮/工具栏缩放时关闭 autoFit
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setAutoFit(false);
    const factor = e.deltaY > 0 ? 0.88 : 1.12;
    setZoom((z) => Math.max(0.3, Math.min(2.5, z * factor)));
  }, []);

  // 拖拽平移
  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    // 只在空白处拖拽
    const target = e.target as SVGElement;
    if (target.tagName === "rect" && (target.getAttribute("fill") === "transparent" || target === containerRef.current?.querySelector("svg > rect"))) {
      setDragging({ x: e.clientX, y: e.clientY });
    } else if (target.tagName === "svg" || target.classList.contains("aon-bg")) {
      setDragging({ x: e.clientX, y: e.clientY });
    }
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragging) return;
    setPan((p) => ({ x: p.x + (e.clientX - dragging.x), y: p.y + (e.clientY - dragging.y) }));
    setDragging({ x: e.clientX, y: e.clientY });
  };
  const onMouseUp = () => setDragging(null);

  // 节点 hover 处理
  const onNodeEnter = (id: string) => setHovered(id);
  const onNodeLeave = () => setHovered(null);

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#94A3B8" }}>加载中...</div>;
  if (!sized.length) {
    return <Empty description="暂无网络图数据（需配置任务依赖）" style={{ padding: 60 }} />;
  }

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <style>{`
        @keyframes aonPulse { 0%,100% { filter: drop-shadow(0 0 4px rgba(255,77,79,.4)); } 50% { filter: drop-shadow(0 0 12px rgba(255,77,79,.85)); } }
        .aon-critical-node { animation: aonPulse 2.2s ease-in-out infinite; }
        .aon-bg { cursor: grab; }
        .aon-bg:active { cursor: grabbing; }
      `}</style>

      {/* 工具栏 */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 8, padding: "6px 10px", background: "#F8FAFC",
        borderRadius: 8, border: "1px solid #E2E8F0",
      }}>
        <Space size={6}>
          <Tag color="red" style={{ borderRadius: 4, fontSize: 11, margin: 0 }}>● 关键路径</Tag>
          <Tag color="default" style={{ borderRadius: 4, fontSize: 11, margin: 0 }}>● 普通节点</Tag>
          <Tag color="blue" style={{ borderRadius: 4, fontSize: 11, margin: 0 }}>FS 完成→开始</Tag>
          <Tag color="purple" style={{ borderRadius: 4, fontSize: 11, margin: 0 }}>FF 完成→完成</Tag>
          <Tag color="cyan" style={{ borderRadius: 4, fontSize: 11, margin: 0 }}>SS 开始→开始</Tag>
          <Tag color="orange" style={{ borderRadius: 4, fontSize: 11, margin: 0 }}>SF 开始→完成</Tag>
        </Space>
        <Space size={4}>
          <Tooltip title="放大">
            <Button size="small" icon={<ZoomInOutlined />} onClick={() => setZoom((z) => Math.min(2.5, z * 1.2))} />
          </Tooltip>
          <Tooltip title="缩小">
            <Button size="small" icon={<ZoomOutOutlined />} onClick={() => setZoom((z) => Math.max(0.3, z / 1.2))} />
          </Tooltip>
          <Tooltip title="适应窗口">
            <Button size="small" icon={<AimOutlined />} onClick={fitToView} />
          </Tooltip>
          <Tooltip title="重置">
            <Button size="small" icon={<ReloadOutlined />} onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} />
          </Tooltip>
          <span style={{ fontSize: 11, color: "#64748B", marginLeft: 4 }}>
            缩放 {Math.round(zoom * 100)}%
          </span>
        </Space>
      </div>

      {/* 图域 */}
      <div
        ref={svgContainerRef}
        style={{
          overflow: "auto",
          borderRadius: 12,
          border: "1px solid #E2E8F0",
          background: "linear-gradient(180deg,#FAFBFC 0%,#F1F5F9 100%)",
          minHeight: 520,
        }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <svg
          className="aon-bg"
          width={Math.max(containerW - 4, width * zoom)}
          height={Math.max(560, height * zoom + 40)}
          viewBox={`${-pan.x / zoom} ${-pan.y / zoom} ${width / zoom} ${(height / zoom) + 40}`}
          style={{ display: "block", userSelect: "none" }}
        >
          <defs>
            <linearGradient id="aonCritHeader" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#FFE7E5" />
              <stop offset="1" stopColor="#FFF1F0" />
            </linearGradient>
            <pattern id="aonGrid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#E2E8F0" strokeWidth="0.5" />
            </pattern>
          </defs>

          {/* 背景网格（覆盖整张画布，避免随 pan/zoom 留白） */}
          <rect x={-2000} y={-2000} width={width + 4000} height={height + 4040} fill="url(#aonGrid)" />

          {/* 边（先画线，再画节点，避免覆盖） */}
          <g>
            {edges.map((e) => {
              const source = sized.find((n) => n.id === e.source);
              const target = sized.find((n) => n.id === e.target);
              if (!source || !target) return null;
              const isCrit = criticalEdgeSet.has(`${e.source}->${e.target}`);
              const isHigh = hovered && (hovered === e.source || hovered === e.target);
              const isDimmed = !!hovered && !isHigh && !isCrit;
              return (
                <EdgeView
                  key={`${e.source}->${e.target}`}
                  edge={e}
                  source={source}
                  target={target}
                  isCriticalEdge={isCrit}
                  isHighlighted={!!isHigh}
                  isDimmed={isDimmed}
                />
              );
            })}
          </g>

          {/* 节点 */}
          <g>
            {sized.map((n) => {
              const w = (n as any).__w || NODE_W_BASE;
              const adjSet = adj.get(n.id) || new Set();
              const isHigh = hovered === n.id || adjSet.has(hovered || "");
              const isDimmed = !!hovered && !isHigh;
              return (
                <NodeBox
                  key={n.id}
                  node={n}
                  w={w}
                  isHighlighted={!!isHigh}
                  isDimmed={isDimmed}
                  onClick={() => onNodeClick?.(n)}
                  onMouseEnter={() => onNodeEnter(n.id)}
                  onMouseLeave={onNodeLeave}
                />
              );
            })}
          </g>
        </svg>
      </div>

      {/* 底部信息条 */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginTop: 8, padding: "6px 10px", background: "#F8FAFC",
        borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 12, color: "#64748B",
      }}>
        <Space size={12}>
          <span>节点 <strong style={{ color: "#0F172A" }}>{sized.length}</strong> 个</span>
          <span>边 <strong style={{ color: "#0F172A" }}>{edges.length}</strong> 条</span>
          <span>层 <strong style={{ color: "#0F172A" }}>{layout.levels || colMap.size}</strong> 层</span>
          <span>关键 <strong style={{ color: "#EF4444" }}>{criticalIds.size}</strong> 节点</span>
        </Space>
        <span style={{ fontSize: 11 }}>
          💡 滚轮缩放 · 拖拽平移 · 悬停高亮紧前紧后
        </span>
      </div>

      {/* 悬浮时显示节点详情卡 */}
      {hovered && (() => {
        const n = sized.find((nn) => nn.id === hovered);
        if (!n) return null;
        return (
          <div style={{
            position: "absolute", top: 60, right: 16, width: 280,
            background: "#fff", borderRadius: 10, padding: "10px 12px",
            boxShadow: "0 8px 24px rgba(15,23,42,.12)",
            border: n.isCritical ? "2px solid #FF4D4F" : "1px solid #E2E8F0",
            zIndex: 10, fontSize: 12,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              {n.isCritical && <FireOutlined style={{ color: "#FF4D4F" }} />}
              <strong style={{ fontSize: 13, color: n.isCritical ? "#CF1322" : "#0F172A" }}>{n.name}</strong>
              {n.wbsCode && <Tag color={n.isCritical ? "red" : "default"} style={{ marginLeft: "auto", fontSize: 10 }}>{n.wbsCode}</Tag>}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 12px", color: "#475569" }}>
              <span>工期：<strong>{n.duration}d</strong></span>
              <span>进度：<strong>{Math.round(n.progress)}%</strong></span>
              <span>ES：<strong style={{ color: "#3B82F6" }}>{n.es}</strong></span>
              <span>EF：<strong style={{ color: "#3B82F6" }}>{n.ef}</strong></span>
              <span>LS：<strong style={{ color: "#F59E0B" }}>{n.ls}</strong></span>
              <span>LF：<strong style={{ color: "#F59E0B" }}>{n.lf}</strong></span>
              <span>TF：<strong style={{ color: n.isCritical ? "#EF4444" : (n.tf > 0 ? "#F59E0B" : "#94A3B8") }}>{n.tf}d</strong></span>
              <span>FF：<strong style={{ color: n.ff > 0 ? "#06B6D4" : "#94A3B8" }}>{n.ff}d</strong></span>
            </div>
            {n.isCritical && (
              <div style={{ marginTop: 6, padding: "4px 8px", background: "#FFF1F0", borderRadius: 4, color: "#CF1322", fontSize: 11, fontWeight: 600 }}>
                ⚡ 关键路径节点：任何延误都会推迟项目总工期
              </div>
            )}
            {onNodeClick && (
              <div style={{ marginTop: 6, textAlign: "right" }}>
                <Button type="link" size="small" style={{ padding: 0, fontSize: 11 }} onClick={() => onNodeClick(n)}>
                  查看任务详情 →
                </Button>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
};

export default NetworkDiagram;
