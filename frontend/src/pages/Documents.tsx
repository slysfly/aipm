import React, { useState, useEffect } from "react";
import { Card, Button, Typography, Space, Tree, Input, Empty, App, Select, Modal, Tag, List, Avatar, Divider, Popconfirm } from "antd";
import { PlusOutlined, DeleteOutlined, EditOutlined, FileTextOutlined, FolderOutlined, StarOutlined, ClockCircleOutlined, UserOutlined, SearchOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import DOMPurify from "dompurify";
import { docApi } from "../api";

const { Title, Text } = Typography;
const { TextArea } = Input;

interface Doc {
  id: string;
  title: string;
  content: string;
  updatedAt: string;
  author: string;
  folder: string;
}

const FOLDERS = ["产品文档", "技术文档", "Sprint 回顾", "会议记录", "设计方案", "通用"];

/**
 * 将轻量 Markdown 片段转换为 HTML，并用 DOMPurify 消毒，
 * 防止用户输入中的 <script>/<img onerror> 等被当作 HTML 执行（存储型 XSS 防护）。
 */
const renderMarkdownToHtml = (content: string): string => {
  const rawHtml = content
    .replace(/^### (.+)$/gm, '<h3 style="font-size:16px;font-weight:600;margin:16px 0 8px;color:#0F172A">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:18px;font-weight:700;margin:20px 0 10px;color:#0F172A">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:22px;font-weight:700;margin:24px 0 12px;color:#0F172A">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/- (.+)$/gm, '<li style="margin:4px 0;padding-left:8px;list-style-type:disc;margin-left:16px">$1</li>')
    .replace(/\n/g, '<br/>');
  return DOMPurify.sanitize(rawHtml);
};

const Documents: React.FC = () => {
  const { message } = App.useApp();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeDoc, setActiveDoc] = useState<Doc | null>(null);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [activeFolder, setActiveFolder] = useState<string>("全部");
  const [searchQuery, setSearchQuery] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await docApi.list();
      const items: any[] = r?.items || [];
      const mapped = items.map((d: any) => ({ ...d, folder: d.folder || "通用" }));
      setDocs(mapped);
      setActiveDoc(mapped.length ? mapped[0] : null);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载文档失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const filteredDocs = docs.filter((d) => {
    const matchFolder = activeFolder === "全部" || d.folder === activeFolder;
    const matchSearch = !searchQuery || d.title.toLowerCase().includes(searchQuery.toLowerCase()) || d.content.toLowerCase().includes(searchQuery.toLowerCase());
    return matchFolder && matchSearch;
  });

  const handleSave = async () => {
    if (!activeDoc) return;
    const updatedAt = new Date().toISOString().split("T")[0];
    try {
      await docApi.update(activeDoc.id, { title: activeDoc.title, content: editContent });
      const updated = { ...activeDoc, content: editContent, updatedAt };
      setDocs((prev) => prev.map((d) => d.id === activeDoc.id ? updated : d));
      setActiveDoc(updated);
      setEditing(false);
      message.success("已保存");
    } catch (e: any) { message.error(e?.response?.data?.detail || "保存失败"); }
  };

  const handleNewDoc = async () => {
    try {
      const r: any = await docApi.create({
        title: "新建文档",
        content: "# 新建文档\n\n在这里开始写作...",
        folder: "产品文档",
        author: "当前用户",
      });
      const newDoc: Doc = { ...r, folder: r.folder || "产品文档" };
      setDocs([newDoc, ...docs]);
      setActiveDoc(newDoc);
      setEditContent(newDoc.content);
      setEditing(true);
    } catch (e: any) { message.error(e?.response?.data?.detail || "创建失败"); }
  };

  const handleDeleteDoc = async (id: string) => {
    try {
      await docApi.remove(id);
      setDocs(docs.filter((d) => d.id !== id));
      if (activeDoc?.id === id) setActiveDoc(null);
      message.success("已删除");
    } catch (e: any) { message.error(e?.response?.data?.detail || "删除失败"); }
  };

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>文档</Title>
          <Text type="secondary">Notion 级文档编辑器，支持 Markdown 写作和知识管理</Text>
        </div>
        <Space>
          <Input.Search
            placeholder="搜索文档..."
            prefix={<SearchOutlined />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleNewDoc}>
            新建文档
          </Button>
        </Space>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {/* 侧边文件夹和文档列表 */}
        <div style={{ width: 280, flexShrink: 0 }}>
          <Card style={{ borderRadius: 16, marginBottom: 12 }} styles={{ body: { padding: 12 } }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div
                onClick={() => setActiveFolder("全部")}
                style={{
                  padding: "8px 12px", borderRadius: 8, cursor: "pointer",
                  background: activeFolder === "全部" ? "#EEF2FF" : "transparent",
                  color: activeFolder === "全部" ? "#4F46E5" : "#475569",
                  fontWeight: activeFolder === "全部" ? 600 : 400, fontSize: 13,
                }}
              >
                📁 全部文档 ({docs.length})
              </div>
              {FOLDERS.map((f) => {
                const count = docs.filter((d) => d.folder === f).length;
                return (
                  <div
                    key={f}
                    onClick={() => setActiveFolder(f)}
                    style={{
                      padding: "8px 12px", borderRadius: 8, cursor: "pointer",
                      background: activeFolder === f ? "#EEF2FF" : "transparent",
                      color: activeFolder === f ? "#4F46E5" : "#475569",
                      fontWeight: activeFolder === f ? 600 : 400, fontSize: 13,
                    }}
                  >
                    📄 {f} ({count})
                  </div>
                );
              })}
            </div>
          </Card>

          <Card style={{ borderRadius: 16 }} styles={{ body: { padding: 8 } }} loading={loading}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 500, overflow: "auto" }}>
              {filteredDocs.map((doc) => (
                <div
                  key={doc.id}
                  onClick={() => { setActiveDoc(doc); setEditContent(doc.content); setEditing(false); }}
                  style={{
                    padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                    background: activeDoc?.id === doc.id ? "#F1F5F9" : "transparent",
                    transition: "all 0.15s",
                    borderLeft: activeDoc?.id === doc.id ? "3px solid #4F46E5" : "3px solid transparent",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = activeDoc?.id === doc.id ? "#F1F5F9" : "#F8FAFC"}
                  onMouseLeave={(e) => e.currentTarget.style.background = activeDoc?.id === doc.id ? "#F1F5F9" : "transparent"}
                >
                  <Text strong style={{ fontSize: 13, display: "block" }}>{doc.title}</Text>
                  <div style={{ display: "flex", gap: 6, marginTop: 4, alignItems: "center" }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{doc.updatedAt}</Text>
                    <Tag style={{ fontSize: 9, borderRadius: 4, lineHeight: "16px" }}>{doc.folder}</Tag>
                  </div>
                </div>
              ))}
              {filteredDocs.length === 0 && (
                <div style={{ padding: 24, textAlign: "center" }}>
                  <Text type="secondary">无匹配文档</Text>
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* 文档编辑器 */}
        <div style={{ flex: 1 }}>
          {activeDoc ? (
            <Card style={{ borderRadius: 16, minHeight: 500 }} className="card-hover" styles={{ body: { padding: 24 } }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <Input
                  variant="borderless"
                  value={activeDoc.title}
                  onChange={(e) => {
                    setDocs((prev) => prev.map((d) => d.id === activeDoc.id ? { ...d, title: e.target.value } : d));
                    setActiveDoc({ ...activeDoc, title: e.target.value });
                  }}
                  style={{ fontSize: 22, fontWeight: 700, padding: 0, color: "#0F172A" }}
                />
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <UserOutlined /> {activeDoc.author} · {activeDoc.updatedAt}
                  </Text>
                  <Button
                    type={editing ? "primary" : "default"}
                    icon={<EditOutlined />}
                    onClick={() => editing ? handleSave() : (setEditContent(activeDoc.content), setEditing(true))}
                  >
                    {editing ? "保存" : "编辑"}
                  </Button>
                  <Popconfirm
                    title="确认删除该文档？"
                    description="删除后不可恢复。"
                    okText="删除"
                    okType="danger"
                    cancelText="取消"
                    onConfirm={() => handleDeleteDoc(activeDoc.id)}
                  >
                    <Button danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              </div>
              <Divider style={{ margin: "0 0 16px" }} />

              {editing ? (
                <TextArea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  style={{
                    minHeight: 400, border: "1px solid #E2E8F0", borderRadius: 12,
                    padding: 16, fontSize: 14, lineHeight: 1.7, fontFamily: "'Inter', monospace",
                    resize: "vertical",
                  }}
                />
              ) : (
                <div
                  style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, fontSize: 14, color: "#334155", minHeight: 400 }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdownToHtml(activeDoc.content) }}
                />
              )}
            </Card>
          ) : (
            <div className="enhanced-empty">
              <FileTextOutlined style={{ fontSize: 48, color: "#CBD5E1" }} />
              <h3>选择一个文档</h3>
              <p>或创建一个新文档开始写作</p>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleNewDoc}>新建文档</Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Documents;
