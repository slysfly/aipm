import React, { useEffect, useState } from "react";
import { Card, Row, Col, Typography, Tag, Progress, Button, Space, Modal, Form, Input, Select, App, Spin, Empty, Statistic, Tabs, Tooltip } from "antd";
import { PlusOutlined, FundProjectionScreenOutlined, BarChartOutlined, AimOutlined, DollarOutlined, AlertOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { projectApi } from "../api";
import { useNavigate } from "react-router-dom";

const { Title, Text } = Typography;

const Portfolio: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<any[]>([]);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await projectApi.list({ page_size: 200 });
        setProjects(res?.items || []);
      } catch (e: any) {
        message.error("加载项目组合失败");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const totalBudget = projects.reduce((s, p) => s + (Number(p.budget) || 0), 0);
  const activeProjects = projects.filter(p => p.status === "active").length;
  const avgProgress = projects.length > 0
    ? Math.round(projects.reduce((s, p) => s + (p.progress || 0), 0) / projects.length)
    : 0;
  const overdueCount = projects.filter(p => {
    if (!p.end_date || p.status === "done") return false;
    return new Date(p.end_date) < new Date();
  }).length;

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spin size="large" /></div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>项目组合管理 (Portfolio)</Title>
          <Text type="secondary">PMI中国AI项目管理社区 标准组合管理 · 全局资源分配与优先级决策</Text>
        </div>
        <Tooltip title="组合创建功能暂未开放">
          <Button type="primary" icon={<PlusOutlined />} disabled>新建组合</Button>
        </Tooltip>
      </div>

      {/* 组合 KPI */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} md={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>项目总数</span>} value={projects.length} prefix={<FundProjectionScreenOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
        <Col xs={12} md={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #3B82F6 0%, #06B6D4 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>进行中</span>} value={activeProjects} prefix={<BarChartOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
        <Col xs={12} md={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>逾期项目</span>} value={overdueCount} prefix={<AlertOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
        <Col xs={12} md={6}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
              <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>总预算</span>} value={`¥${totalBudget.toLocaleString()}`} prefix={<DollarOutlined />} valueStyle={{ color: "#fff" }} />
            </Card>
          </motion.div>
        </Col>
      </Row>

      {/* 组合健康度 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={8}>
          <Card title="组合健康度" style={{ borderRadius: 16 }} className="card-hover">
            <div style={{ textAlign: "center", padding: "20px 0" }}>
              <Progress type="dashboard" percent={avgProgress} strokeColor={{ from: "#4F46E5", to: "#06B6D4" }} size={160} />
              <div style={{ marginTop: 12 }}>
                <Text strong>平均进度 {avgProgress}%</Text>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="项目优先级矩阵" style={{ borderRadius: 16 }} className="card-hover" data-tour="portfolio-matrix">
            {projects.length === 0 ? (
              <Empty description="暂无项目" />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {projects.slice(0, 8).map((p, idx) => (
                  <motion.div key={p.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.05 }}>
                    <div
                      onClick={() => navigate(`/projects/${p.id}`)}
                      style={{ cursor: "pointer", padding: "10px 14px", borderRadius: 10, background: "#F8FAFC", border: "1px solid #E2E8F0", transition: "all 0.2s" }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = "#4F46E5"; e.currentTarget.style.boxShadow = "0 2px 8px rgba(79,70,229,0.1)"; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = "#E2E8F0"; e.currentTarget.style.boxShadow = "none"; }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <Text strong style={{ fontSize: 13 }}>{p.name}</Text>
                        <Space>
                          <Tag color={p.priority <= 2 ? "red" : p.priority === 3 ? "orange" : "blue"} style={{ borderRadius: 6, margin: 0 }}>
                            {p.priority <= 2 ? "高优先级" : p.priority === 3 ? "中优先级" : "低优先级"}
                          </Tag>
                          <Tag color={p.status === "active" ? "green" : p.status === "planning" ? "blue" : "default"} style={{ borderRadius: 6, margin: 0 }}>
                            {p.status === "active" ? "进行中" : p.status === "planning" ? "规划" : p.status}
                          </Tag>
                        </Space>
                      </div>
                      <Progress percent={p.progress || 0} size="small" strokeColor={{ from: "#4F46E5", to: "#7C3AED" }} showInfo={false} />
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* 资源分配概览 */}
      <Card title="资源分配概览" style={{ borderRadius: 16 }} className="card-hover">
        <Row gutter={[12, 12]}>
          {projects.slice(0, 6).map((p, idx) => (
            <Col key={p.id} xs={24} sm={12} md={8}>
              <div style={{ padding: 12, borderRadius: 10, background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
                <Text strong style={{ fontSize: 12 }}>{p.name}</Text>
                <div style={{ marginTop: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>预算使用</Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>{p.budget_used || 0} / {p.budget || 0}</Text>
                  </div>
                  <Progress percent={p.budget ? Math.round(((p.budget_used || 0) / p.budget) * 100) : 0} size="small" strokeColor="#F59E0B" showInfo={false} />
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>
    </div>
  );
};

export default Portfolio;
