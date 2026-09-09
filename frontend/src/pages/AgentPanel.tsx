import React, { useState, useEffect } from "react";
import { Card, Typography, Row, Col, Tag, Button, Space, App, Statistic, Progress, Tooltip, Badge, Divider, Alert, Modal, Select, Input, List, Empty, Spin } from "antd";
import { RobotOutlined, CheckCircleOutlined, SyncOutlined, ThunderboltOutlined, AimOutlined, BarChartOutlined, WarningOutlined, FileTextOutlined, SafetyOutlined, BookOutlined, FileDoneOutlined, PlayCircleOutlined, HeartOutlined, BulbOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { agentApi, projectApi } from "../api";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface AgentStatus {
  id: string;
  name: string;
  type: string;
  icon: string;
  status: "online" | "busy" | "offline";
  description: string;
  lastActive: string;
  tasksCompleted: number;
  coverage: number;
  accuracy: number;
  color: string;
  inputHint: string;
}

const ICON_MAP: Record<string, React.ComponentType<any>> = {
  BarChartOutlined, WarningOutlined, FileTextOutlined, RobotOutlined,
  ThunderboltOutlined, SafetyOutlined, AimOutlined, FileDoneOutlined,
  HeartOutlined, BulbOutlined,
};

const RUNNABLE_WITH_INPUT = ["meeting_minutes", "wbs"];

const AgentPanel: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);

  const [runModal, setRunModal] = useState(false);
  const [active, setActive] = useState<AgentStatus | null>(null);
  const [selProject, setSelProject] = useState<string | undefined>();
  const [inputText, setInputText] = useState("");
  const [create, setCreate] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await agentApi.list();
      setAgents(r?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载 Agent 状态失败");
    } finally {
      setLoading(false);
    }
  };

  const loadProjects = async () => {
    try {
      const r: any = await projectApi.list();
      const list = Array.isArray(r) ? r : (r?.items || []);
      setProjects(list);
    } catch { /* ignore */ }
  };

  useEffect(() => { load(); loadProjects(); }, []);

  const onlineCount = agents.filter(a => a.status === "online").length;
  const totalExecuted = agents.reduce((s, a) => s + a.tasksCompleted, 0);
  const Icon = (name: string) => ICON_MAP[name] || RobotOutlined;

  const openRun = (a: AgentStatus) => {
    setActive(a); setResult(null); setInputText(""); setCreate(true); setRunModal(true);
  };

  const onRun = async () => {
    if (!active) return;
    if (RUNNABLE_WITH_INPUT.includes(active.id) && !selProject) {
      message.warning("请先选择目标项目"); return;
    }
    const needsProject = active.id === "risk" || active.id === "evm" || active.id === "resource" || active.id === "compliance" || active.id === "quality" || active.id === "health_check" || active.id === "decision";
    if (needsProject && !selProject) {
      message.warning("请先选择目标项目"); return;
    }
    setRunning(true);
    try {
      const r: any = await agentApi.run({
        agent_type: active.id,
        project_id: selProject,
        input: inputText,
        options: active.id === "risk" ? { create } : active.id === "meeting_minutes" ? { create } : active.id === "weekly_report" ? { weeks: 1 } : {},
      });
      setResult(r?.result);
      message.success("Agent 执行完成");
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "执行失败");
    } finally {
      setRunning(false);
    }
  };

  const renderResult = (res: any) => {
    if (!res) return null;
    if (res.report) return <Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{res.report}</Paragraph>;
    if (Array.isArray(res.risks)) return (
      <List size="small" dataSource={res.risks} renderItem={(r: any) => (
        <List.Item>
          <div><Text strong>{r.name}</Text> <Tag color="red">P{r.probability}·I{r.impact}</Tag>
          <div style={{ fontSize: 12, color: "#64748B" }}>{r.description}</div>
          <div style={{ fontSize: 12, color: "#0EA5E9" }}>建议：{r.recommendation}</div></div>
        </List.Item>
      )} />
    );
    if (Array.isArray(res.created)) return (
      <List size="small" dataSource={res.created} renderItem={(c: any) => (
        <List.Item><CheckCircleOutlined style={{ color: "#10B981" }} /> <span style={{ marginLeft: 8 }}>{c.name}</span></List.Item>
      )} />
    );
    if (res.planner) return (
      <>
        <Divider>Planner 计划</Divider>
        <List size="small" dataSource={res.planner} renderItem={(p: any) => <List.Item>{p.step} — <Text type="secondary">{typeof p.owner === 'string' ? p.owner : p.owner?.full_name || p.owner?.name || p.owner?.username || '--'}</Text></List.Item>} />
        <Divider>Reviewer 审查</Divider>
        <Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{res.reviewer}</Paragraph>
      </>
    );
    return <pre style={{ fontSize: 12, maxHeight: 320, overflow: "auto" }}>{JSON.stringify(res, null, 2)}</pre>;
  };

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Agent</Title>
          <Text type="secondary">{onlineCount} 个专业 AI Agent 在线 · 共 {agents.length} 个 · 真实调用次数 {totalExecuted}</Text>
        </div>
        <Space wrap>
          <Badge count={onlineCount} style={{ background: "#10B981" }}>
            <Button icon={<SyncOutlined spin={loading} />} onClick={load}>刷新状态</Button>
          </Badge>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>Agent 总数</span>} value={agents.length} prefix={<RobotOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>在线</span>} value={onlineCount} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>真实执行次数</span>} value={totalExecuted} prefix={<ThunderboltOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card style={{ borderRadius: 16, background: "linear-gradient(135deg, #3B82F6 0%, #6366F1 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>平均准确率</span>} value={`${agents.length ? Math.round(agents.reduce((s, a) => s + a.accuracy, 0) / agents.length) : 0}%`} prefix={<AimOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
      </Row>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {agents.map((agent, idx) => {
          const AgentIcon = Icon(agent.icon);
          return (
            <motion.div key={agent.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.05 }}>
              <Card className="card-hover" style={{ borderRadius: 16, border: `1px solid ${agent.color}20` }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 44, height: 44, borderRadius: 12, background: `${agent.color}15`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, color: agent.color }}>
                      <AgentIcon />
                    </div>
                    <div>
                      <Text strong style={{ fontSize: 14 }}>{agent.name}</Text>
                      <div style={{ marginTop: 2 }}>
                        <Badge status={agent.status === "online" ? "success" : agent.status === "busy" ? "processing" : "default"} text={agent.status === "online" ? "在线" : agent.status === "busy" ? "忙碌" : "离线"} style={{ fontSize: 11 }} />
                      </div>
                    </div>
                  </div>
                  <Tooltip title={`准确率 ${agent.accuracy}%`}>
                    <Progress type="circle" percent={agent.accuracy} size={40} strokeColor={agent.color} format={() => ""} />
                  </Tooltip>
                </div>
                <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8, minHeight: 32 }}>{agent.description}</Text>
                <Divider style={{ margin: "8px 0" }} />
                <Row gutter={8} style={{ marginBottom: 8 }}>
                  <Col span={12}><Text type="secondary" style={{ fontSize: 11 }}>真实执行: <b>{agent.tasksCompleted}</b></Text></Col>
                  <Col span={12}><Text type="secondary" style={{ fontSize: 11 }}>覆盖记录: <b>{agent.coverage}</b></Text></Col>
                </Row>
                <Space style={{ width: "100%", justifyContent: "space-between" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{agent.lastActive}</Text>
                  <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => openRun(agent)}>运行</Button>
                </Space>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <Card title="Agent 协作架构" style={{ borderRadius: 16, marginTop: 24 }} className="card-hover">
        <Alert type="info" showIcon message="系统现有专业 Agent 与 PMBOK / CPMAI 知识单元 Agent 已统一纳入 Agent 中心，可直接运行并沉淀业务结果。" style={{ marginBottom: 16 }} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
          {agents.map(a => (<Tag key={a.id} color={a.color} style={{ borderRadius: 6, padding: "4px 10px" }}>{a.name}</Tag>))}
        </div>
      </Card>

      <Modal title={`运行 ${active?.name || ""}`} open={runModal} onOk={onRun} onCancel={() => setRunModal(false)} okText="执行" cancelText="取消" confirmLoading={running} width={680}>
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          {active?.inputHint && <Alert type="info" showIcon message={`参数说明：${active.inputHint}`} />}
          {active?.id !== "report" && (
            <div>
              <Text>目标项目</Text>
              <Select style={{ width: "100%", marginTop: 6 }} placeholder="选择项目（report 可不选）" allowClear value={selProject} onChange={setSelProject}
                options={projects.map((p: any) => ({ value: p.id, label: p.name }))} />
            </div>
          )}
          {RUNNABLE_WITH_INPUT.includes(active?.id || "") && (
            <div>
              <Text>{active?.id === "wbs" ? "项目目标 / 范围描述" : "会议纪要 / 需求文本"}</Text>
              <TextArea rows={6} style={{ marginTop: 6 }} value={inputText} onChange={(e) => setInputText(e.target.value)} placeholder={active?.id === "wbs" ? "例如：搭建电商平台，含商品、订单、支付模块" : "粘贴会议纪要，自动提取行动项并建任务"} />
            </div>
          )}
          {(active?.id === "risk" || active?.id === "meeting_minutes") && (
            <div><label><input type="checkbox" checked={create} onChange={(e) => setCreate(e.target.checked)} /> 将结果落库（创建风险/任务）</label></div>
          )}
          {result && (
            <Card size="small" title="执行结果" style={{ background: "#F8FAFC" }}>
              <Spin spinning={running}>
                {renderResult(result)}
              </Spin>
            </Card>
          )}
        </Space>
      </Modal>
    </div>
  );
};

export default AgentPanel;
