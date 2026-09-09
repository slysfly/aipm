import React, { useState, useEffect } from "react";
import { FloatButton, Drawer, Input, Button, List, Avatar, Spin, Tag, Select, Space, Empty } from "antd";
import { RobotOutlined, SendOutlined, ProjectOutlined } from "@ant-design/icons";
import { post } from "../api/http";
import { projectApi } from "../api";
import DOMPurify from "dompurify";

interface Msg {
  role: "user" | "ai";
  content: string;
}

/**
 * 轻量 Markdown → HTML 并用 DOMPurify 消毒，避免 AI 回复中的脚本被当作 HTML 执行。
 * 覆盖标题 / 加粗 / 行内代码 / 列表 / 换行，满足助手回复的常见排版。
 */
const renderMarkdown = (content: string): string => {
  const raw = content
    .replace(/^### (.+)$/gm, '<h4 style="margin:12px 0 6px;font-size:14px;font-weight:600">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 style="margin:14px 0 6px;font-size:15px;font-weight:700">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 style="margin:16px 0 8px;font-size:16px;font-weight:700">$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, '<code style="background:#eef;padding:1px 4px;border-radius:3px">$1</code>')
    .replace(/^- (.+)$/gm, '<div style="padding-left:14px;line-height:1.7">• $1</div>')
    .replace(/\n/g, "<br/>");
  return DOMPurify.sanitize(raw);
};

const GlobalAssistant: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "ai", content: "你好，我是本系统的 **AI 项目经理**。选择一个项目后向我提问，我会**先分析该项目的全部数据**（任务、风险、里程碑、进度、预算等），再基于真实数据给出答案；也可以直接问通用项目管理问题。" },
  ]);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!open) return;
    projectApi.list({ page_size: 100 }).then((r: any) => setProjects(r?.items || [])).catch(() => {});
  }, [open]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const res = await post("/openclaw/assistant/chat", {
        message: text,
        project_id: projectId,
        context: { source: "global_assistant", project_id: projectId },
      });
      setMsgs((m) => [...m, { role: "ai", content: res.message || "（无回复）" }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "ai", content: "调用失败：" + (e?.response?.data?.detail || e?.message || "未知错误") }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <FloatButton
        icon={<RobotOutlined />}
        type="primary"
        tooltip="AI 项目经理"
        onClick={() => setOpen(true)}
        style={{ insetInlineEnd: 24, insetBlockEnd: 88 }}
      />
      <Drawer
        title={<span><RobotOutlined /> AI 项目经理</span>}
        placement="right"
        width={400}
        open={open}
        onClose={() => setOpen(false)}
        footer={
          <div style={{ display: "flex", gap: 8 }}>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={send}
              placeholder={projectId ? "已选该项目，AI 会先分析其全部数据再回答…" : "输入问题，让 AI 协助..."}
              disabled={loading}
            />
            <Button type="primary" icon={<SendOutlined />} loading={loading} onClick={send}>发送</Button>
          </div>
        }
      >
        <Space style={{ marginBottom: 12, width: "100%" }}>
          <ProjectOutlined />
          <Select
            allowClear
            placeholder="选择项目上下文（可选）"
            style={{ flex: 1 }}
            value={projectId}
            onChange={(v) => setProjectId(v)}
            options={projects.map((p: any) => ({ label: p.name, value: p.id }))}
          />
        </Space>
        <List
          dataSource={msgs}
          renderItem={(m) => (
            <List.Item style={{ display: "block" }}>
              <div style={{ display: "flex", gap: 8, justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
                {m.role === "ai" && <Avatar icon={<RobotOutlined />} style={{ background: "linear-gradient(135deg,#F97316,#EF4444)" }} />}
                <div
                  style={{
                    maxWidth: "80%",
                    padding: "10px 12px",
                    borderRadius: 10,
                    background: m.role === "user" ? "linear-gradient(135deg,#F97316,#EF4444)" : "#f7f8fa",
                    color: m.role === "user" ? "#fff" : "#1f2329",
                    fontSize: 13,
                    lineHeight: 1.7,
                  }}
                  dangerouslySetInnerHTML={{
                    __html:
                      m.role === "ai"
                        ? renderMarkdown(m.content)
                        : DOMPurify.sanitize(m.content),
                  }}
                />
              </div>
            </List.Item>
          )}
        />
        {loading && <div style={{ textAlign: "center", padding: 8 }}><Spin size="small" /></div>}
        {msgs.length === 1 && projects.length === 0 && (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="可选定项目后向我提问" />
        )}
        <div style={{ marginTop: 12 }}>
          <Tag color="orange">AI 项目经理</Tag>
          <Tag color={projectId ? "green" : "default"}>{projectId ? "已选项目 · 将先分析全量数据" : "结合项目上下文"}</Tag>
        </div>
      </Drawer>
    </>
  );
};

export default GlobalAssistant;
