import React, { useEffect, useMemo, useState } from "react";
import {
  Card, Row, Col, Statistic, Table, Tag, Typography, Spin,
  Empty, Alert, Tabs, Input, Button, Space, Radio, Tooltip, Badge,
} from "antd";
import {
  ApiOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
  DatabaseOutlined, DollarOutlined, RiseOutlined,
  ArrowUpOutlined, ArrowDownOutlined, ThunderboltOutlined,
  FireOutlined, ProjectOutlined, AppstoreOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { http } from "../api/http";

const { Title, Text } = Typography;

/* ── 接口定义 ──────────────────────────────────────────── */

interface MonitorStats {
  total_calls: number; total_tokens: number; avg_latency_ms: number;
  success_rate: number; calls_by_provider: Record<string, number>;
  calls_by_agent: Record<string, number>;
  recent_errors: Array<{ agent_type: string; title: string; time: string; session_id: string }>;
  recent_calls_7d: number;
  real_total_calls: number; real_total_tokens: number;
  real_total_cost_usd: number; real_avg_latency_ms: number; real_success_rate: number;
}

interface WindowAgg {
  calls: number; tokens: number; cost_usd: number; errors: number;
  error_rate?: number; avg_latency_ms?: number;
}

interface RealtimeData {
  today: WindowAgg & { calls_by_provider: Record<string, number>; calls_by_task: Record<string, number> };
  yesterday: WindowAgg;
  last_hour: WindowAgg;
  current_hour: WindowAgg;
  this_week: WindowAgg;
  this_month: WindowAgg;
  hourly_today: Array<{ hour: number; calls: number; tokens: number; cost_usd: number; errors: number }>;
  cost_by_provider_today: Array<{ provider: string; model: string; calls: number; tokens: number; cost_usd: number }>;
  cost_by_task_today: Array<{ task_name: string; calls: number; tokens: number; cost_usd: number; error_rate: number }>;
  cost_by_project_today: Array<{ project_id: string; project_name: string; calls: number; tokens: number; cost_usd: number }>;
  last_call_at: string | null;
  last_call_provider: string | null;
  last_call_model: string | null;
  comparison: {
    calls_delta_pct: number; cost_delta_pct: number;
    tokens_delta_pct: number; errors_delta_pct: number;
  };
  window_start: string | null;
  window_end: string | null;
}

interface CallRecord {
  id: string; agent_type: string; title: string; summary: string;
  status: string; project_id: string | null; user_id: string;
  message_count: number; created_at: string | null; updated_at: string | null;
}

interface UsageItem {
  provider: string; model: string; calls: number; total_tokens: number;
  prompt_tokens: number; completion_tokens: number; avg_latency_ms: number;
  total_cost_usd: number; success_rate: number;
}

interface TrendPoint { date: string; calls: number; tokens: number; cost_usd: number; }

type TrendWindow = 1 | 7 | 30 | 90;

/* ── 工具方法 ──────────────────────────────────────────── */

const fmtMoney = (v: number) => `$${(v || 0).toFixed(4)}`;
const fmtInt = (v: number) => (v || 0).toLocaleString();
const fmtPct = (v: number) => `${((v || 0) * 100).toFixed(1)}%`;

function timeAgo(iso: string | null): string {
  if (!iso) return "暂无";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)} 秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

