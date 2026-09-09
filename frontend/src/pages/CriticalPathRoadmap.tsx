import React, { useState, useEffect, useMemo, useRef } from "react";
import { Card, Typography, Select, Spin, Empty, Alert, Tag, Tooltip, Space, Tabs, Table, message } from "antd";
import {
  ApartmentOutlined, ArrowRightOutlined, FireOutlined,
  ClockCircleOutlined, WarningOutlined,
  ProjectOutlined, ShareAltOutlined,
} from "@ant-design/icons";
import { motion } from "framer-motion";
import dayjs from "dayjs";
import ReactECharts from "echarts-for-react";
import * as echarts from "echarts";
import { projectApi } from "../api";
import NetworkDiagram, { NetworkNode, NetworkEdge, NetworkLayout } from "../components/NetworkDiagram";

const { Title, Text } = Typography;

/* ═══════════════════ 类型定义 ═══════════════════ */

interface CPTask {
  id: string;
  name: string;
  wbs_code: string | null;
  duration_days: number;
  es: number; ef: number; ls: number; lf: number;
  total_float: number; free_float: number;
  is_critical: boolean;
  start_date: string; end_date: string;
  progress: number; status: string; priority: number;
  assignee_name: string | null;
  dependency_ids: string[];
}

interface GanttBar {
  taskId: string; name: string; start: string; end: string;
  duration: number; progress: number; status: string; priority: number;
  isCritical: boolean; es: number; ef: number; ls: number; lf: number;
  tf: number; ff: number; wbsCode: string | undefined;
  assigneeName: string | undefined; dependencyIds: string[];
}

interface NetworkNode {
  id: string; name: string; shortName: string;
  x: number; y: number;
  es: number; ef: number; ls: number; lf: number;
  tf: number; ff: number; isCritical: boolean;
  duration: number; level: number;
  progress: number; status: string; wbsCode: string | undefined;
}

interface NetworkEdge {
  source: string; target: string; label: string; type: string; lag: number;
}

interface CPData {
  project_id: string;
  project_name: string;
  anchor_date: string | null;
  project_duration_days: number;
  has_dependencies: boolean;
  task_count: number;
  tasks: CPTask[];
  critical_path: string[];
  critical_path_names: string[];
  gantt_data?: GanttBar[];
  network_data?: {
    nodes: NetworkNode[];
    edges: NetworkEdge[];
    layout: { width: number; height: number; levels: number; nodeSize?: { w: number; h: number } };
  };
}

const STATUS_LABEL: Record<string, string> = {
  todo: "待办", doing: "进行中", in_progress: "进行中", done: "已完成",
  blocked: "阻塞", review: "评审", testing: "测试中",
};
const STATUS_COLOR: Record<string, string> = {
  todo: "#94A3B8", doing: "#3B82F6", in_progress: "#3B82F6", done: "#10B981",
  blocked: "#EF4444", review: "#8B5CF6", testing: "#F59E0B",
};

/* ═══════════════════ 主组件 ═══════════════════ */

