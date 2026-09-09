import React, { useState, useEffect } from "react";
import { Card, Typography, Tag, Button, Space, Modal, Form, Input, Select, App, Rate, Collapse, Spin, Popconfirm, Alert, Divider } from "antd";
import { PlusOutlined, EditOutlined, TrophyOutlined, DatabaseOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { lessonApi } from "../api";

const { Title, Text } = Typography;

interface Lesson {
  id: string;
  projectName: string;
  category: string;
  title: string;
  description: string;
  whatWentWell: string;
  whatCouldImprove: string;
  actionItems: string;
  rating: number;
  createdBy: string;
  createdAt: string;
}

const CATEGORIES = ["项目管理", "技术", "沟通", "质量", "风险", "资源", "采购", "相关方"];

const LessonsLearned: React.FC = () => {
  const { message } = App.useApp();
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Lesson | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>("全部");
  const [form] = Form.useForm();

  // AI 自动生成模式
  const [genOpen, setGenOpen] = useState(false);
  const [genForm] = Form.useForm();
  const [genLoading, setGenLoading] = useState(false);
  const [genResult, setGenResult] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await lessonApi.list();
      setLessons(r?.items || []);
    } catch (e) {
      message.error("加载经验教训失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (lesson: Lesson) => {
    setEditing(lesson);
    form.setFieldsValue(lesson);
    setModalOpen(true);
  };

  const handleSubmit = async (values: any) => {
    setSaving(true);
    try {
      if (editing) {
        await lessonApi.update(editing.id, values);
        message.success("经验已更新");
      } else {
        await lessonApi.create(values);
        message.success("经验已记录");
      }
      setModalOpen(false);
      await load();
    } catch (e) {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await lessonApi.remove(id);
      message.success("已删除");
      await load();
    } catch (e) {
      message.error("删除失败");
    }
  };

  const handleArchive = async (id: string) => {
    try {
      await lessonApi.archive(id);
      message.success("已归档到知识库（组织过程资产）");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "归档失败");
    }
  };

  const handleArchiveAll = async () => {
    if (lessons.length === 0) { message.info("暂无经验教训可归档"); return; }
    try {
      const r: any = await lessonApi.archiveAll();
      message.success(`已批量归档 ${r?.data?.archived ?? lessons.length} 条到知识库`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "归档失败");
    }
  };

  // ============== AI 自动生成模式 ==============
  const openGen = () => {
    setGenResult(null);
    genForm.resetFields();
    setGenOpen(true);
  };

  const handleGenerate = async (values: any) => {
    setGenLoading(true);
    try {
      const r: any = await lessonApi.generate({
        topic: values.topic,
        category: values.category,
        kb_scope: values.kb_scope || "mine",
        context_hint: values.context_hint,
      });
      setGenResult(r?.data || {});
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "AI 生成失败");
    } finally {
      setGenLoading(false);
    }
  };

  const fillAndEdit = () => {
    const d = genResult || {};
    setEditing(null);
    form.setFieldsValue({
      title: d.title,
      category: d.category,
      whatWentWell: d.whatWentWell,
      whatCouldImprove: d.whatCouldImprove,
      actionItems: d.actionItems,
    });
    setGenOpen(false);
    setModalOpen(true);
  };

  const saveDirect = async () => {
    const d = genResult || {};
    try {
      await lessonApi.create({
        title: d.title,
        category: d.category,
        whatWentWell: d.whatWentWell,
        whatCouldImprove: d.whatCouldImprove,
        actionItems: d.actionItems,
      });
      message.success("已保存为经验教训");
      setGenOpen(false);
      setGenResult(null);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    }
  };

  const filtered = activeCategory === "全部" ? lessons : lessons.filter(l => l.category === activeCategory);

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>经验教训登记册 (Lessons Learned)</Title>
          <Text type="secondary">PMI中国AI项目管理社区 知识管理 · 持续改进组织过程资产</Text>
        </div>
        <Space>
          <Button icon={<DatabaseOutlined />} onClick={handleArchiveAll}>全部归档到知识库</Button>
          <Button icon={<ThunderboltOutlined />} onClick={openGen}>AI 自动生成</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate} data-tour="lessons-new">记录经验</Button>
        </Space>
      </div>

      {/* 分类筛选 */}
      <div className="pill-group" style={{ marginBottom: 24 }} data-tour="lessons-cat">
        {["全部", ...CATEGORIES].map(c => (
          <span key={c} className={`pill ${activeCategory === c ? "active" : ""}`} onClick={() => setActiveCategory(c)}>{c}</span>
        ))}
      </div>

      <Spin spinning={loading}>
        {filtered.length === 0 ? (
          <div className="enhanced-empty">
            <div style={{ fontSize: 60, marginBottom: 16 }}>📚</div>
            <h3>还没有经验教训记录</h3>
            <p>记录项目中的成功经验和改进点，为未来项目提供参考</p>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>记录第一条经验</Button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {filtered.map((lesson, idx) => (
              <motion.div key={lesson.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.08 }}>
                <Card className="card-hover" style={{ borderRadius: 16 }} bodyStyle={{ padding: 20 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                    <Space>
                      <TrophyOutlined style={{ fontSize: 20, color: "#F59E0B" }} />
                      <div>
                        <Text strong style={{ fontSize: 15 }}>{lesson.title}</Text>
                        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                          <Tag style={{ borderRadius: 6 }}>{lesson.category}</Tag>
                          {lesson.projectName && <Tag style={{ borderRadius: 6, background: "#EEF2FF", border: "none" }}>{lesson.projectName}</Tag>}
                        </div>
                      </div>
                    </Space>
                    <Rate disabled value={lesson.rating} style={{ fontSize: 14 }} />
                  </div>
                  <Collapse ghost items={[
                    { key: "1", label: "查看详情", children: (
                      <div>
                        <div style={{ marginBottom: 12 }}>
                          <Text strong style={{ color: "#10B981", display: "block", marginBottom: 4 }}>做得好的</Text>
                          <Text>{lesson.whatWentWell}</Text>
                        </div>
                        <div style={{ marginBottom: 12 }}>
                          <Text strong style={{ color: "#EF4444", display: "block", marginBottom: 4 }}>需要改进的</Text>
                          <Text>{lesson.whatCouldImprove}</Text>
                        </div>
                        <div>
                          <Text strong style={{ color: "#3B82F6", display: "block", marginBottom: 4 }}>后续行动</Text>
                          <Text style={{ whiteSpace: "pre-line" }}>{lesson.actionItems}</Text>
                        </div>
                      </div>
                    )},
                  ]} />
                  <div style={{ marginTop: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{lesson.createdBy} · {lesson.createdAt}</Text>
                    <Space>
                      <Button type="link" size="small" icon={<DatabaseOutlined />} onClick={() => handleArchive(lesson.id)}>归档到知识库</Button>
                      <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(lesson)}>编辑</Button>
                      <Popconfirm title="确定删除这条经验？" onConfirm={() => handleDelete(lesson.id)} okText="删除" cancelText="取消">
                        <Button type="link" size="small" danger>删除</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </Spin>

      <Modal title={editing ? "编辑经验教训" : "记录经验教训"} open={modalOpen} onCancel={() => setModalOpen(false)} footer={null} destroyOnClose width={640}>
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item label="标题" name="title" rules={[{ required: true }]}><Input placeholder="例如：多智能体协作架构设计经验" /></Form.Item>
          <Space style={{ width: "100%" }}>
            <Form.Item label="所属项目" name="projectName"><Input style={{ width: 200 }} placeholder="例如：AI-PM v1.0.0" /></Form.Item>
            <Form.Item label="类别" name="category" rules={[{ required: true }]} initialValue="项目管理"><Select style={{ width: 150 }} options={CATEGORIES.map(c => ({ label: c, value: c }))} /></Form.Item>
            <Form.Item label="评分" name="rating" initialValue={3}><Rate /></Form.Item>
          </Space>
          <Form.Item label="做得好的方面" name="whatWentWell" rules={[{ required: true, message: "请填写做得好的方面" }]}><Input.TextArea rows={2} placeholder="例如：Planner-Executor-Reviewer 三角色协作模式效果显著" /></Form.Item>
          <Form.Item label="需要改进的方面" name="whatCouldImprove" rules={[{ required: true, message: "请填写需要改进的方面" }]}><Input.TextArea rows={2} placeholder="例如：Agent 间通信延迟高峰期需优化" /></Form.Item>
          <Form.Item label="后续行动项" name="actionItems"><Input.TextArea rows={2} placeholder={"例如：\n1. 增加 MCP 消息优先级队列\n2. 引入 Agent 健康检查机制"} /></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" block loading={saving}>{editing ? "保存修改" : "记录经验"}</Button></Form.Item>
        </Form>
      </Modal>

      {/* AI 自动生成模式：结合知识库 RAG 直接生成解决办法 */}
      <Modal title="AI 自动生成经验教训" open={genOpen} onCancel={() => setGenOpen(false)} footer={null} destroyOnClose width={680}>
        {!genResult ? (
          <Form form={genForm} layout="vertical" onFinish={handleGenerate}>
            <Form.Item label="问题 / 场景描述" name="topic" rules={[{ required: true, message: "请描述经验或问题" }]}>
              <Input.TextArea rows={4} placeholder="例如：多智能体协作时 Agent 间通信高峰期延迟严重，导致任务堆积" />
            </Form.Item>
            <Space style={{ width: "100%" }} wrap>
              <Form.Item label="期望归类" name="category" initialValue="项目管理" style={{ width: 160 }}>
                <Select options={CATEGORIES.map(c => ({ label: c, value: c }))} />
              </Form.Item>
              <Form.Item label="检索知识库范围" name="kb_scope" initialValue="mine" style={{ width: 200 }}>
                <Select options={[
                  { label: "仅我的知识库", value: "mine" },
                  { label: "全部可见知识库", value: "all" },
                ]} />
              </Form.Item>
            </Space>
            <Form.Item label="补充背景（可选）" name="context_hint">
              <Input.TextArea rows={2} placeholder="例如：项目使用 FastAPI + 异步 SQLAlchemy，部署在 PostgreSQL 上" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" block loading={genLoading} icon={<ThunderboltOutlined />}>
                生成解决办法
              </Button>
            </Form.Item>
            <Text type="secondary" style={{ fontSize: 12 }}>
              系统将先从所选知识库做 RAG 召回，再结合召回内容由大模型生成结构化的经验教训与可直接落地的解决办法。
            </Text>
          </Form>
        ) : (
          <div>
            <Alert
              type={genResult.mode === "ai_generated" ? "success" : "info"}
              showIcon
              message={genResult.mode === "ai_generated" ? "已结合知识库生成解决办法" : (genResult.mode === "rag_only" ? "未配置大模型，已返回知识库检索结果" : "已返回生成内容")}
              style={{ marginBottom: 12 }}
            />
            <Title level={5} style={{ marginTop: 0 }}>{genResult.title}</Title>
            {genResult.whatWentWell && (
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ color: "#10B981", display: "block", marginBottom: 4 }}>做得好的</Text>
                <Text style={{ whiteSpace: "pre-line" }}>{genResult.whatWentWell}</Text>
              </div>
            )}
            {genResult.whatCouldImprove && (
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ color: "#EF4444", display: "block", marginBottom: 4 }}>需要改进的</Text>
                <Text style={{ whiteSpace: "pre-line" }}>{genResult.whatCouldImprove}</Text>
              </div>
            )}
            <div style={{ marginBottom: 12 }}>
              <Text strong style={{ color: "#3B82F6", display: "block", marginBottom: 4 }}>基于知识库的解决办法</Text>
              <div style={{ whiteSpace: "pre-line", background: "#F8FAFC", padding: 12, borderRadius: 8, fontSize: 13, maxHeight: 280, overflow: "auto" }}>
                {genResult.solution}
              </div>
            </div>
            {genResult.actionItems && (
              <div style={{ marginBottom: 12 }}>
                <Text strong style={{ color: "#6366F1", display: "block", marginBottom: 4 }}>后续行动</Text>
                <Text style={{ whiteSpace: "pre-line" }}>{genResult.actionItems}</Text>
              </div>
            )}
            {Array.isArray(genResult.references) && genResult.references.length > 0 && (
              <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
                引用知识库：{genResult.references.join("、")}
              </Text>
            )}
            <Divider style={{ margin: "12px 0" }} />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <Button onClick={() => setGenResult(null)}>重新生成</Button>
              <Button onClick={fillAndEdit}>填入并编辑</Button>
              <Button type="primary" onClick={saveDirect}>直接保存为经验</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default LessonsLearned;
