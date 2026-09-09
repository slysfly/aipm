import React, { useEffect, useState } from "react";
import { Card, Typography, Tag, Table, Button, Space, Modal, Form, Input, InputNumber, Select, DatePicker, App, Spin, Empty, Progress, Descriptions, Row, Col, Statistic, Divider, List, Tabs, Alert, Rate, message } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, RobotOutlined, ProfileOutlined, LinkOutlined, FundProjectionScreenOutlined, AlertOutlined, ClockCircleOutlined, CheckCircleOutlined, AimOutlined, DollarOutlined, TeamOutlined, BulbOutlined, DatabaseOutlined } from "@ant-design/icons";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { projectApi, taskApi, lessonApi, sprintApi, projectTypeApi, knowledgeApi } from "../api";
import { useTaskProgress, onDataChanged } from "../realtime/useRealtime";
import dayjs from "dayjs";

const { Title, Text } = Typography;

const ProjectDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const [project, setProject] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editModal, setEditModal] = useState(false);
  const [taskModal, setTaskModal] = useState(false);
  const [editingTask, setEditingTask] = useState<any>(null);
  const [form] = Form.useForm();
  const [taskForm] = Form.useForm();
  const [lessons, setLessons] = useState<any[]>([]);
  const [sprints, setSprints] = useState<any[]>([]);
  const [genResult, setGenResult] = useState<any>(null);
  const [genTaskId, setGenTaskId] = useState<string | null>(null);
  // 订阅后台「AI 总结经验教训」任务的实时进度/结果（WebSocket 推送）
  const genTask = useTaskProgress(genTaskId);

  const [types, setTypes] = useState<any[]>([]);
  useEffect(() => {
    projectTypeApi.list().then((d: any) => setTypes(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);
  const typeMap: Record<string, any> = {};
  types.forEach((t) => { typeMap[t.code] = t; });
  const renderTypeTag = (code?: string) => {
    const t = code ? typeMap[code] : undefined;
    if (!t) return code ? <Tag>{code}</Tag> : null;
    return <Tag color={t.color} style={{ borderRadius: 6 }}>{t.name}</Tag>;
  };

  // 本项目知识库（按 project_id 过滤）
  const [projKbs, setProjKbs] = useState<any[]>([]);
  useEffect(() => {
    if (!id) return;
    knowledgeApi.listBases("all", { project_id: id })
      .then((r: any) => setProjKbs(Array.isArray(r) ? r : (r?.items || [])))
      .catch(() => setProjKbs([]));
  }, [id]);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [p, s, t, lr, sp] = await Promise.all([
        projectApi.get(id),
        projectApi.statistics(id).catch(() => null),
        taskApi.list({ project_id: id, page_size: 200 }),
        lessonApi.list().catch(() => null),
        sprintApi.list({ project_id: id, page_size: 200 }).catch(() => ({ items: [] })),
      ]);
      setProject(p);
      setStats(s);
      setTasks(t?.items || []);
      setSprints((sp as any)?.items || []);
      const projName = (p as any)?.name || "";
      setLessons((lr?.items || []).filter((l: any) => l.projectName === projName));
    } catch (e: any) {
      msg.error(e?.response?.data?.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  // 后台 AI 任务完成后：用结果刷新经验教训卡片并重新拉取列表
  useEffect(() => {
    if (genTaskId && genTask.done) {
      const r = genTask.result || {};
      setGenResult(r);
      if (r?.mode === "ai_generated") msg.success(`AI 已总结 ${r.lessons?.length || 0} 条经验教训并存入知识库`);
      else if (r?.mode === "no_llm") msg.warning("未配置系统大模型，无法自动生成，可在「经验教训登记册」手动记录");
      load();
      setGenTaskId(null);
    }
  }, [genTask.done, genTaskId]);

  useEffect(() => {
    if (genTaskId && genTask.failed) {
      msg.error(genTask.error || "AI 总结失败");
      setGenTaskId(null);
    }
  }, [genTask.failed, genTaskId]);

  // 多用户协作：其他人在本项目沉淀了经验教训，实时刷新
  useEffect(() => {
    return onDataChanged("lessons", (e) => {
      if (e?.project_id === id) load();
    });
  }, [id]);

  const handleEdit = async (values: any) => {
    try {
      const payload = { ...values };
      if (values.start_date) payload.start_date = values.start_date.format("YYYY-MM-DD");
      if (values.end_date) payload.end_date = values.end_date.format("YYYY-MM-DD");
      if (values.budget === null || values.budget === undefined || values.budget === "") delete payload.budget;
      else payload.budget = Number(values.budget);
      await projectApi.update(id!, payload);
      msg.success("项目已更新");
      setEditModal(false);
      load();
    } catch (e: any) { msg.error(e?.response?.data?.detail || "更新失败"); }
  };

  const handleCreateTask = async (values: any) => {
    try {
      const payload: any = { ...values, project_id: id };
      if (values.due_date) payload.due_date = values.due_date.format("YYYY-MM-DD");
      if (editingTask) {
        const { project_id, ...updatePayload } = payload;
        await taskApi.update(editingTask.id, updatePayload);
        msg.success("任务已更新");
      } else {
        await taskApi.create(payload);
        msg.success("任务已创建");
      }
      setTaskModal(false);
      setEditingTask(null);
      taskForm.resetFields();
      load();
    } catch (e: any) { msg.error(e?.response?.data?.detail || "操作失败"); }
  };

  const openTaskEdit = (r: any) => {
    setEditingTask(r);
    taskForm.setFieldsValue({
      name: r.name,
      description: r.description,
      priority: r.priority,
      status: r.status || "todo",
      assignee_id: r.assignee_id,
    });
    setTaskModal(true);
  };

  const openEditModal = () => {
    form.setFieldsValue({
      name: project.name,
      description: project.description,
      status: project.status,
      priority: project.priority,
      project_type: project.project_type,
      budget: project.budget,
      start_date: project.start_date ? dayjs(project.start_date) : undefined,
      end_date: project.end_date ? dayjs(project.end_date) : undefined,
    });
    setEditModal(true);
  };

  const handleStatusChange = async (taskId: string, status: string) => {
    try {
      await taskApi.update(taskId, { status });
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status } : t));
      msg.success("状态已更新");
    } catch { msg.error("更新失败"); }
  };

  const handleSummarize = async () => {
    setGenResult(null);
    try {
      const r: any = await projectApi.summarizeLessons(id!);
      if (r?.task_id) {
        // 后台异步执行：进度经 WebSocket 实时推送，完成后由上方 effect 刷新
        setGenTaskId(r.task_id);
      } else {
        msg.error("未能创建后台任务");
      }
    } catch (e: any) {
      msg.error(e?.response?.data?.detail || "AI 总结失败");
    }
  };

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spin size="large" /></div>;
  if (!project) return <Empty description="项目不存在" />;

  const doneTasks = tasks.filter(t => t.status === "done").length;
  const overdueTasks = tasks.filter(t => t.due_date && new Date(t.due_date) < new Date() && t.status !== "done");
  const totalProgress = tasks.length > 0 ? Math.round((doneTasks / tasks.length) * 100) : 0;

  return (
    <div>
      {/* 头部 */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="gradient-bg" style={{ borderRadius: 20, padding: "24px 32px", marginBottom: 24, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: -30, right: -10, width: 180, height: 180, borderRadius: "50%", background: "rgba(255,255,255,0.05)", pointerEvents: "none" }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", rowGap: 16, columnGap: 16, position: "relative", zIndex: 1 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <Title level={3} style={{ color: "#fff", margin: 0 }}>{project.name}</Title>
              <Tag color={project.status === "active" ? "green" : project.status === "planning" ? "blue" : "default"} style={{ borderRadius: 6 }}>
                {project.status === "active" ? "进行中" : project.status === "planning" ? "规划中" : project.status === "done" ? "已完成" : "已归档"}
              </Tag>
              <Tag color={project.priority <= 2 ? "red" : project.priority === 3 ? "orange" : "blue"} style={{ borderRadius: 6 }}>
                {project.priority <= 2 ? "高优先级" : project.priority === 3 ? "中优先级" : "低优先级"}
              </Tag>
            </div>
            <Text style={{ color: "rgba(255,255,255,0.75)" }}>{project.description || "暂无描述"}</Text>
          </div>
          <Space>
            <Button icon={<RobotOutlined />} ghost onClick={() => navigate(`/ai/wbs?projectId=${project.id}`)}>AI 生成 WBS</Button>
            <Button type="default" ghost icon={<EditOutlined />} onClick={openEditModal}>编辑项目</Button>
          </Space>
        </div>
      </motion.div>

      {/* KPI 卡片 */}
      <Row data-tour="pd-tabs" gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={8} md={4}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>总任务</span>} value={tasks.length} prefix={<ProfileOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>已完成</span>} value={doneTasks} prefix={<CheckCircleOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #F59E0B 0%, #EF4444 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>逾期</span>} value={overdueTasks.length} prefix={<AlertOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #3B82F6 0%, #6366F1 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>进度</span>} value={`${totalProgress}%`} prefix={<ClockCircleOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #8B5CF6 0%, #A855F7 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>预算</span>} value={`¥${Number(project.budget || 0).toLocaleString()}`} prefix={<DollarOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={4}>
          <Card className="card-hover" style={{ borderRadius: 16, background: "linear-gradient(135deg, #06B6D4 0%, #0891B2 100%)" }}>
            <Statistic title={<span style={{ color: "rgba(255,255,255,0.8)" }}>成员</span>} value={project.member_count || stats?.member_count || "—"} prefix={<TeamOutlined />} valueStyle={{ color: "#fff" }} />
          </Card>
        </Col>
      </Row>

      {/* 项目信息 + 进度 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={10}>
          <Card title="项目信息" style={{ borderRadius: 16 }} className="card-hover" extra={
            <Button type="link" icon={<EditOutlined />} onClick={openEditModal}>编辑</Button>
          }>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="状态"><Tag>{project.status === "active" ? "进行中" : project.status === "planning" ? "规划" : project.status === "done" ? "已完成" : "归档"}</Tag></Descriptions.Item>
              <Descriptions.Item label="优先级"><Tag color={project.priority <= 2 ? "red" : project.priority === 3 ? "orange" : "blue"}>{project.priority <= 2 ? "高" : project.priority === 3 ? "中" : "低"}</Tag></Descriptions.Item>
              <Descriptions.Item label="行业">{project.industry_type || "—"}</Descriptions.Item>
              <Descriptions.Item label="项目类型">{renderTypeTag(project.project_type) || "—"}</Descriptions.Item>
              <Descriptions.Item label="开始">{project.start_date || "—"}</Descriptions.Item>
              <Descriptions.Item label="结束">{project.end_date || "—"}</Descriptions.Item>
              <Descriptions.Item label="预算">¥{Number(project.budget || 0).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="组合">{project.portfolio_id || "未分配"}</Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>{project.description || "暂无"}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="项目进度" style={{ borderRadius: 16 }} className="card-hover">
            <div style={{ textAlign: "center", padding: "12px 0" }}>
              <Progress type="dashboard" percent={totalProgress} strokeColor={{ from: "#4F46E5", to: "#06B6D4" }} size={140} format={p => <span style={{ fontSize: 18, fontWeight: 700 }}>{p}%</span>} />
            </div>
            <Divider>任务状态分布</Divider>
            <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
              {[
                { label: "待办", key: "todo", color: "#94A3B8" },
                { label: "进行中", key: "in_progress", color: "#3B82F6" },
                { label: "审查", key: "in_review", color: "#F59E0B" },
                { label: "测试", key: "testing", color: "#8B5CF6" },
                { label: "已完成", key: "done", color: "#10B981" },
              ].map(s => {
                const count = tasks.filter(t => (t.status || "todo") === s.key).length;
                const pct = tasks.length > 0 ? Math.round((count / tasks.length) * 100) : 0;
                return (
                  <div key={s.key} style={{ textAlign: "center", padding: "8px 16px", borderRadius: 10, background: `${s.color}10`, minWidth: 80 }}>
                    <Text style={{ color: s.color, fontSize: 20, fontWeight: 800 }}>{count}</Text>
                    <div style={{ color: s.color, fontSize: 11, fontWeight: 500 }}>{s.label}</div>
                    <Text type="secondary" style={{ fontSize: 10 }}>{pct}%</Text>
                  </div>
                );
              })}
            </div>
          </Card>
        </Col>
      </Row>

      {/* 本项目知识库（关联入口） */}
      <Card
        title={<span><DatabaseOutlined style={{ marginRight: 8, color: "#4F46E5" }} />本项目知识库（服务于本项目的知识资产）</span>}
        style={{ borderRadius: 16, marginBottom: 24 }} className="card-hover"
        extra={
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>共 {projKbs.length} 个</Text>
            <Button type="link" icon={<LinkOutlined />} onClick={() => navigate(`/knowledge?projectId=${id}`)}>前往知识库管理</Button>
          </Space>
        }
      >
        {projKbs.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <div>本项目尚未关联任何知识库</div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  在「知识库」页面创建或编辑知识库时，可选择关联到本项目；关联后 AI 问答将优先检索本项目专属资料
                </Text>
              </div>
            }
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/knowledge?projectId=${id}&new=1`)}>立即创建</Button>
          </Empty>
        ) : (
          <Row gutter={[12, 12]}>
            {projKbs.map((kb: any) => (
              <Col xs={24} sm={12} md={8} key={kb.id}>
                <Card size="small" hoverable onClick={() => navigate(`/knowledge?kbId=${kb.id}`)} style={{ borderRadius: 12, borderLeft: "3px solid #4F46E5" }}>
                  <Space direction="vertical" size={2} style={{ width: "100%" }}>
                    <Space style={{ width: "100%", justifyContent: "space-between" }}>
                      <Text strong style={{ fontSize: 14 }}>{kb.name}</Text>
                      <Tag color="blue">{kb.document_count || 0} 篇</Tag>
                    </Space>
                    {kb.description && <Text type="secondary" style={{ fontSize: 12 }} ellipsis>{kb.description}</Text>}
                    <Tag color={kb.visibility === "system" ? "purple" : kb.visibility === "shared" ? "blue" : "default"} style={{ fontSize: 10, marginTop: 4 }}>
                      {kb.visibility === "system" ? "系统共享" : kb.visibility === "shared" ? "已分享" : "私有"}
                    </Tag>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Card>

      {/* 任务列表 */}
      <Card
        title={<span><ProfileOutlined style={{ marginRight: 8 }} />任务列表 ({tasks.length})</span>}
        style={{ borderRadius: 16 }} className="card-hover"
        extra={
          <Space>
            <Button icon={<LinkOutlined />} onClick={() => navigate(`/kanban?projectId=${project.id}`)}>看板视图</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingTask(null); setTaskModal(true); }}>创建任务</Button>
          </Space>
        }
      >
        {tasks.length === 0 ? (
          <div className="enhanced-empty">
            <div style={{ fontSize: 48, marginBottom: 16 }}>📋</div>
            <h3>暂无任务</h3>
            <p>使用 AI 生成 WBS 或手动创建任务</p>
            <Space>
              <Button type="primary" icon={<RobotOutlined />} onClick={() => navigate(`/ai/wbs?projectId=${project.id}`)}>AI 生成 WBS</Button>
              <Button icon={<PlusOutlined />} onClick={() => { setEditingTask(null); setTaskModal(true); }}>手动创建</Button>
            </Space>
          </div>
        ) : (
          <Table
            dataSource={tasks}
            rowKey="id"
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
            className="enhanced-table"
            columns={[
              { title: "WBS", dataIndex: "wbs_code", key: "wbs_code", width: 100, render: (c: string) => <Tag style={{ fontFamily: "monospace", borderRadius: 4 }}>{c || "—"}</Tag> },
              { title: "任务名称", dataIndex: "name", key: "name", render: (n: string, r: any) => <Text strong onClick={() => openTaskEdit(r)} style={{ cursor: "pointer", color: "#4F46E5" }}>{n}</Text> },
              { title: "状态", dataIndex: "status", key: "status", render: (s: string, r: any) => (
                <Select value={s || "todo"} size="small" style={{ width: 100 }} onChange={val => handleStatusChange(r.id, val)}
                  options={[{ label: "待办", value: "todo" }, { label: "进行中", value: "in_progress" }, { label: "审查", value: "in_review" }, { label: "测试", value: "testing" }, { label: "已完成", value: "done" }]} />
              )},
              { title: "优先级", dataIndex: "priority", key: "priority", width: 80, render: (p: number) => <Tag color={p <= 2 ? "red" : p === 3 ? "orange" : "blue"}>{p <= 2 ? "高" : p === 3 ? "中" : "低"}</Tag> },
              { title: "负责人", dataIndex: "assignee_id", key: "assignee_id", render: (a: string) => a || "—" },
              { title: "截止", dataIndex: "due_date", key: "due_date", render: (d: string) => {
                if (!d) return "—";
                const isOverdue = new Date(d) < new Date();
                return <Text style={{ color: isOverdue ? "#EF4444" : "inherit" }}>{d}</Text>;
              }},
              { title: "进度", dataIndex: "progress", key: "progress", render: (p: number) => <Progress percent={p || 0} size="small" style={{ width: 100 }} /> },
            ]}
          />
        )}
      </Card>

      {/* 经验教训：AI 基于项目真实数据自动总结并直接入库知识库 */}
      <Card
        title={<span><BulbOutlined style={{ marginRight: 8, color: "#F59E0B" }} />经验教训 (Lessons Learned)</span>}
        style={{ borderRadius: 16 }} className="card-hover"
        extra={<Button type="primary" icon={<RobotOutlined />} loading={!!genTaskId && !genTask.done && !genTask.failed} onClick={handleSummarize}>AI 自动总结</Button>}
      >
        <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
          一键基于本项目真实数据（任务 / 风险 / 变更 / 里程碑 / 进展）生成结构化经验教训，并直接沉淀到项目知识库，形成组织过程资产(OPA)闭环，无需手动录入与归档。
        </Text>

        {genTaskId && !genTask.done && !genTask.failed && (
          <div style={{ marginBottom: 16, padding: "12px 16px", background: "#FFFBE6", borderRadius: 12, border: "1px solid #FFE58F" }}>
            <Progress percent={genTask.progress} status="active" />
            <Text type="secondary">{genTask.message || "AI 正在后台总结经验教训，完成后将实时通知..."}</Text>
          </div>
        )}

        {genResult && genResult.mode === "ai_generated" && (
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 16, borderRadius: 12 }}
            message={`已生成 ${genResult.lessons?.length || 0} 条经验教训并直接存入知识库`}
            description={(() => {
              const arcs: any[] = genResult.archives || [];
              const kbNames = Array.from(new Set(arcs.filter(a => a.kb_name).map((a: any) => a.kb_name)));
              return kbNames.map((kb: any, i: number) => (
                <div key={i}><DatabaseOutlined style={{ marginRight: 6, color: "#3B82F6" }} />{kb}：{arcs.filter((a: any) => a.kb_name === kb).map((a: any) => a.doc_title).join("、")}</div>
              ));
            })()}
          />
        )}

        {genResult && genResult.mode === "no_llm" && (
          <Alert type="info" showIcon style={{ marginBottom: 16, borderRadius: 12 }} message="未配置系统大模型，无法自动生成。可在「经验教训登记册」手动记录本项目的经验。" />
        )}

        {genResult?.lessons?.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
            {genResult.lessons.map((l: any, i: number) => (
              <Card key={i} size="small" style={{ borderRadius: 12, borderLeft: "3px solid #F59E0B" }}>
                <Space style={{ marginBottom: 6 }} wrap>
                  <Text strong>{l.title}</Text>
                  <Tag>{l.category}</Tag>
                  <Rate disabled value={l.rating} style={{ fontSize: 12 }} />
                </Space>
                {l.whatWentWell && <div style={{ marginBottom: 4 }}><Text strong style={{ color: "#10B981" }}>做得好的：</Text> <Text style={{ whiteSpace: "pre-line" }}>{l.whatWentWell}</Text></div>}
                {l.whatCouldImprove && <div style={{ marginBottom: 4 }}><Text strong style={{ color: "#EF4444" }}>待改进：</Text> <Text style={{ whiteSpace: "pre-line" }}>{l.whatCouldImprove}</Text></div>}
                {l.actionItems && <div><Text strong style={{ color: "#3B82F6" }}>行动项：</Text> <Text style={{ whiteSpace: "pre-line" }}>{l.actionItems}</Text></div>}
              </Card>
            ))}
          </div>
        )}

        <Divider orientation="left" plain>本项目已有经验教训（{(lessons || []).length}）</Divider>
        {(!lessons || lessons.length === 0) ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无经验教训，点击右上角「AI 自动总结」生成" />
        ) : (
          <List
            dataSource={lessons}
            renderItem={(l: any) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<BulbOutlined style={{ fontSize: 18, color: "#F59E0B" }} />}
                  title={<Space><span>{l.title}</span><Tag>{l.category}</Tag><Rate disabled value={l.rating} style={{ fontSize: 12 }} /></Space>}
                  description={
                    <div>
                      {l.whatWentWell && <div><Text type="secondary">做得好：</Text>{l.whatWentWell}</div>}
                      {l.whatCouldImprove && <div><Text type="secondary">待改进：</Text>{l.whatCouldImprove}</div>}
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      {/* 编辑项目弹窗 */}
      <Modal title="编辑项目" open={editModal} onCancel={() => setEditModal(false)} footer={null} destroyOnClose width={640}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Form.Item label="项目名称" name="name" rules={[{ required: true, message: "请输入项目名称" }]}>
            <Input placeholder="例如：智慧城市管理系统" />
          </Form.Item>
          <Form.Item label="描述" name="description"><Input.TextArea rows={2} placeholder="例如：覆盖门禁、停车、能耗三大子系统的一期建设" /></Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label="状态" name="status"><Select style={{ width: 150 }} options={[{ label: "规划", value: "planning" }, { label: "进行中", value: "active" }, { label: "已完成", value: "done" }, { label: "已归档", value: "archived" }]} /></Form.Item>
            <Form.Item label="优先级" name="priority" initialValue={3}><Select style={{ width: 150 }} options={[{ label: "高", value: 1 }, { label: "中", value: 3 }, { label: "低", value: 5 }]} /></Form.Item>
            <Form.Item label="项目类型" name="project_type">
              <Select
                placeholder="选择项目类型"
                allowClear
                showSearch
                optionFilterProp="label"
                options={types.map((t) => ({
                  label: (
                    <Space>
                      <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 3, background: t.color, border: "1px solid #d9d9d9" }} />
                      {t.name} <Text type="secondary" style={{ fontSize: 12 }}>{t.code}</Text>
                    </Space>
                  ),
                  value: t.code,
                }))}
              />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }}>
            <Form.Item label="开始日期" name="start_date"><DatePicker style={{ width: 150 }} /></Form.Item>
            <Form.Item label="结束日期" name="end_date"><DatePicker style={{ width: 150 }} /></Form.Item>
            <Form.Item label="预算" name="budget"><InputNumber min={0} prefix="¥" style={{ width: 150 }} placeholder="预算金额" /></Form.Item>
          </Space>
          <Form.Item><Button type="primary" htmlType="submit" block>保存变更</Button></Form.Item>
        </Form>
      </Modal>

      {/* 创建/编辑任务弹窗 */}
      <Modal title={editingTask ? "编辑任务" : "创建任务"} open={taskModal} onCancel={() => { setTaskModal(false); setEditingTask(null); }} footer={null} destroyOnClose>
        <Form form={taskForm} layout="vertical" onFinish={handleCreateTask}>
          <Form.Item label="任务名称" name="name" rules={[{ required: true, message: "请输入任务名称" }]}><Input placeholder="例如：完成登录模块开发" /></Form.Item>
          <Form.Item label="描述" name="description"><Input.TextArea rows={2} placeholder="例如：实现用户名/密码登录，包含表单校验与错误提示" /></Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label="状态" name="status" initialValue="todo"><Select style={{ width: 130 }} options={[{ label: "待办", value: "todo" }, { label: "进行中", value: "in_progress" }, { label: "审查", value: "in_review" }, { label: "测试", value: "testing" }, { label: "已完成", value: "done" }]} /></Form.Item>
            <Form.Item label="优先级" name="priority" initialValue={3}><Select style={{ width: 130 }} options={[{ label: "高", value: 1 }, { label: "中", value: 3 }, { label: "低", value: 5 }]} /></Form.Item>
            <Form.Item label="负责人ID" name="assignee_id"><Input style={{ width: 130 }} placeholder="用户ID" /></Form.Item>
          </Space>
          <Form.Item label="所属 Sprint" name="sprint_id" tooltip="仅显示本项目的 Sprint，可留空">
            <Select
              allowClear
              options={sprints.map((s: any) => ({ value: s.id, label: s.name }))}
              placeholder={sprints.length ? "选择 Sprint（可留空）" : "本项目暂无 Sprint"}
            />
          </Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block>{editingTask ? "保存修改" : "创建任务"}</Button></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ProjectDetail;