const CriticalPathRoadmap: React.FC = () => {
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [data, setData] = useState<CPData | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("gantt");
  const ganttRef = useRef<ReactECharts>(null);

  useEffect(() => {
    projectApi.list().then((r: any) => setProjects(r?.items || r || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) { setData(null); return; }
    setLoading(true);
    projectApi.criticalPath(projectId)
      .then((r: any) => setData(r))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [projectId]);

  const criticalCount = data ? data.tasks.filter((t) => t.is_critical).length : 0;
  const floatCount = data ? data.tasks.filter((t) => !t.is_critical && t.total_float > 0).length : 0;

  /* ── 统计卡片 ── */
  const StatCard = ({ icon, label, value, suffix, color }: any) => (
    <motion.div
      initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
      style={{
        flex: 1, minWidth: 150, background: "#fff", borderRadius: 16, padding: "14px 16px",
        border: "1px solid #EEF2F7", boxShadow: "0 6px 18px rgba(15,23,42,.04)",
        display: "flex", alignItems: "center", gap: 12,
      }}
    >
      <div style={{ width: 40, height: 40, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", background: `${color}1A`, color }}>{icon}</div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: "#0F172A", lineHeight: 1.1 }}>{value}{suffix && <span style={{ fontSize: 13, color: "#64748B", fontWeight: 500 }}> {suffix}</span>}</div>
        <div style={{ fontSize: 12, color: "#64748B" }}>{label}</div>
      </div>
    </motion.div>
  );

  /* ── 甘特图 Option（echarts）── */
  const ganttOption = useMemo(() => {
    if (!data || !data.anchor_date || !(data.gantt_data || []).length) return {};
    const bars = data.gantt_data!;
    const anchor = dayjs(data.anchor_date);
    const totalDays = Math.max(data.project_duration_days || 30, 30);

    // 计算日期范围
    const minDate = anchor;
    const maxDate = anchor.add(totalDays, "day");

    // 任务 Y 轴数据（倒序让第一个任务在顶部）
    const categories = [...bars].reverse().map((b) =>
      b.name.length > 18 ? b.name.slice(0, 17) + ".." : b.name
    );
    const categoryMap = [...bars].reverse().map((b) => b.taskId);

    // 今日位置
    const today = dayjs().startOf("day");
    const todayOffset = today.diff(anchor, "day");

    // 构建系列数据
    const seriesData: any[] = [];
    const linkData: any[] = [];       // 依赖连线
    const markLineData: any[] = [];   // 今日线

    bars.forEach((bar, idx) => {
      const revIdx = bars.length - 1 - idx; // 倒序后的索引
      const startDay = dayjs(bar.start).diff(anchor, "day");
      const dur = Math.max(bar.duration, 1);

      seriesData.push({
        value: [startDay, revIdx, dur, bar.progress || 0, bar.isCritical ? 1 : 0],
        itemStyle: {
          color: bar.isCritical
            ? new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: "#FF4D4F" },
              { offset: 1, color: "#FF7A45" },
            ])
            : new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: "#3B82F6" },
              { offset: 1, color: "#06B6D4" },
            ]),
          borderRadius: [4, 4, 4, 4],
          borderColor: bar.isCritical ? "#ff7875" : "#93c5fd",
          borderWidth: 1,
        },
      });

      // 依赖箭头连线
      (bar.dependencyIds || []).forEach((depId) => {
        const depIdx = bars.findIndex((b) => b.taskId === depId);
        if (depIdx >= 0) {
          const depRevIdx = bars.length - 1 - depIdx;
          const depStartDay = dayjs(bars[depIdx].start).diff(anchor, "day");
          const depDur = Math.max(bars[depIdx].duration, 1);
          linkData.push({
            coords: [
              [depStartDay + depDur, depRevIdx],
              [startDay, revIdx],
            ],
            lineStyle: {
              color: "#94A3B8",
              width: 1.2,
              type: "solid",
              curveness: 0.15,
            },
            symbol: ["none", "arrow"],
            symbolSize: [6, 6],
          });
        }
      });
    });

    // 今日线
    if (todayOffset >= -5 && todayOffset <= totalDays + 5) {
      markLineData.push({
        xAxis: todayOffset,
        lineStyle: { color: "#EF4444", width: 2, type: "dashed" },
        label: { formatter: "今天", position: "end", color: "#EF4444", fontWeight: "bold", fontSize: 11 },
      });
    }

    return {
      tooltip: {
        trigger: "item",
        confine: true,
        formatter(params: any) {
          if (params.componentType === "markLine") return params.name || "";
          const d = bars[params.dataIndex];
          if (!d) return "";
          return `
            <div style="font-size:12px;line-height:1.8">
              <strong>${d.name}</strong><br/>
              工期: ${d.duration}d &nbsp;|&nbsp; 进度: ${Math.round(d.progress)}%<br/>
              ES:${d.es} EF:${d.ef} LS:${d.ls} LF:${d.lf}<br/>
              总浮动: ${d.tf}d &nbsp;|&nbsp; ${d.isCritical ? '<span style="color:#EF4444;font-weight:bold">关键路径</span>' : '非关键'}
            </div>
          `;
        },
      },
      grid: { left: 160, right: 24, top: 10, bottom: 24 },
      xAxis: {
        type: "value",
        min: -1,
        max: totalDays + 2,
        interval: 7,
        axisLabel: {
          formatter: (v: number) => anchor.add(v, "day").format("MM-DD"),
          fontSize: 11, color: "#64748B",
        },
        splitLine: { show: true, lineStyle: { color: "#EEF2F7", type: "solid" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "category",
        data: categories,
        inverse: true,
        axisLabel: { fontSize: 11, color: "#334155", width: 150, overflow: "truncate" },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: "#F8FAFC" } },
      },
      series: [
        {
          type: "custom",
          renderItem(params: any, api: any) {
            const v = api.value();
            // 防御：markLine（今日线）等非数组数据点会作为标量传入，跳过避免崩溃
            if (!Array.isArray(v) || v.length < 5) return { type: "group", children: [] };
            const [start, yIdx, dur, progress, isCrit] = v;
            const h = 24;
            const coordStart = api.coord([start, yIdx]);
            const coordEnd = api.coord([start + dur, yIdx]);
            const x = coordStart[0];
            const y = coordStart[1] - h / 2;
            const w = coordEnd[0] - x;

            // 进度填充宽度
            const progW = w * Math.min(100, Math.max(0, progress)) / 100;

            const group: any = {
              type: "group",
              children: [
                // 背景条
                {
                  type: "rect",
                  shape: { x, y, width: w, height: h, r: 4 },
                  style: api.style(),
                },
                // 进度遮罩
                ...(progress > 0 ? [{
                  type: "rect",
                  shape: { x, y, width: progW, height: h, r: [4, 0, 0, 4] },
                  style: { fill: "rgba(15,23,42,.22)" },
                }] : []),
                // 文字标签
                {
                  type: "text",
                  style: {
                    x: x + 6, y: y + h / 2,
                    text: `${dur}d${isCrit ? " ⚡" : ""}`,
                    fill: "#fff", fontSize: 10, fontWeight: 600,
                    textVerticalAlign: "middle",
                    textShadowColor: "rgba(0,0,0,.25)", textShadowBlur: 2,
                  },
                },
              ],
            };

            return group;
          },
          encode: { x: 0, y: 1 },
          data: seriesData,
          z: 10,
          markLine: { silent: true, data: markLineData, symbol: "none" },
        },
        // 依赖连线层
        ...(linkData.length > 0 ? [{
          type: "lines",
          coordinateSystem: "cartesian2d",
          data: linkData,
          z: 5,
          silent: true,
        }] : []),
      ],
    };
  }, [data]);

  /* ── 网络图（AON 紧前逻辑关系图）—— 改用专业 SVG 自绘 ── */
  const networkData = useMemo<{
    nodes: NetworkNode[]; edges: NetworkEdge[]; layout: NetworkLayout;
  } | null>(() => {
    const nd = data?.network_data;
    if (!nd || !nd.nodes?.length) return null;
    return {
      nodes: nd.nodes as NetworkNode[],
      edges: nd.edges as NetworkEdge[],
      layout: nd.layout as NetworkLayout,
    };
  }, [data]);

  /** 点击网络图节点：跳转到任务详情 / 复制 ID */
  const handleNetworkNodeClick = (n: NetworkNode) => {
    const t = data?.tasks?.find((tk: any) => tk.id === n.id);
    if (t) {
      message.info(`任务 [${t.wbs_code || n.id.slice(0, 6)}] ${t.name} · 工期 ${n.duration}d · TF=${n.tf}d`);
    } else {
      // 兜底：复制任务 ID
      try {
        navigator.clipboard?.writeText(n.id);
        message.success(`已复制任务 ID：${n.id.slice(0, 8)}…`);
      } catch { /* ignore */ }
    }
  };

  /* ── 浮动时间表格列 ── */
  const floatColumns = [
    { title: "任务", dataIndex: "name", key: "name", width: 200,
      render: (t: string, r: CPTask) => (
        <span>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: r.is_critical ? "#EF4444" : STATUS_COLOR[r.status] || "#94A3B8", marginRight: 6 }} />
          {t}
        </span>
      ),
    },
    { title: "WBS", dataIndex: "wbs_code", key: "wbs_code", width: 90, ellipsis: true },
    { title: "工期(d)", dataIndex: "duration_days", key: "dur", width: 70, align: "center" },
    { title: "ES", dataIndex: "es", key: "es", width: 46, align: "center" },
    { title: "EF", dataIndex: "ef", key: "ef", width: 46, align: "center" },
    { title: "LS", dataIndex: "ls", key: "ls", width: 46, align: "center" },
    { title: "LF", dataIndex: "lf", key: "lf", width: 46, align: "center" },
    { title: "总浮动(TF)", dataIndex: "total_float", key: "tf", width: 86, align: "center",
      render: (v: number, r: CPTask) => (
        <span style={{ color: r.is_critical ? "#EF4444" : v > 0 ? "#F59E0B" : "#94A3B8", fontWeight: r.is_critical ? 700 : 400 }}>
          {v}d
        </span>
      ),
    },
    { title: "自由浮动(FF)", dataIndex: "free_float", key: "ff", width: 88, align: "center",
      render: (v: number) => <span style={{ color: v > 0 ? "#06B6D4" : "#94A3B8" }}>{v}d</span>,
    },
    { title: "状态", dataIndex: "status", key: "status", width: 80,
      render: (s: string) => <Tag color={STATUS_COLOR[s]} style={{ borderRadius: 4, fontSize: 11 }}>{STATUS_LABEL[s] || s}</Tag>,
    },
    { title: "进度", dataIndex: "progress", key: "prog", width: 70, align: "center",
      render: (p: number) => `${Math.round(p)}%`,
    },
  ];

  const tabItems = [
    {
      key: "gantt",
      label: (
        <span><ProjectOutlined /> 甘特图</span>
      ),
      children: (
        <Card className="card-hover" style={{ borderRadius: 16 }}>
          {(data?.gantt_data || []).length > 0 ? (
            <ReactECharts
              ref={ganttRef}
              option={ganttOption}
              style={{ height: Math.max(400, (data!.tasks!.length || 10) * 42 + 60), width: "100%" }}
              opts={{ renderer: "canvas" }}
              notMerge={true}
              lazyUpdate={true}
            />
          ) : (
            <Empty description="暂无甘特图数据" style={{ padding: 60 }} />
          )}
        </Card>
      ),
    },
    {
      key: "network",
      label: (
        <span><ShareAltOutlined /> 紧前逻辑关系图（AON）</span>
      ),
      children: (
        <Card className="card-hover" style={{ borderRadius: 16 }} bodyStyle={{ padding: 12 }}>
          {networkData ? (
            <NetworkDiagram
              nodes={networkData.nodes}
              edges={networkData.edges}
              layout={networkData.layout}
              onNodeClick={handleNetworkNodeClick}
            />
          ) : (
            <Empty description="暂无网络图数据（需配置任务依赖）" style={{ padding: 60 }} />
          )}
          {/* PMBOK 说明 */}
          <Alert
            type="info" showIcon
            message="PMBOK 紧前绘图法（Precedence Diagramming Method / Activity-on-Node）"
            description={
              <div style={{ fontSize: 12, lineHeight: 1.8 }}>
                节点表示活动（Task），含 ES/EF/LS/LF 四个时间参数与总浮动 TF、自由浮动 FF。边表示逻辑依赖关系：
                <Space size={12} wrap style={{ marginTop: 4 }}>
                  <Tag color="blue">FS 完成→开始</Tag>
                  <Tag color="purple">FF 完成→完成</Tag>
                  <Tag color="cyan">SS 开始→开始</Tag>
                  <Tag color="orange">SF 开始→完成</Tag>
                </Space>
                <br />红色高亮节点为<strong>关键路径</strong>上的活动（TF ≤ 0），任何延误都将影响项目总工期。
                <br />支持滚轮缩放、拖拽平移、悬停高亮紧前/紧后活动。
              </div>
            }
            style={{ marginTop: 12, borderRadius: 10 }}
          />
        </Card>
      ),
    },
    {
      key: "float",
      label: (
        <span><ClockCircleOutlined /> 浮动分析表</span>
      ),
      children: (
        <Card className="card-hover" style={{ borderRadius: 16 }}>
          <Table
            dataSource={data?.tasks || []}
            columns={floatColumns}
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 900 }}
            rowClassName={(r: CPTask) => r.is_critical ? "cpm-critical-row" : ""}
          />
          <style>{`.cpm-critical-row { background: #FFF1F0 !important; } .cpm-critical-row:hover > td { background: #FFE7E5 !important; }`}</style>
        </Card>
      ),
    },
  ];

  return (
    <div>
      <style>{`
        @keyframes cpmPulse { 0%,100%{box-shadow:0 0 6px rgba(255,77,79,.45)} 50%{box-shadow:0 0 18px rgba(255,77,79,.9)} }
        .cpm-critical { animation: cpmPulse 2.2s ease-in-out infinite; }
      `}</style>

      {/* 页头 */}
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            关键路径路线图 <Tag color="red" style={{ borderRadius: 6, marginLeft: 4 }}>CPM</Tag>
          </Title>
          <Text type="secondary">关键路径法 · 基于 PMBOK 第6章 · 支持 FS/FF/SS/SF 四种依赖关系与延隔</Text>
        </div>
        <Select
          allowClear placeholder="选择项目"
          data-tour="cp-sel"
          style={{ width: 240 }}
          value={projectId || undefined}
          onChange={(v) => setProjectId(v || "")}
          options={projects.map((p: any) => ({ label: p.name, value: p.id }))}
          showSearch optionFilterProp="label"
        />
      </div>

      <Spin spinning={loading}>
        {!projectId ? (
          <Empty description="请选择一个项目以查看关键路径路线图" style={{ marginTop: 80 }} />
        ) : !data || data.task_count === 0 ? (
          <Empty description="该项目暂无任务（里程碑除外），无法计算关键路径" style={{ marginTop: 80 }} />
        ) : (
          <div style={{ marginTop: 18 }}>
            {/* 统计卡片 */}
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 16 }}>
              <StatCard icon={<ClockCircleOutlined />} label="项目总工期" value={data.project_duration_days} suffix="天" color="#4F46E5" />
              <StatCard icon={<FireOutlined />} label="关键任务" value={`${criticalCount}`} suffix={`/ ${data.task_count}`} color="#EF4444" />
              <StatCard icon={<ApartmentOutlined />} label="关键路径长度" value={data.critical_path.length} suffix="个节点" color="#F59E0B" />
              <StatCard icon={<WarningOutlined />} label="含浮动缓冲任务" value={floatCount} suffix="个" color="#06B6D4" />
            </div>

            {/* 依赖提示 */}
            {!data.has_dependencies && (
              <Alert
                type="info" showIcon
                message="尚未设置任务依赖"
                description="当前任务之间未配置前后置依赖，关键路径即各任务自身。在「任务」页为任务添加依赖后，即可获得真实的关键路径与浮动分析。"
                style={{ borderRadius: 12, marginBottom: 16 }}
              />
            )}

            {/* 关键路径链条 */}
            <Card className="card-hover" style={{ borderRadius: 16, marginBottom: 16 }} data-tour="cp-path">
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <FireOutlined style={{ color: "#EF4444" }} />
                <Text strong style={{ fontSize: 15 }}>关键路径（Critical Path）</Text>
                <Tag color="red" style={{ borderRadius: 6 }}>{data.critical_path.length} 节点</Tag>
              </div>
              {data.critical_path_names.length === 0 ? (
                <Text type="secondary">无（请添加任务依赖）</Text>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 4 }}>
                  {data.critical_path_names.map((name, i) => (
                    <React.Fragment key={i}>
                      <motion.span
                        initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: i * 0.08 }}
                        style={{
                          padding: "6px 12px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                          color: "#fff", background: "linear-gradient(90deg,#ff4d4f,#ff7a45)",
                          boxShadow: "0 0 12px rgba(255,77,79,.5)", whiteSpace: "nowrap",
                        }}
                      >
                        {name}
                      </motion.span>
                      {i < data.critical_path_names.length - 1 && (
                        <ArrowRightOutlined style={{ color: "#EF4444", fontSize: 12 }} />
                      )}
                    </React.Fragment>
                  ))}
                </div>
              )}
            </Card>

            {/* Tab 切换：甘特图 / 网络图 / 浮动表 */}
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={tabItems}
              size="middle"
              style={{ borderRadius: 16, overflow: "hidden" }}
            />
          </div>
        )}
      </Spin>
    </div>
  );
};

export default CriticalPathRoadmap;
