import React, { useEffect, useState } from "react";
import {
  Card, Tabs, Table, Button, Modal, Input, App, Tag, Typography, Descriptions, Space,
} from "antd";
import { ApiOutlined, PlayCircleOutlined, FileTextOutlined } from "@ant-design/icons";
import { mcpApi } from "../api";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const MCP: React.FC = () => {
  const { message } = App.useApp();
  const [status, setStatus] = useState<any>(null);
  const [tools, setTools] = useState<any[]>([]);
  const [resources, setResources] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [toolModal, setToolModal] = useState<{ open: boolean; tool: any | null }>({ open: false, tool: null });
  const [paramsText, setParamsText] = useState("{}");
  const [calling, setCalling] = useState(false);
  const [callResult, setCallResult] = useState<string>("");
  const [resourceContent, setResourceContent] = useState<string>("");
  const [resModal, setResModal] = useState<{ open: boolean; uri: string }>({ open: false, uri: "" });

  const load = async () => {
    setLoading(true);
    try {
      const s = await mcpApi.status();
      setStatus(s);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载 MCP 状态失败");
    }
    try {
      const tl = await mcpApi.listTools();
      const t = tl?.result?.tools || tl?.tools || [];
      setTools(Array.isArray(t) ? t : []);
    } catch (e: any) {
      setTools([]);
    }
    try {
      const rl = await mcpApi.listResources();
      const r = rl?.result?.resources || rl?.resources || [];
      setResources(Array.isArray(r) ? r : []);
    } catch (e: any) {
      setResources([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openTool = (tool: any) => {
    setToolModal({ open: true, tool });
    setParamsText("{}");
    setCallResult("");
  };

  const callTool = async () => {
    if (!toolModal.tool) return;
    let args: any = {};
    try {
      args = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch (e) {
      message.error("参数不是合法 JSON");
      return;
    }
    setCalling(true);
    try {
      const res = await mcpApi.callTool(toolModal.tool.name, args);
      const content = res?.result?.content || res?.content || [];
      const text = (Array.isArray(content) ? content : [])
        .map((c: any) => c?.text ?? c?.data ?? JSON.stringify(c))
        .join("\n");
      setCallResult(text || "(无返回内容)");
    } catch (e: any) {
      const detail = e?.response?.data?.detail || String(e);
      message.error(detail);
      setCallResult(String(detail));
    } finally {
      setCalling(false);
    }
  };

  const readResource = async (uri: string) => {
    setResModal({ open: true, uri });
    setResourceContent("");
    try {
      const res = await mcpApi.readResource(uri);
      const content = res?.result?.contents || res?.contents || res?.result?.content || [];
      const text = (Array.isArray(content) ? content : [])
        .map((c: any) => c?.text ?? c?.data ?? JSON.stringify(c))
        .join("\n");
      setResourceContent(text || "(空)");
    } catch (e: any) {
      setResourceContent(String(e?.response?.data?.detail || e));
    }
  };

  const toolColumns = [
    { title: "名称", dataIndex: "name", render: (n: string) => <Tag color="blue">{n}</Tag> },
    { title: "描述", dataIndex: "description", ellipsis: true },
    {
      title: "操作",
      render: (_: any, r: any) => (
        <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => openTool(r)}>
          调用
        </Button>
      ),
    },
  ];

  const resourceColumns = [
    { title: "URI", dataIndex: "uri", ellipsis: true, render: (u: string) => <Text code>{u}</Text> },
    { title: "名称", dataIndex: "name" },
    {
      title: "操作",
      render: (_: any, r: any) => (
        <Button size="small" icon={<FileTextOutlined />} onClick={() => readResource(r.uri)}>
          读取
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>MCP 协议服务</h2>
        <Button onClick={load}>刷新</Button>
      </div>
      <Text type="secondary">
        Model Context Protocol 服务，暴露工具（Tools）与资源（Resources），可被外部 MCP 客户端或本页直接调用，所有操作基于真实数据库。
      </Text>

      <Card style={{ marginTop: 12 }} loading={loading}>
        {status && (
          <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="状态">{status?.status || status?.server_status || "unknown"}</Descriptions.Item>
            <Descriptions.Item label="版本">{status?.version || status?.server_version || "-"}</Descriptions.Item>
            <Descriptions.Item label="工具数">{tools.length}</Descriptions.Item>
            <Descriptions.Item label="资源数">{resources.length}</Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Tabs
        style={{ marginTop: 12 }}
        items={[
          {
            key: "tools",
            label: (
              <span>
                <ApiOutlined /> 工具 ({tools.length})
              </span>
            ),
            children: <Table rowKey="name" columns={toolColumns} dataSource={tools} pagination={false} />,
          },
          {
            key: "resources",
            label: (
              <span>
                <FileTextOutlined /> 资源 ({resources.length})
              </span>
            ),
            children: <Table rowKey="uri" columns={resourceColumns} dataSource={resources} pagination={false} />,
          },
        ]}
      />

      <Modal
        title={`调用工具: ${toolModal.tool?.name || ""}`}
        open={toolModal.open}
        onOk={callTool}
        confirmLoading={calling}
        onCancel={() => setToolModal({ open: false, tool: null })}
        width={640}
        destroyOnClose
      >
        <p>参数 (JSON)：</p>
        <TextArea
          rows={6}
          value={paramsText}
          onChange={(e) => setParamsText(e.target.value)}
          placeholder='{"key": "value"}'
        />
        {callResult && (
          <div style={{ marginTop: 12 }}>
            <p>返回结果：</p>
            <Paragraph>
              <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6, maxHeight: 240, overflow: "auto" }}>
                {callResult}
              </pre>
            </Paragraph>
          </div>
        )}
      </Modal>

      <Modal
        title={`资源内容: ${resModal.uri}`}
        open={resModal.open}
        footer={null}
        onCancel={() => setResModal({ open: false, uri: "" })}
        width={640}
      >
        <Paragraph>
          <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6, maxHeight: 360, overflow: "auto" }}>
            {resourceContent}
          </pre>
        </Paragraph>
      </Modal>
    </div>
  );
};

export default MCP;