function deltaTag(pct: number): React.ReactNode {
  if (pct === 0) return <Text type="secondary">—</Text>;
  const up = pct > 0;
  const color = up ? "#EF4444" : "#10B981"; // 上涨红、下跌绿（成本视角）
  return (
    <Text style={{ color, fontSize: 12 }}>
      {up ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {Math.abs(pct).toFixed(1)}%
    </Text>
  );
}

/* ── 主组件 ──────────────────────────────────────────── */

const AIMonitor: React.FC = () => {
  const [stats, setStats] = useState<MonitorStats | null>(null);
  const [realtime, setRealtime] = useState<RealtimeData | null>(null);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [totalCalls, setTotalCalls] = useState(0);
  const [usage, setUsage] = useState<{ items: UsageItem[]; summary: any }>({ items: [], summary: {} });
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [trendWindow, setTrendWindow] = useState<TrendWindow>(30);
  const [loading, setLoading] = useState(true);
  const [realtimeLoading, setRealtimeLoading] = useState(true);
  const [callsLoading, setCallsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [sliceTab, setSliceTab] = useState<"provider" | "task" | "project">("provider");

  // A/B 对比
  const [modelA, setModelA] = useState("openai/gpt-4o");
  const [modelB, setModelB] = useState("deepseek/deepseek-chat");
  const [abResult, setAbResult] = useState<any>(null);
  const [abLoading, setAbLoading] = useState(false);

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { loadTrend(); /* eslint-disable-next-line */ }, [trendWindow]);

  // 30 秒自动刷新 realtime（含自动刷新"最后 X 秒前"提示）
  useEffect(() => {
    const t = setInterval(() => {
      loadRealtime(true);
      setLastRefresh(new Date());
    }, 30_000);
    return () => clearInterval(t);
  }, []);

  /* ── 切片表列定义（必须在所有早 return 之前） ─────────── */
  const sliceColumns = useMemo(() => {
    if (sliceTab === "provider") {
      return [
        { title: "Provider", dataIndex: "provider", width: 100, render: (v: string) => <Tag color="purple">{v}</Tag> },
        { title: "模型", dataIndex: "model", ellipsis: true },
        { title: "调用", dataIndex: "calls", width: 80, sorter: (a: any, b: any) => a.calls - b.calls },
        { title: "Token", dataIndex: "tokens", width: 100, render: (v: number) => fmtInt(v) },
        { title: "成本(USD)", dataIndex: "cost_usd", width: 120, render: (v: number) => <Text strong style={{ color: "#D97706" }}>{fmtMoney(v)}</Text>, sorter: (a: any, b: any) => a.cost_usd - b.cost_usd },
      ];
    }
    if (sliceTab === "task") {
      return [
        { title: "任务/Agent", dataIndex: "task_name", render: (v: string) => <Tag color="cyan">{v || "unknown"}</Tag> },
        { title: "调用", dataIndex: "calls", width: 80, sorter: (a: any, b: any) => a.calls - b.calls },
        { title: "Token", dataIndex: "tokens", width: 100, render: (v: number) => fmtInt(v) },
        { title: "错误率", dataIndex: "error_rate", width: 100, render: (v: number) => <Tag color={v >= 0.1 ? "red" : "green"}>{fmtPct(v)}</Tag> },
        { title: "成本(USD)", dataIndex: "cost_usd", width: 120, render: (v: number) => <Text strong style={{ color: "#D97706" }}>{fmtMoney(v)}</Text>, sorter: (a: any, b: any) => a.cost_usd - b.cost_usd },
      ];
    }
    return [
      { title: "项目", dataIndex: "project_name", render: (v: string, r: any) => <span><ProjectOutlined /> {v || "(无项目)"}{r.project_id ? <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>#{r.project_id.slice(0, 8)}</Text> : null}</span> },
      { title: "调用", dataIndex: "calls", width: 80, sorter: (a: any, b: any) => a.calls - b.calls },
      { title: "Token", dataIndex: "tokens", width: 100, render: (v: number) => fmtInt(v) },
      { title: "成本(USD)", dataIndex: "cost_usd", width: 120, render: (v: number) => <Text strong style={{ color: "#D97706" }}>{fmtMoney(v)}</Text>, sorter: (a: any, b: any) => a.cost_usd - b.cost_usd },
    ];
  }, [sliceTab]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [statsRes, usageRes] = await Promise.all([
        http.get("/ai/monitor/stats"),
        http.get("/ai/monitor/usage"),
      ]);
      setStats(statsRes.data);
      setUsage(usageRes.data);
      setError(null);
    } catch (err: any) {
      const fallback: MonitorStats = {
        total_calls: 0, total_tokens: 0, avg_latency_ms: 0, success_rate: 0,
        calls_by_provider: {}, calls_by_agent: {}, recent_errors: [],
        recent_calls_7d: 0, real_total_calls: 0, real_total_tokens: 0,
        real_total_cost_usd: 0, real_avg_latency_ms: 0, real_success_rate: 0,
      };
      setStats(fallback);
      setError(err?.response?.data?.detail || "监控数据暂不可用（显示空数据）");
    } finally { setLoading(false); }
    loadCalls();
    loadRealtime(false);
  };

  const loadRealtime = async (silent: boolean) => {
    try {
      if (!silent) setRealtimeLoading(true);
      const res = await http.get("/ai/monitor/realtime");
      setRealtime(res.data);
    } catch { /* 静默；realtime 缺失不影响累计 KPI */ }
    finally { if (!silent) setRealtimeLoading(false); }
  };

  const loadCalls = async (page = 1) => {
    try {
      setCallsLoading(true);
      const res = await http.get("/ai/monitor/calls", { params: { page, page_size: 20 } });
      setCalls(res.data.items);
      setTotalCalls(res.data.total);
    } catch { /* 静默 */ }
    finally { setCallsLoading(false); }
  };

  const loadTrend = async () => {
    try {
      const res = await http.get("/ai/monitor/usage/trend", { params: { days: trendWindow } });
      setTrend(res.data.trend || []);
    } catch { /* 静默 */ }
  };

  const runABTest = async () => {
    try {
      setAbLoading(true);
      const res = await http.get("/ai/monitor/ab-test", { params: { model_a: modelA, model_b: modelB } });
      setAbResult(res.data);
    } catch (e: any) {
      setAbResult({ error: e?.response?.data?.detail || "对比失败" });
    } finally { setAbLoading(false); }
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
        <Spin size="large" tip="加载监控数据..." />
      </div>
    );
  }
  const showWarningBanner = error && !!stats;
  if (!stats) return <Empty description="暂无监控数据" />;

  const agentRanking = Object.entries(stats.calls_by_agent || {})
    .sort(([, a], [, b]) => b - a).slice(0, 10);
  const maxAgentCalls = agentRanking.length > 0 ? agentRanking[0][1] : 1;
  const providerEntries = Object.entries(stats.calls_by_provider || {});
  const totalProviderCalls = providerEntries.reduce((s, [, v]) => s + v, 0) || 1;

  /* ── 趋势图 ──────────────────────────────────────────── */
  const W = 640, H = 200, pad = 30;
  const maxCost = Math.max(1, ...trend.map(t => t.cost_usd), 0.001);
  const maxCalls = Math.max(1, ...trend.map(t => t.calls));
  const n = trend.length;
  const xAt = (i: number) => pad + (n <= 1 ? 0 : (i / (n - 1)) * (W - pad * 2));
  const costPath = trend.map((t, i) =>
    `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${(H - pad - (t.cost_usd / maxCost) * (H - pad * 2)).toFixed(1)}`).join(" ");
  const callPath = trend.map((t, i) =>
    `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${(H - pad - (t.calls / maxCalls) * (H - pad * 2)).toFixed(1)}`).join(" ");

  /* ── 24h 实时柱状图 ────────────────────────────────────── */
  const hourly = realtime?.hourly_today || [];
  const HW = 640, HH = 160, Hpad = 24;
  const hourMaxCost = Math.max(0.0001, ...hourly.map(h => h.cost_usd));
  const hourMaxCalls = Math.max(1, ...hourly.map(h => h.calls));
  const barW = (HW - Hpad * 2) / 24;
  const nowHour = new Date().getHours();

  /* ── 切片表（provider / task / project） ───────────────── */
  const sliceData = realtime
    ? (sliceTab === "provider" ? realtime.cost_by_provider_today
       : sliceTab === "task" ? realtime.cost_by_task_today
       : realtime.cost_by_project_today)
    : [];

  /* ── 表格列：累计模型成本与性能 ──────────────────────────── */
  const usageColumns = [
    { title: "Provider", dataIndex: "provider", key: "provider", width: 110,
      render: (v: string) => <Tag color="purple">{v}</Tag> },
    { title: "模型", dataIndex: "model", key: "model", ellipsis: true },
    { title: "调用", dataIndex: "calls", key: "calls", width: 80,
      sorter: (a: UsageItem, b: UsageItem) => a.calls - b.calls },
    { title: "Token", dataIndex: "total_tokens", key: "total_tokens", width: 100,
      render: (v: number) => v.toLocaleString() },
    { title: "平均延迟", dataIndex: "avg_latency_ms", key: "avg_latency_ms", width: 100,
      render: (v: number) => `${v} ms`, sorter: (a: UsageItem, b: UsageItem) => a.avg_latency_ms - b.avg_latency_ms },
    { title: "成本(USD)", dataIndex: "total_cost_usd", key: "total_cost_usd", width: 110,
      render: (v: number) => <Text strong style={{ color: "#D97706" }}>${v.toFixed(4)}</Text>,
      sorter: (a: UsageItem, b: UsageItem) => a.total_cost_usd - b.total_cost_usd },
    { title: "成功率", dataIndex: "success_rate", key: "success_rate", width: 90,
      render: (v: number) => {
        const pct = (v * 100).toFixed(1);
        return <Tag color={v >= 0.9 ? "green" : "red"}>{pct}%</Tag>;
      } },
  ];

  const abColumns = ["指标", "模型 A", "模型 B"];
  const abRows = abResult?.a && abResult?.b ? [
    { 指标: "调用次数", "模型 A": abResult.a.calls, "模型 B": abResult.b.calls },
    { 指标: "平均延迟(ms)", "模型 A": abResult.a.avg_latency_ms, "模型 B": abResult.b.avg_latency_ms },
    { 指标: "累计成本(USD)", "模型 A": `$${abResult.a.total_cost_usd}`, "模型 B": `$${abResult.b.total_cost_usd}` },
    { 指标: "平均输出Token", "模型 A": abResult.a.avg_completion_tokens, "模型 B": abResult.b.avg_completion_tokens },
    { 指标: "成功率", "模型 A": `${(abResult.a.success_rate * 100).toFixed(1)}%`, "模型 B": `${(abResult.b.success_rate * 100).toFixed(1)}%` },
  ] : [];

  const t = realtime?.today;
  const y = realtime?.yesterday;
  const ch = realtime?.current_hour;
  const lh = realtime?.last_hour;
  const cmp = realtime?.comparison;

  return (
    <div>
      {showWarningBanner && (
        <Alert message="监控数据暂不可用" description={error} type="warning" showIcon closable
          style={{ marginBottom: 16 }} action={<a onClick={loadAll}>重试</a>} />
      )}

      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            <ApiOutlined style={{ marginRight: 8 }} /> AI 监控仪表盘
          </Title>
          <Text type="secondary">LLM 实时与每日消耗 · 成本与性能 · 模型 A/B 对比</Text>
        </div>
        <Space>
          <Tooltip title={`上次刷新：${lastRefresh.toLocaleTimeString("zh-CN")}（每 30 秒自动刷新）`}>
            <Badge status={realtimeLoading ? "processing" : "success"} text={realtimeLoading ? "刷新中..." : "实时"} />
          </Tooltip>
          <Button icon={<ReloadOutlined />} onClick={() => { loadAll(); loadRealtime(false); setLastRefresh(new Date()); }}>立即刷新</Button>
        </Space>
      </div>

      {/* 第一层：累计 KPI */}
      <Row gutter={[16, 16]} style={{ marginBottom: 12 }} data-tour="ai-mon-kpi">
        <Col xs={12} sm={6}>
          <Card hoverable size="small">
            <Statistic title="累计真实调用" value={stats.real_total_calls || stats.total_calls}
              prefix={<ApiOutlined />} valueStyle={{ color: "#4F46E5" }} />
            <Text type="secondary" style={{ fontSize: 12 }}>最近 7 天：{stats.recent_calls_7d} 次</Text>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable size="small">
            <Statistic title="累计真实 Token" value={stats.real_total_tokens || stats.total_tokens}
              prefix={<DatabaseOutlined />} valueStyle={{ color: "#0891B2" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable size="small">
            <Statistic title="累计成本(USD)" value={stats.real_total_cost_usd || 0}
              precision={4} prefix={<DollarOutlined />} valueStyle={{ color: "#D97706" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable size="small">
            <Statistic title="平均延迟" value={stats.real_avg_latency_ms || stats.avg_latency_ms}
              suffix="ms" prefix={<ClockCircleOutlined />} valueStyle={{ color: "#F59E0B" }} />
          </Card>
        </Col>
      </Row>

      {/* 第二层：今日实时 KPI（高亮"今日"） */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card hoverable size="small" style={{ borderTop: "2px solid #4F46E5" }}>
            <Space style={{ marginBottom: 2 }}>
              <Tag color="blue" style={{ margin: 0 }}>今日</Tag>
              {t ? deltaTag(cmp?.calls_delta_pct || 0) : null}
            </Space>
            <Statistic title="今日调用次数" value={t?.calls || 0} prefix={<ThunderboltOutlined />} valueStyle={{ color: "#4F46E5" }} />
            <Text type="secondary" style={{ fontSize: 12 }}>昨日：{y?.calls || 0} 次</Text>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable size="small" style={{ borderTop: "2px solid #0891B2" }}>
            <Space style={{ marginBottom: 2 }}>
              <Tag color="cyan" style={{ margin: 0 }}>今日</Tag>
              {t ? deltaTag(cmp?.tokens_delta_pct || 0) : null}
            </Space>
            <Statistic title="今日 Token 用量" value={t?.tokens || 0} prefix={<DatabaseOutlined />} valueStyle={{ color: "#0891B2" }} />
            <Text type="secondary" style={{ fontSize: 12 }}>昨日：{fmtInt(y?.tokens || 0)}</Text>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable size="small" style={{ borderTop: "2px solid #D97706" }}>
            <Space style={{ marginBottom: 2 }}>
              <Tag color="orange" style={{ margin: 0 }}>今日</Tag>
              {t ? deltaTag(cmp?.cost_delta_pct || 0) : null}
            </Space>
            <Statistic title="今日成本(USD)" value={t?.cost_usd || 0} precision={4}
              prefix={<FireOutlined />} valueStyle={{ color: "#D97706" }} />
            <Text type="secondary" style={{ fontSize: 12 }}>昨日：{fmtMoney(y?.cost_usd || 0)}</Text>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable size="small" style={{ borderTop: "2px solid #EF4444" }}>
            <Space style={{ marginBottom: 2 }}>
              <Tag color="red" style={{ margin: 0 }}>今日</Tag>
              {t ? deltaTag(cmp?.errors_delta_pct || 0) : null}
            </Space>
            <Statistic title="今日错误数" value={t?.errors || 0}
              prefix={<CloseCircleOutlined />} valueStyle={{ color: "#EF4444" }} />
            <Text type="secondary" style={{ fontSize: 12 }}>错误率 {fmtPct(t?.error_rate || 0)} · 昨日 {y?.errors || 0}</Text>
          </Card>
        </Col>
      </Row>

      {/* 24 小时实时柱图 + 实时小窗 */}
      <Card
        size="small" style={{ marginBottom: 16 }}
        title={<span><ClockCircleOutlined /> 24 小时实时消耗（今日 · 逐小时）</span>}
        extra={
          realtime ? (
            <Space size={16}>
              <Text type="secondary" style={{ fontSize: 12 }}>最后调用：<Text strong>{timeAgo(realtime.last_call_at)}</Text> · {realtime.last_call_provider}/{realtime.last_call_model}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>本周：{fmtMoney(realtime.this_week.cost_usd)} · 本月：{fmtMoney(realtime.this_month.cost_usd)}</Text>
            </Space>
          ) : null
        }
      >
        <Row gutter={16} style={{ marginBottom: 12 }}>
          <Col xs={12} md={6}>
            <Statistic title="当前小时成本" value={ch?.cost_usd || 0} precision={4} prefix={<DollarOutlined />} valueStyle={{ color: "#D97706", fontSize: 22 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>调用 {ch?.calls || 0} 次 · Token {fmtInt(ch?.tokens || 0)} · 错误 {ch?.errors || 0}</Text>
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="最近 1 小时" value={lh?.cost_usd || 0} precision={4} prefix={<DollarOutlined />} valueStyle={{ color: "#0891B2", fontSize: 22 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>调用 {lh?.calls || 0} 次 · Token {fmtInt(lh?.tokens || 0)} · 错误 {lh?.errors || 0}</Text>
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="本周累计" value={realtime?.this_week.cost_usd || 0} precision={4} prefix={<DollarOutlined />} valueStyle={{ color: "#4F46E5", fontSize: 22 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>调用 {realtime?.this_week.calls || 0} 次 · Token {fmtInt(realtime?.this_week.tokens || 0)}</Text>
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="本月累计" value={realtime?.this_month.cost_usd || 0} precision={4} prefix={<DollarOutlined />} valueStyle={{ color: "#8B5CF6", fontSize: 22 }} />
            <Text type="secondary" style={{ fontSize: 12 }}>调用 {realtime?.this_month.calls || 0} 次 · Token {fmtInt(realtime?.this_month.tokens || 0)}</Text>
          </Col>
        </Row>
        {hourly.length === 0 ? (
          <Empty description="暂无今日逐小时数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <svg viewBox={`0 0 ${HW} ${HH}`} width="100%" style={{ display: "block" }}>
            {/* 网格 */}
            {[0, 0.25, 0.5, 0.75, 1].map((p, i) => (
              <line key={i} x1={Hpad} y1={HH - Hpad - p * (HH - Hpad * 2)}
                x2={HW - Hpad} y2={HH - Hpad - p * (HH - Hpad * 2)}
                stroke="#F1F5F9" strokeDasharray="3 3" />
            ))}
            {/* 柱（成本） */}
            {hourly.map((h, i) => {
              const bh = (h.cost_usd / hourMaxCost) * (HH - Hpad * 2);
              const x = Hpad + i * barW + 2;
              const y = HH - Hpad - bh;
              const isNow = i === nowHour;
              return (
                <g key={i}>
                  <Tooltip title={`${i}:00-${i + 1}:00 · ${h.calls} 次 · ${fmtInt(h.tokens)} Token · ${fmtMoney(h.cost_usd)} · ${h.errors} 错误`}>
                    <rect x={x} y={y} width={Math.max(2, barW - 4)} height={bh}
                      fill={isNow ? "#EF4444" : "#D97706"} opacity={isNow ? 0.95 : 0.7}
                      rx={2} />
                  </Tooltip>
                </g>
              );
            })}
            {/* X 轴小时标签（每 3 小时） */}
            {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
              <text key={h} x={Hpad + h * barW + barW / 2 - 6} y={HH - 6}
                fontSize={10} fill="#64748B">{`${String(h).padStart(2, "0")}时`}</text>
            ))}
            {/* 当前小时指示 */}
            <line x1={Hpad + nowHour * barW + barW / 2} y1={4}
              x2={Hpad + nowHour * barW + barW / 2} y2={HH - Hpad}
              stroke="#EF4444" strokeDasharray="2 2" opacity={0.5} />
            <text x={HW - Hpad - 4} y={14} textAnchor="end" fontSize={10} fill="#EF4444">← 现在</text>
          </svg>
        )}
      </Card>

      {/* 趋势图 + Provider 分布 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={14}>
          <Card
            size="small"
            title="成本 / 调用趋势"
            extra={
              <Radio.Group size="small" value={trendWindow} onChange={(e) => setTrendWindow(e.target.value as TrendWindow)}>
                <Radio.Button value={1}>今日</Radio.Button>
                <Radio.Button value={7}>7 天</Radio.Button>
                <Radio.Button value={30}>30 天</Radio.Button>
                <Radio.Button value={90}>90 天</Radio.Button>
              </Radio.Group>
            }
          >
            {trend.length === 0 ? (
              <Empty description="暂无趋势数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
                <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="#E2E8F0" />
                <path d={costPath} fill="none" stroke="#D97706" strokeWidth={2} />
                <path d={callPath} fill="none" stroke="#4F46E5" strokeWidth={2} strokeDasharray="4 3" />
                <text x={pad} y={16} fontSize={11} fill="#D97706">● 成本(USD)</text>
                <text x={pad + 90} y={16} fontSize={11} fill="#4F46E5">● 调用次数</text>
              </svg>
            )}
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title="Provider 分布（累计）" size="small">
            {providerEntries.length === 0 ? (
              <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : providerEntries.map(([provider, count]) => {
              const pct = (count / totalProviderCalls) * 100;
              const color = ({ minimax: "#4F46E5", openai: "#10B981" } as any)[provider] || "#6366F1";
              return (
                <div key={provider} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <Text strong style={{ fontSize: 13 }}>{provider}</Text>
                    <Text style={{ fontSize: 13 }}>{count} ({pct.toFixed(1)}%)</Text>
                  </div>
                  <div style={{ height: 8, background: "#F1F5F9", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4 }} />
                  </div>
                </div>
              );
            })}
          </Card>
        </Col>
      </Row>

      {/* 每日明细表（来自 trend） */}
      <Card title="每日明细" size="small" style={{ marginBottom: 16 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>按天聚合 · 含历史 {trendWindow} 天</Text>}>
        <Table dataSource={trend} columns={[
          { title: "日期", dataIndex: "date", width: 140 },
          { title: "调用", dataIndex: "calls", width: 90, sorter: (a: TrendPoint, b: TrendPoint) => a.calls - b.calls },
          { title: "Token", dataIndex: "tokens", width: 120, render: (v: number) => fmtInt(v), sorter: (a: TrendPoint, b: TrendPoint) => a.tokens - b.tokens },
          { title: "成本(USD)", dataIndex: "cost_usd", width: 130, render: (v: number) => <Text strong style={{ color: "#D97706" }}>{fmtMoney(v)}</Text>, sorter: (a: TrendPoint, b: TrendPoint) => a.cost_usd - b.cost_usd },
          {
            title: "成本条", dataIndex: "cost_usd", width: 200,
            render: (v: number) => {
              const pct = (v / Math.max(0.0001, maxCost)) * 100;
              return (
                <div style={{ height: 8, background: "#F1F5F9", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: "#D97706", borderRadius: 4 }} />
                </div>
              );
            },
          },
        ]} rowKey="date" size="small" pagination={{ pageSize: 10, showSizeChanger: false, showTotal: (t) => `共 ${t} 天` }}
          locale={{ emptyText: <Empty description="暂无每日数据" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }} />
      </Card>

      {/* 累计：模型成本与性能 */}
      <Card title="模型成本与性能（累计 · 真实度量）" size="small" style={{ marginBottom: 16 }}>
        <Table dataSource={usage.items} columns={usageColumns} rowKey={(r) => `${r.provider}/${r.model}`}
          size="small" pagination={false}
          locale={{ emptyText: <Empty description="暂无真实调用记录，触发一次 AI 功能后将出现" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }} />
        {usage.summary && (usage.summary.total_calls > 0) && (
          <div style={{ marginTop: 8, color: "#64748B", fontSize: 12 }}>
            合计：{usage.summary.total_calls} 次调用 · {usage.summary.total_tokens.toLocaleString()} Token · ${usage.summary.total_cost_usd.toFixed(4)}
          </div>
        )}
      </Card>

      {/* 今日成本 TOP：Provider / Task / Project 三 Tab */}
      <Card
        title={<span><AppstoreOutlined /> 今日成本 TOP（Provider / 任务 / 项目 切片）</span>}
        size="small" style={{ marginBottom: 16 }}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>数据源：llm_call_logs · 当日 00:00 至今</Text>}
      >
        <Tabs size="small" activeKey={sliceTab} onChange={(k) => setSliceTab(k as any)}
          items={[
            { key: "provider", label: `Provider (${realtime?.cost_by_provider_today.length || 0})`, children: null },
            { key: "task", label: `任务/Agent (${realtime?.cost_by_task_today.length || 0})`, children: null },
            { key: "project", label: `项目 (${realtime?.cost_by_project_today.length || 0})`, children: null },
          ]} />
        <Table dataSource={sliceData} columns={sliceColumns}
          rowKey={(r: any) => sliceTab === "provider" ? `${r.provider}/${r.model}` : (r.task_name || r.project_id)}
          size="small" pagination={false}
          locale={{ emptyText: <Empty description={`今日暂无 ${sliceTab === "provider" ? "Provider" : sliceTab === "task" ? "任务" : "项目"} 维度成本数据`} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }} />
      </Card>

      {/* 模型 A/B 对比 */}
      <Card title={<span><RiseOutlined /> 模型 A/B 对比（累计）</span>} size="small" style={{ marginBottom: 16 }}>
        <Space style={{ marginBottom: 12 }}>
          <Text>模型 A:</Text>
          <Input value={modelA} onChange={(e) => setModelA(e.target.value)} style={{ width: 200 }} placeholder="provider/model" />
          <Text>模型 B:</Text>
          <Input value={modelB} onChange={(e) => setModelB(e.target.value)} style={{ width: 200 }} placeholder="provider/model" />
          <Button type="primary" loading={abLoading} onClick={runABTest}>对比</Button>
        </Space>
        {abResult?.error && <Alert type="error" message={abResult.error} showIcon />}
        {abRows.length > 0 && (
          <Table columns={abColumns.map(c => ({ title: c, dataIndex: c, key: c }))}
            dataSource={abRows} rowKey="指标" size="small" pagination={false} bordered />
        )}
        {abResult && !abResult.error && abRows.length === 0 && (
          <Empty description="所选模型暂无调用数据，请先触发对应模型的 AI 功能" />
        )}
      </Card>

      {/* Agent 排行 + 错误 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card title="Agent 调用排行（累计）" size="small">
            {agentRanking.length === 0 ? (
              <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : agentRanking.map(([agent, count], idx) => {
              const pct = (count / maxAgentCalls) * 100;
              const colors = ["#4F46E5", "#0891B2", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4"];
              return (
                <div key={agent} style={{ marginBottom: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                    <Text style={{ fontSize: 12 }}><Text type="secondary" style={{ fontSize: 11 }}>{idx + 1}.</Text> {agent}</Text>
                    <Text style={{ fontSize: 12, fontWeight: 600 }}>{count}</Text>
                  </div>
                  <div style={{ height: 6, background: "#F1F5F9", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: colors[idx % colors.length], borderRadius: 3 }} />
                  </div>
                </div>
              );
            })}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="最近错误" size="small">
            {stats.recent_errors.length === 0 ? (
              <div style={{ textAlign: "center", padding: 20 }}>
                <CheckCircleOutlined style={{ fontSize: 32, color: "#10B981" }} />
                <div style={{ marginTop: 8, color: "#64748B" }}>暂无错误记录</div>
              </div>
            ) : (
              <div style={{ maxHeight: 260, overflowY: "auto" }}>
                {stats.recent_errors.slice(0, 10).map((err, idx) => (
                  <Alert key={idx}
                    message={<div style={{ fontSize: 12 }}>
                      <Tag color="red" style={{ fontSize: 10 }}>{err.agent_type}</Tag>
                      {err.title?.replace(/\[.*?\]\s*/, "").slice(0, 40)}
                    </div>}
                    type="error" showIcon style={{ marginBottom: 4, padding: "4px 8px" }} />
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 调用记录表 */}
      <Card title="调用记录" size="small" data-tour="ai-mon-calls">
        <Table dataSource={calls} columns={[
          { title: "Agent类型", dataIndex: "agent_type", key: "agent_type", width: 120,
            render: (v: string) => <Tag color="blue">{v || "unknown"}</Tag> },
          { title: "标题", dataIndex: "title", key: "title", ellipsis: true, width: 250 },
          { title: "状态", dataIndex: "status", key: "status", width: 100,
            render: (v: string) => <Tag color={v === "success" ? "green" : "red"}>{v === "success" ? "成功" : "失败"}</Tag> },
          { title: "消息数", dataIndex: "message_count", key: "message_count", width: 80 },
          { title: "时间", dataIndex: "created_at", key: "created_at", width: 180,
            render: (v: string | null) => v ? new Date(v).toLocaleString("zh-CN") : "-" },
        ]} rowKey="id" loading={callsLoading} size="small"
          pagination={{ total: totalCalls, pageSize: 20, showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`, onChange: (page) => loadCalls(page) }}
          locale={{ emptyText: <Empty description="暂无调用记录" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }} />
      </Card>
    </div>
  );
};

export default AIMonitor;