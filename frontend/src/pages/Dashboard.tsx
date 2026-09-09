import React, { useEffect, useState } from "react";
import { Row, Col, Card, Typography, List, Tag, Empty, App, Spin, Progress, Button, Statistic, Select, Tooltip, Skeleton, Divider, Space, Alert } from "antd";
import {
  ProjectOutlined,
  ProfileOutlined,
  AlertOutlined,
  RiseOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  RightCircleOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  BarChartOutlined,
  FundProjectionScreenOutlined,
  FlagOutlined,
  SwapOutlined,
  HistoryOutlined,
  LayoutOutlined,
  BulbOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { projectApi, taskApi, dashboardApi } from "../api";
import { motion } from "framer-motion";

const { Title, Text } = Typography;

// 渐变统计卡片组件
const StatCard: React.FC<{
  title: string;
  value: number;
  prefix: React.ReactNode;
  gradient: string;
  icon: React.ReactNode;
  delay?: number;
}> = ({ title, value, prefix, gradient, icon, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay: delay * 0.1, duration: 0.5, ease: "easeOut" }}
  >
    <Card
      className="stat-card"
      style={{
        background: gradient,
        borderRadius: 16,
        border: "none",
        height: "100%",
      }}
      styles={{ body: { padding: 20 } }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Statistic title={title} value={value} prefix={prefix} />
        <div style={{
          width: 44, height: 44, borderRadius: 12,
          background: "rgba(255,255,255,0.15)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 22, color: "#fff",
        }}>
          {icon}
        </div>
      </div>
    </Card>
  </motion.div>
);

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalProjects: 0, activeProjects: 0, totalTasks: 0, doneTasks: 0,
    overdue: 0, avgProgress: 0,
  });
  const [projects, setProjects] = useState<any[]>([]);

  // AI 下一步建议
  const [advice, setAdvice] = useState<any>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState<string | null>(null);
  const [adviceProjectId, setAdviceProjectId] = useState<string | undefined>(undefined);

  const loadAdvice = async (pid?: string) => {
    const target = pid ?? adviceProjectId;
    setAdviceLoading(true);
    setAdviceError(null);
    try {
      const data = await dashboardApi.nextSteps(target ? { project_id: target } : {});
      setAdvice(data);
    } catch (e: any) {
      setAdviceError(e?.response?.data?.detail || "生成下一步建议失败");
    } finally {
      setAdviceLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const [projRes, taskRes] = await Promise.all([
          projectApi.list({ page_size: 100 }),
          taskApi.list({ page_size: 100 }),
        ]);
        const projItems = projRes?.items || [];
        const taskItems = taskRes?.items || [];
        const doneTasks = taskItems.filter((t: any) => t.status === "done").length;
        const avgProgress = taskItems.length > 0
          ? Math.round((doneTasks / taskItems.length) * 100)
          : 0;
        setProjects(projItems.slice(0, 6));
        setStats({
          totalProjects: projItems.length,
          activeProjects: projItems.filter((p: any) => p.status === "active").length,
          totalTasks: taskRes?.total ?? taskItems.length,
          doneTasks,
          overdue: taskItems.filter((t: any) => t.due_date && new Date(t.due_date) < new Date() && t.status !== "done").length,
          avgProgress,
        });
        // 主数据就绪后，自动生成 AI 下一步建议（组合视角）
        loadAdvice();
      } catch (e: any) {
        message.error(e?.response?.data?.detail || "加载仪表盘失败");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "60vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="page-container" style={{ padding: "0 0 24px" }}>
      {/* 欢迎横幅 */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="gradient-bg"
        style={{
          borderRadius: 20, padding: "28px 36px", marginBottom: 24,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          position: "relative", overflow: "hidden",
        }}
      >
        <div style={{ position: "absolute", top: -40, right: -20, width: 200, height: 200, borderRadius: "50%", background: "rgba(255,255,255,0.05)", pointerEvents: "none" }} />
        <div style={{ position: "absolute", bottom: -60, left: "30%", width: 160, height: 160, borderRadius: "50%", background: "rgba(255,255,255,0.04)", pointerEvents: "none" }} />
        <div>
          <Title level={4} style={{ color: "#fff", margin: 0, fontWeight: 700 }}>🚀 欢迎使用 PMI中国 项目管理</Title>
          <Text style={{ color: "rgba(255,255,255,0.75)", marginTop: 4, display: "block", fontSize: 14 }}>
            {new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })} · 今日有 {stats.overdue} 个逾期任务需要关注
          </Text>
        </div>
        <Button
          type="default"
          ghost
          icon={<PlusOutlined />}
          onClick={() => navigate("/projects")}
          style={{ borderRadius: 10, borderColor: "rgba(255,255,255,0.3)", color: "#fff" }}
        >
          新建项目
        </Button>
      </motion.div>

      {/* KPI 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }} data-tour="dash-kpi">
        <Col xs={12} sm={12} md={6}>
          <StatCard
            title="项目总数" value={stats.totalProjects}
            prefix={<ProjectOutlined />}
            gradient="linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)"
            icon={<ProjectOutlined />}
            delay={1}
          />
        </Col>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            title="进行中项目" value={stats.activeProjects}
            prefix={<RiseOutlined />}
            gradient="linear-gradient(135deg, #3B82F6 0%, #06B6D4 100%)"
            icon={<BarChartOutlined />}
            delay={2}
          />
        </Col>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            title="任务总数" value={stats.totalTasks}
            prefix={<ProfileOutlined />}
            gradient="linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)"
            icon={<TeamOutlined />}
            delay={3}
          />
        </Col>
        <Col xs={12} sm={12} md={6}>
          <StatCard
            title="已完成任务" value={stats.doneTasks}
            prefix={<CheckCircleOutlined />}
            gradient="linear-gradient(135deg, #10B981 0%, #06B6D4 100%)"
            icon={<ThunderboltOutlined />}
            delay={4}
          />
        </Col>
      </Row>

      {/* AI 下一步建议（PMP / ACP / CPMAI 多维预判） */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.5 }}
        style={{ marginBottom: 24 }}
      >
        <Card
          title={
            <Space size={8}>
              <RobotOutlined style={{ color: "#7C3AED" }} />
              <span style={{ fontWeight: 600 }}>AI 下一步建议</span>
              <Tag color="purple" style={{ borderRadius: 6, marginInlineStart: 4 }}>
                PMP · ACP · CPMAI
              </Tag>
            </Space>
          }
          extra={
            <Space size={8}>
              <Select
                size="small"
                style={{ width: 180 }}
                placeholder="全部进行中项目"
                value={adviceProjectId ?? ""}
                onChange={(v: string) => { setAdviceProjectId(v || undefined); loadAdvice(v || undefined); }}
                options={[
                  { value: "", label: "全部进行中项目" },
                  ...projects.map((p: any) => ({ value: p.id, label: p.name })),
                ]}
                allowClear
              />
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={adviceLoading}
                onClick={() => loadAdvice()}
              >
                重新生成
              </Button>
            </Space>
          }
          className="card-hover"
          style={{ borderRadius: 16 }}
        >
          {adviceLoading && <Skeleton active paragraph={{ rows: 7 }} />}
          {!adviceLoading && adviceError && (
            <Alert type="error" showIcon message={adviceError} />
          )}
          {!adviceLoading && !adviceError && advice && (
            <>
              <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap", marginBottom: 16 }}>
                <div style={{ flex: "1 1 320px", minWidth: 260 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>总体研判</Text>
                  <Typography.Paragraph style={{ margin: "4px 0 8px", fontSize: 14 }}>
                    {advice.overall_assessment || "（暂无研判）"}
                  </Typography.Paragraph>
                  <Space wrap size={[6, 6]}>
                    {(advice.frameworks_used || []).map((f: string) => (
                      <Tag key={f} color={f === "PMP" ? "blue" : f === "ACP" ? "green" : "purple"}>
                        {f}
                      </Tag>
                    ))}
                    {advice.mode === "rule_based" && <Tag color="default">规则引擎</Tag>}
                    {advice.mode === "free_text" && <Tag color="default">文本解析</Tag>}
                  </Space>
                </div>
                <div style={{ width: 130, textAlign: "center", flexShrink: 0 }}>
                  <Progress
                    type="dashboard"
                    percent={Math.round((advice.health_score * 10) / (advice.dimensions?.length || 11))}
                    size={108}
                    strokeColor={{ from: "#7C3AED", to: "#4F46E5" }}
                  />
                  <div style={{ fontSize: 12, color: "rgba(0,0,0,0.45)", marginTop: -8 }}>综合健康度</div>
                </div>
              </div>

              {/* 维度评分标签 */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
                {(advice.dimensions || []).map((d: any, i: number) => {
                  const stColor = d.status === "健康" ? "green" : d.status === "需关注" ? "orange" : "red";
                  return (
                    <Tooltip key={i} title={`${d.framework} · ${d.score}/10`}>
                      <Tag color={stColor} style={{ borderRadius: 6, margin: 0 }}>
                        {d.name} {d.score}
                      </Tag>
                    </Tooltip>
                  );
                })}
              </div>

              <Divider style={{ margin: "8px 0 12px" }}>执行建议</Divider>

              {!advice.recommendations || advice.recommendations.length === 0 ? (
                <Empty description="暂无可执行的下一步建议" />
              ) : (
                <List
                  dataSource={advice.recommendations}
                  renderItem={(r: any, i: number) => {
                    const fwColor = r.framework === "PMP" ? "blue" : r.framework === "ACP" ? "green" : "purple";
                    const prColor = r.priority === "高" ? "red" : r.priority === "中" ? "orange" : "green";
                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.05 * i, duration: 0.3 }}
                      >
                        <List.Item
                          style={{
                            padding: "14px 0", borderBottom:
                              i === (advice.recommendations.length - 1) ? "none" : "1px solid #F0F0F0",
                          }}
                        >
                          <div style={{ width: "100%" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                              <Tag color={fwColor} style={{ borderRadius: 6, margin: 0 }}>{r.framework}</Tag>
                              <Tag color={prColor} style={{ borderRadius: 6, margin: 0 }}>{r.priority}</Tag>
                              <Tag color="default" style={{ borderRadius: 6, margin: 0 }}>{r.dimension}</Tag>
                              <Text strong style={{ fontSize: 14 }}>{r.title}</Text>
                            </div>
                            {r.rationale && (
                              <div style={{ fontSize: 13, color: "rgba(0,0,0,0.65)", marginBottom: 6, lineHeight: 1.7 }}>
                                {r.rationale}
                              </div>
                            )}
                            {r.actions && r.actions.length > 0 && (
                              <ol style={{ margin: "0 0 6px 18px", padding: 0, fontSize: 13, color: "rgba(0,0,0,0.75)", lineHeight: 1.8 }}>
                                {r.actions.map((a: string, idx: number) => (
                                  <li key={idx}>{a}</li>
                                ))}
                              </ol>
                            )}
                            {r.expected_outcome && (
                              <div style={{ fontSize: 12, color: "#7C3AED" }}>
                                <BulbOutlined style={{ marginRight: 4 }} />预期成效：{r.expected_outcome}
                              </div>
                            )}
                          </div>
                        </List.Item>
                      </motion.div>
                    );
                  }}
                />
              )}
            </>
          )}
        </Card>
      </motion.div>

      {/* 项目进度概览 + 最近项目 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
          >
            <Card
              title={<span style={{ fontWeight: 600 }}>项目进度概览</span>}
              className="card-hover"
              style={{ borderRadius: 16, height: "100%" }}
            >
              {projects.length === 0 ? (
                <div className="enhanced-empty">
                  <div style={{ fontSize: 48, marginBottom: 16 }}>📋</div>
                  <h3>暂无项目</h3>
                  <p>创建一个项目，开始你的项目管理之旅</p>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/projects")}>
                    创建项目
                  </Button>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {projects.slice(0, 5).map((p: any, idx: number) => (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.1 * idx, duration: 0.3 }}
                    >
                      <div
                        onClick={() => navigate(`/projects/${p.id}`)}
                        style={{
                          cursor: "pointer", padding: "12px 16px",
                          borderRadius: 12, background: "#F8FAFC",
                          border: "1px solid #E2E8F0",
                          transition: "all 0.2s",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#4F46E5"; e.currentTarget.style.boxShadow = "0 2px 8px rgba(79,70,229,0.1)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#E2E8F0"; e.currentTarget.style.boxShadow = "none"; }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                          <Text strong style={{ fontSize: 14 }}>{p.name}</Text>
                          <Tag color={p.status === "active" ? "green" : "default"} style={{ borderRadius: 6, margin: 0 }}>
                            {p.status === "active" ? "进行中" : p.status}
                          </Tag>
                        </div>
                        <Progress
                          percent={p.progress || 0}
                          size="small"
                          strokeColor={{ from: "#4F46E5", to: "#7C3AED" }}
                          showInfo={false}
                          style={{ margin: 0 }}
                        />
                        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>{p.industry || "通用"}</Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>{p.progress || "--"}%</Text>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </Card>
          </motion.div>
        </Col>

        <Col xs={24} lg={14}>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.5 }}
          >
            <Card
              title={<span style={{ fontWeight: 600 }}>最近项目</span>}
              extra={
                <Button type="link" icon={<RightCircleOutlined />} onClick={() => navigate("/projects")}>
                  查看全部
                </Button>
              }
              className="card-hover"
              style={{ borderRadius: 16 }}
            >
              {projects.length === 0 ? (
                <Empty description="暂无项目" />
              ) : (
                <List
                  dataSource={projects}
                  renderItem={(p: any, idx: number) => (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.05 * idx, duration: 0.3 }}
                    >
                      <List.Item
                        actions={[
                          <Button type="link" key="open" onClick={() => navigate(`/projects/${p.id}`)}>
                            打开
                          </Button>,
                        ]}
                        style={{ padding: "12px 0", cursor: "pointer" }}
                      >
                        <List.Item.Meta
                          avatar={
                            <div style={{
                              width: 40, height: 40, borderRadius: 10,
                              background: p.color || "linear-gradient(135deg, #4F46E5, #7C3AED)",
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 18, color: "#fff",
                            }}>
                              {p.name?.charAt(0) || "P"}
                            </div>
                          }
                          title={
                            <Text strong style={{ fontSize: 14 }}>{p.name}</Text>
                          }
                          description={
                            <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                              {p.description || "暂无描述"}
                            </Text>
                          }
                        />
                      </List.Item>
                    </motion.div>
                  )}
                />
              )}
            </Card>
          </motion.div>
        </Col>
      </Row>

      {/* 快捷操作 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.5 }}
        style={{ marginTop: 24 }}
      >
        <Card
          title={<span style={{ fontWeight: 600 }}>🚀 快捷操作</span>}
          style={{ borderRadius: 16 }}
          className="card-hover"
        >
          <Row gutter={[12, 12]}>
            {[
              { icon: <PlusOutlined />, label: "新建项目", color: "#4F46E5", onClick: () => navigate("/projects") },
              { icon: <ProfileOutlined />, label: "创建任务", color: "#3B82F6", onClick: () => navigate("/tasks") },
              { icon: <RobotOutlined />, label: "AI 智能体", color: "#8B5CF6", onClick: () => navigate("/ai/wbs") },
              { icon: <FundProjectionScreenOutlined />, label: "项目组合", color: "#7C3AED", onClick: () => navigate("/portfolio") },
              { icon: <FlagOutlined />, label: "OKR 目标", color: "#F59E0B", onClick: () => navigate("/okrs") },
              { icon: <BarChartOutlined />, label: "生成报表", color: "#F59E0B", onClick: () => navigate("/reports") },
              { icon: <AlertOutlined />, label: "风险登记册", color: "#EF4444", onClick: () => navigate("/risk") },
              { icon: <SwapOutlined />, label: "变更控制", color: "#06B6D4", onClick: () => navigate("/changes") },
              { icon: <ThunderboltOutlined />, label: "自动化规则", color: "#10B981", onClick: () => navigate("/automations") },
              { icon: <HistoryOutlined />, label: "经验教训", color: "#8B5CF6", onClick: () => navigate("/lessons") },
              { icon: <LayoutOutlined />, label: "看板视图", color: "#3B82F6", onClick: () => navigate("/kanban") },
            ].map((item, i) => (
              <Col key={i} xs={12} sm={8} md={4}>
                <Button
                  type="default"
                  size="large"
                  block
                  icon={item.icon}
                  onClick={item.onClick}
                  style={{
                    height: 56, borderRadius: 12, border: `1px solid ${item.color}20`,
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    fontWeight: 500, color: item.color, background: `${item.color}08`,
                    transition: "all 0.2s",
                    borderColor: `${item.color}30`,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = `${item.color}15`; e.currentTarget.style.borderColor = `${item.color}60`; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = `${item.color}08`; e.currentTarget.style.borderColor = `${item.color}30`; }}
                >
                  {item.label}
                </Button>
              </Col>
            ))}
          </Row>
        </Card>
      </motion.div>
    </div>
  );
};

export default Dashboard;
