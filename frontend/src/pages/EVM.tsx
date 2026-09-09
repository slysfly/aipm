import React, { useState, useEffect } from "react";
import { Card, Typography, Row, Col, Statistic, Table, Tag, Button, Progress, Space, Tabs, Empty, Divider, List, Select, App } from "antd";
import { BarChartOutlined, LineChartOutlined, PieChartOutlined, DownloadOutlined, AlertOutlined, CheckCircleOutlined, ClockCircleOutlined, RiseOutlined, FallOutlined, FilePdfOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { analysisApi, projectApi } from "../api";
import { http } from "../api/http";

const { Title, Text } = Typography;

// PMI中国AI项目管理社区 标准 EVM 9 大指标
interface EVMMetrics {
  pv: number; ev: number; ac: number;
  bac: number; sv: number; cv: number;
  spi: number; cpi: number;
  eac: number; etc: number; vac: number;
  tcpi: number;
}

const emptyMetrics: EVMMetrics = {
  pv: 0, ev: 0, ac: 0, bac: 0, sv: 0, cv: 0,
  spi: 1, cpi: 1, eac: 0, etc: 0, vac: 0, tcpi: 1,
};

const EVM: React.FC = () => {
  const { message } = App.useApp();
  const [metrics, setMetrics] = useState<EVMMetrics>(emptyMetrics);
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  const load = async (pid: string) => {
    if (!pid) return;
    setLoading(true);
    try {
      const r: any = await analysisApi.evm(pid);
      const c = r?.current || {};
      setMetrics({
        pv: c.pv || 0, ev: c.ev || 0, ac: c.ac || 0, bac: c.bac || 0,
        sv: c.sv || 0, cv: c.cv || 0,
        spi: c.spi || 1, cpi: c.cpi || 1,
        eac: c.eac || 0, etc: c.etc || 0, vac: c.vac || 0, tcpi: c.tcpi || 1,
      });
      // 历史快照（如果有）
      const h = r?.history || r?.snapshots || [];
      setHistory(Array.isArray(h) ? h : []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载 EVM 失败");
    } finally {
      setLoading(false);
    }
  };

  const exportPdf = async () => {
    if (!projectId) {
      message.warning("请先选择项目");
      return;
    }
    setExporting(true);
    try {
      const resp = await http.get(`/reports/evm/pdf`, {
        params: { project_id: projectId },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([resp], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `evm_report_${projectId}_${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      message.success("EVM 偏差分析报告 PDF 导出成功");
    } catch (e: any) {
      message.error("PDF 导出失败：" + (e?.message || "未知错误"));
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    projectApi.list().then((r: any) => {
      const ps: any[] = r?.items || r || [];
      setProjects(ps);
      if (ps[0]) setProjectId(ps[0].id);
    }).catch(() => {});
  }, []);
  useEffect(() => { if (projectId) load(projectId); }, [projectId]);

  const m = metrics;
  const formatCurrency = (v: number) => `¥${Math.abs(v).toLocaleString()}`;
  const donePct = m.bac > 0 ? Math.round((m.ev / m.bac) * 100) : 0;

  const indicators = [
    { label: "PV (计划价值)", value: formatCurrency(m.pv), color: "#3B82F6", status: "normal" },
    { label: "EV (挣得价值)", value: formatCurrency(m.ev), color: "#10B981", status: "normal" },
    { label: "AC (实际成本)", value: formatCurrency(m.ac), color: "#EF4444", status: "normal" },
    { label: "BAC (完工预算)", value: formatCurrency(m.bac), color: "#8B5CF6", status: "normal" },
    { label: "SV (进度偏差)", value: formatCurrency(m.sv), color: m.sv >= 0 ? "#10B981" : "#EF4444", status: m.sv >= 0 ? "good" : "bad", prefix: m.sv >= 0 ? "+" : "" },
    { label: "CV (成本偏差)", value: formatCurrency(m.cv), color: m.cv >= 0 ? "#10B981" : "#EF4444", status: m.cv >= 0 ? "good" : "bad", prefix: m.cv >= 0 ? "+" : "" },
    { label: "SPI (进度绩效)", value: m.spi.toFixed(2), color: m.spi >= 1 ? "#10B981" : "#F59E0B", status: m.spi >= 1 ? "good" : "warning" },
    { label: "CPI (成本绩效)", value: m.cpi.toFixed(2), color: m.cpi >= 1 ? "#10B981" : "#F59E0B", status: m.cpi >= 1 ? "good" : "warning" },
    { label: "EAC (完工估算)", value: formatCurrency(m.eac), color: "#6366F1", status: "normal" },
    { label: "ETC (完工尚需)", value: formatCurrency(m.etc), color: "#06B6D4", status: "normal" },
    { label: "VAC (完工偏差)", value: formatCurrency(m.vac), color: m.vac >= 0 ? "#10B981" : "#EF4444", status: m.vac >= 0 ? "good" : "bad", prefix: "" },
    { label: "TCPI (完工绩效)", value: m.tcpi.toFixed(2), color: m.tcpi <= 1 ? "#10B981" : "#EF4444", status: m.tcpi <= 1 ? "good" : "warning" },
  ];

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>EVM 挣值分析 Pro</Title>
          <Text type="secondary">PMI中国AI项目管理社区 标准 · 9大核心指标 · 实时成本与进度绩效监控</Text>
        </div>
        <Space wrap>
        <Select
          allowClear placeholder="选择项目"
          data-tour="evm-sel"
            style={{ width: 200 }}
            value={projectId || undefined}
            onChange={(v) => setProjectId(v || "")}
            options={projects.map((p: any) => ({ label: p.name, value: p.id }))}
          />
          <Button icon={<DownloadOutlined />} onClick={() => message.info("可在报表页导出")}>导出报告</Button>
          <Button type="primary" icon={<FilePdfOutlined />} loading={exporting} onClick={exportPdf}>导出 EVM PDF</Button>
        </Space>
      </div>

      {loading && <Empty description="加载中..." style={{ marginTop: 40 }} />}

      {/* 核心KPI */}
      <Row gutter={[12, 12]} style={{ marginBottom: 24 }}>
        {[{ label: "CPI", value: m.cpi.toFixed(2), color: m.cpi >= 1 ? "#10B981" : "#F59E0B", icon: <RiseOutlined /> },
          { label: "SPI", value: m.spi.toFixed(2), color: m.spi >= 1 ? "#10B981" : "#F59E0B", icon: <BarChartOutlined /> },
          { label: "EAC", value: formatCurrency(m.eac), color: "#6366F1", icon: <ClockCircleOutlined /> },
          { label: "VAC", value: formatCurrency(m.vac), color: m.vac >= 0 ? "#10B981" : "#EF4444", icon: m.vac >= 0 ? <RiseOutlined /> : <FallOutlined /> },
        ].map((item, i) => (
          <Col xs={12} sm={6} key={i}>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}>
              <Card className="card-hover" style={{ borderRadius: 16, textAlign: "center", background: `${item.color}08`, border: `1px solid ${item.color}20` }}>
                <Statistic title={<span style={{ color: item.color }}>{item.label}</span>} value={item.value} prefix={item.icon} valueStyle={{ color: item.color, fontSize: 22, fontWeight: 700 }} />
              </Card>
            </motion.div>
          </Col>
        ))}
      </Row>

      {/* EVM 仪表盘 + 12指标 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="EVM 绩效仪表盘" style={{ borderRadius: 16 }} className="card-hover" data-tour="evm-dash">
            <div style={{ textAlign: "center", padding: "12px 0" }}>
              <Progress type="dashboard" percent={donePct} strokeColor={{ from: "#4F46E5", to: "#06B6D4" }} size={160} format={p => <span style={{ fontSize: 18, fontWeight: 700 }}>{p}%</span>} />
              <div style={{ marginTop: 8 }}><Text>完工百分比</Text></div>
            </div>
            <Divider />
            <div style={{ display: "flex", justifyContent: "space-around" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: m.cpi >= 1 ? "#10B981" : "#F59E0B" }}>{m.cpi.toFixed(2)}</div>
                <Text type="secondary" style={{ fontSize: 11 }}>CPI</Text>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: m.spi >= 1 ? "#10B981" : "#F59E0B" }}>{m.spi.toFixed(2)}</div>
                <Text type="secondary" style={{ fontSize: 11 }}>SPI</Text>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#6366F1" }}>{formatCurrency(m.eac)}</div>
                <Text type="secondary" style={{ fontSize: 11 }}>EAC</Text>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="PMI中国AI项目管理社区 标准 12 项 EVM 指标" style={{ borderRadius: 16 }} className="card-hover">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
              {indicators.map((item, i) => (
                <motion.div key={i} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.03 }}>
                  <div style={{ padding: "10px 12px", borderRadius: 10, background: `${item.color}08`, border: `1px solid ${item.color}15` }}>
                    <Text type="secondary" style={{ fontSize: 10, display: "block" }}>{item.label}</Text>
                    <Text style={{ color: item.color, fontSize: 16, fontWeight: 700 }}>{item.value}</Text>
                    {(item as any).prefix && <Text style={{ color: item.color, fontSize: 12, marginLeft: 2 }}>{(item as any).prefix}</Text>}
                  </div>
                </motion.div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      {/* EVM 趋势图（基于历史快照） */}
      {history.length > 0 && (
        <Card title="EVM 历史趋势" style={{ borderRadius: 16, marginTop: 16 }} className="card-hover">
          <div style={{ padding: "8px 0" }}>
            <Text type="secondary" style={{ fontSize: 12 }}>CPI / SPI 趋势（基于历史快照）</Text>
            <div style={{ display: "flex", gap: 16, marginTop: 8, alignItems: "flex-end", height: 120, padding: "0 8px", borderBottom: "1px solid #eee" }}>
              {history.slice(-30).map((h: any, i: number) => {
                const spi = parseFloat(h.spi || 1);
                const cpi = parseFloat(h.cpi || 1);
                const max = 1.5;
                const min = 0.5;
                const norm = (v: number) => Math.max(0, Math.min(1, (v - min) / (max - min)));
                return (
                  <div key={i} style={{ flex: 1, minWidth: 6, display: "flex", flexDirection: "column", alignItems: "center", height: "100%", justifyContent: "flex-end" }}>
                    <div style={{ width: "100%", height: `${norm(spi) * 100}%`, background: "#4F46E5", opacity: 0.7, borderRadius: "2px 2px 0 0" }} title={`SPI=${spi.toFixed(2)}`} />
                    <div style={{ width: "100%", height: `${norm(cpi) * 100}%`, background: "#10B981", opacity: 0.7, borderRadius: "2px 2px 0 0" }} title={`CPI=${cpi.toFixed(2)}`} />
                  </div>
                );
              })}
            </div>
            <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
              <Tag color="#4F46E5">SPI 趋势</Tag>
              <Tag color="#10B981">CPI 趋势</Tag>
              <Text type="secondary" style={{ fontSize: 11 }}>共 {history.length} 个快照</Text>
            </div>
          </div>
        </Card>
      )}

      {/* EVM 趋势解释 */}
      <Card title="EVM 分析解读" style={{ borderRadius: 16, marginTop: 16 }} className="card-hover">        <Row gutter={16}>
          <Col xs={24} md={8}>
            <div style={{ padding: 12, borderRadius: 10, background: m.spi < 1 ? "#FEF2F2" : "#F0FDF4" }}>
              <Text strong style={{ color: m.spi < 1 ? "#EF4444" : "#10B981" }}>
                SPI = {m.spi.toFixed(2)} {m.spi < 1 ? "⚠ 进度滞后" : "✅ 进度正常"}
              </Text>
              <Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
                {m.spi < 1 && m.pv > 0 ? `实际进度仅为计划的 ${(m.spi * 100).toFixed(0)}%，落后计划 ${m.pv > 0 ? Math.round((m.sv / m.pv) * -100) : 0}%` : "进度符合或超前于计划"}
              </Text>
            </div>
          </Col>
          <Col xs={24} md={8}>
            <div style={{ padding: 12, borderRadius: 10, background: m.cpi < 1 ? "#FEF2F2" : "#F0FDF4" }}>
              <Text strong style={{ color: m.cpi < 1 ? "#EF4444" : "#10B981" }}>
                CPI = {m.cpi.toFixed(2)} {m.cpi < 1 ? "⚠ 成本超支" : "✅ 成本可控"}
              </Text>
              <Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
                {m.cpi < 1 && m.cpi > 0 ? `每完成 ¥1 价值的工作实际花费 ¥${(1 / m.cpi).toFixed(2)}，超支 ${((1 / m.cpi - 1) * 100).toFixed(0)}%` : "成本效率良好"}
              </Text>
            </div>
          </Col>
          <Col xs={24} md={8}>
            <div style={{ padding: 12, borderRadius: 10, background: m.tcpi > 1 ? "#FEF2F2" : "#F0FDF4" }}>
              <Text strong style={{ color: m.tcpi > 1 ? "#EF4444" : "#10B981" }}>
                TCPI = {m.tcpi.toFixed(2)} {m.tcpi > 1 ? "⚠ 需提升效率" : "✅ 目标可行"}
              </Text>
              <Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
                {m.tcpi > 1 ? `剩余工作需要以 ${(m.tcpi * 100).toFixed(0)}% 的效率完成才能达成 BAC 目标` : "剩余工作可以在当前效率下完成"}
              </Text>
            </div>
          </Col>
        </Row>
      </Card>
    </div>
  );
};

export default EVM;
