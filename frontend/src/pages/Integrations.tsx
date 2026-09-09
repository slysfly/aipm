import React, { useEffect, useState, useCallback } from "react";
import {
  Card, Tag, Button, App, Spin, Row, Col, Modal, Form, Input, Select,
  Switch, Table, Typography, Space, Tabs, Alert, Descriptions, Statistic,
  Badge, List, Avatar, Segmented, Collapse, Popconfirm, Divider, Steps,
  message as antMessage, Empty,
} from "antd";
import {
  DingtalkOutlined, WechatOutlined, SlackOutlined, ApiOutlined,
  LinkOutlined, PlusOutlined, SettingOutlined, UserOutlined,
  SafetyCertificateOutlined, WarningOutlined, DisconnectOutlined,
  SendOutlined, HistoryOutlined, DashboardOutlined, KeyOutlined,
  ExclamationCircleOutlined, BulbOutlined, RobotOutlined, ReloadOutlined,
} from "@ant-design/icons";
import { imGatewayApi, authApi } from "../api";

const { Title, Paragraph, Text } = Typography;

const PLATFORMS: Record<string, { name: string; icon: React.ReactNode; color: string; desc: string }> = {
  dingtalk: { name: "钉钉", icon: <DingtalkOutlined />, color: "#0089FF", desc: "机器人 / Webhook / 消息卡片" },
  feishu: { name: "飞书", icon: <WechatOutlined />, color: "#3370FF", desc: "机器人 / 事件订阅 / 消息卡片" },
  wecom: { name: "企业微信", icon: <WechatOutlined />, color: "#2DC100", desc: "回调模式 / 应用消息" },
  slack: { name: "Slack", icon: <SlackOutlined />, color: "#4A154B", desc: "Bot / Slash Commands" },
};

const IntegrationsPage: React.FC = () => {
  const { message, modal } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");
  const [providers, setProviders] = useState<any[]>([]);
  const [bindings, setBindings] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [configProvider, setConfigProvider] = useState("");
  const [bindingModalOpen, setBindingModalOpen] = useState(false);
  const [bindingProvider, setBindingProvider] = useState("");
  const [configForm] = Form.useForm();
  const [bindingForm] = Form.useForm();

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [provRes, bindRes, statsRes, userRes] = await Promise.all([
        imGatewayApi.listProviders().catch(() => ({ items: [] })),
        imGatewayApi.listBindings().catch(() => ({ items: [] })),
        imGatewayApi.getStats().catch(() => null),
        authApi.listUsers().catch(() => []),
      ]);
      setProviders(provRes?.items || []);
      setBindings(bindRes?.items || []);
      setStats(statsRes);
      setUsers(userRes?.items || []);
    } catch (e) { console.error("加载失败:", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  /* 平台配置 */
  const openConfigModal = (provider?: string) => {
    setConfigProvider(provider || "");
    configForm.resetFields();
    setConfigModalOpen(true);
  };
  const handleSaveConfig = async () => {
    const v = await configForm.validateFields().catch(() => null);
    if (!v) return;
    try {
      if (providers.find((p: any) => p.provider === configProvider)) {
        await imGatewayApi.updateProvider(configProvider, v);
      } else {
        await imGatewayApi.createProvider({ ...v, provider: configProvider });
      }
      message.success("保存成功");
      setConfigModalOpen(false);
      loadAll();
    } catch (e: any) { message.error(e?.response?.data?.detail || "失败"); }
  };

  /* 用户绑定 */
  const openBindingModal = (provider: string) => {
    setBindingProvider(provider);
    bindingForm.resetFields();
    bindingForm.setFieldsValue({ provider });
    setBindingModalOpen(true);
  };
  const handleCreateBinding = async () => {
    const v = await bindingForm.validateFields().catch(() => null);
    if (!v) return;
    try {
      await imGatewayApi.createBinding(v);
      message.success("绑定成功");
      setBindingModalOpen(false);
      loadAll();
    } catch (e: any) { message.error(e?.response?.data?.detail || "失败"); }
  };
  const handleRemoveBinding = async (id: string) => {
    try {
      await imGatewayApi.removeBinding(id);
      message.success("已解绑");
      loadAll();
    } catch (e: any) { message.error(e?.response?.data?.detail || "失败"); }
  };

  /* 审计日志 */
  useEffect(() => {
    if (activeTab === "logs") {
      imGatewayApi.listAuditLogs({ page_size: 50 }).then((r: any) => setAuditLogs(r?.items || [])).catch(() => {});
    }
  }, [activeTab]);

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;

  /* ===== Tab 渲染函数 ===== */

  const renderOverview = () => (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="已配置平台" value={stats?.configuredPlatforms || 0} prefix={<ApiOutlined />} suffix="/4" /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="活跃绑定" value={stats?.myBindings || 0} prefix={<LinkOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="今日消息" value={stats?.todayMessages || 0} prefix={<SendOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="今日冲突" value={stats?.todayConflicts || 0}
            valueStyle={{ color: (stats?.todayConflicts || 0) > 0 ? "#cf1322" : "#3f8600" }}
            prefix={<WarningOutlined />} />
          </Card>
        </Col>
      </Row>

      <Title level={4}>平台接入状态</Title>
      <Row gutter={[16, 16]}>
        {Object.entries(PLATFORMS).map(([key, plat]) => {
          const cfg = providers.find((p: any) => p.provider === key);
          const myBind = bindings.find((b: any) => b.provider === key);
          return (
            <Col xs={24} md={12} key={key}>
              <Card
                title={<Space>{plat.icon} <Text strong>{plat.name}</Text></Space>}
                extra={<Tag color={cfg?.enabled ? "green" : cfg ? "default" : "orange"}>{cfg?.enabled ? "已启用" : cfg ? "已配置未启用" : "未配置"}</Tag>}
                actions={[
                  !cfg && <Button type="primary" size="small" icon={<KeyOutlined />} onClick={() => { setConfigProvider(key); setConfigModalOpen(true); }}>配置</Button>,
                  cfg && <Button size="small" icon={<SettingOutlined />} onClick={() => openConfigModal(key)}>设置</Button>,
                  myBind
                    ? <Button size="small" danger icon={<DisconnectOutlined />} onClick={() => handleRemoveBinding(myBind.id)}>解绑</Button>
                    : cfg ? <Button size="small" type="primary" icon={<UserOutlined />} onClick={() => openBindingModal(key)}>绑定账号</Button> : undefined,
                ].filter(Boolean)}
              >
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="能力描述">{plat.desc}</Descriptions.Item>
                  <Descriptions.Item label="App ID">{cfg?.config?.appId || "—"}</Descriptions.Item>
                  <Descriptions.Item label="我的IM账号">
                    {myBind ? <Space><Badge status="success" />{myBind.imUserName || myBind.imUserId}</Space> : <Text type="secondary">未绑定</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label="Webhook地址">
                    {cfg ? <Text copyable={{ text: `${window.location.origin}/api/v1/im-gateway/webhook/${key}` }}>{`/api/v1/im-gateway/webhook/${key}`}</Text> : "—"}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          );
        })}
      </Row>

      <Divider />
      <Alert type="info" showIcon icon={<BulbOutlined />} message="使用指南"
        description={
          <div>
            <p>1. 点击各平台的「配置」按钮，填写 App ID 和 App Secret（从对应开放平台获取）</p>
            <p>2. 配置完成后，点击「绑定账号」将你的 IM 账号与 AIPM 系统关联</p>
            <p>3. 将 Webhook 地址填入对应平台的机器人/应用回调设置中</p>
            <p>4. 之后就可以在钉钉/飞书/企微中直接与 AI-PM 助手对话了！</p>
          </div>
        }
      />
    </div>
  );

  const renderBindings = () => (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Title level={4} style={{ margin: 0 }}>我的 IM 账号绑定</Title>
        <Segmented options={Object.entries(PLATFORMS).map(([k, v]) => ({ label: v.name, value: k }))} onChange={(v) => v && openBindingModal(v as string)} />
      </div>
      {bindings.length === 0
        ? <Empty description="尚未绑定任何 IM 账号。请在上方选择平台进行绑定。" />
        : <List
            dataSource={bindings}
            renderItem={(item: any) => {
              const plat = PLATFORMS[item.provider as keyof typeof PLATFORMS];
              return (
                <List.Item actions={[
                  <Popconfirm title="确认解绑？" onConfirm={() => handleRemoveBinding(item.id)}>
                    <Button size="small" danger icon={<DisconnectOutlined />}>解绑</Button>
                  </Popconfirm>,
                ]}>
                  <List.Item.Meta
                    avatar={<Avatar style={{ backgroundColor: plat?.color || "#1890ff" }}>{plat?.icon}</Avatar>}
                    title={<Space><Text strong>{plat?.name || item.provider}</Text><Tag color={item.status === "active" ? "green" : "default"}>{item.status === "active" ? "活跃" : item.status}</Tag></Space>}
                    description={<Space split={<Divider type="vertical" />}><span>IM用户: {item.imUserName || item.imUserId}</span>{item.defaultProjectId && <span>默认项目: {item.defaultProjectId}</span>}<span>绑定时间: {item.boundAt ? new Date(item.boundAt).toLocaleDateString() : "—"}</span></Space>}
                  />
                </List.Item>
              );
            }}
          />}
    </div>
  );

  const renderAuditLogs = () => (
    <div>
      <Title level={4}>操作审计日志</Title>
      <Table
        dataSource={auditLogs} rowKey="id" size="middle" pagination={{ pageSize: 20 }} scroll={{ x: 900 }}
        columns={[
          { title: "时间", dataIndex: "createdAt", width: 160, render: (t: string) => t ? new Date(t).toLocaleString() : "—" },
          { title: "平台", dataIndex: "provider", width: 80, render: (p: string) => { const plat = PLATFORMS[p as keyof typeof PLATFORMS]; return plat ? <Tag color={plat.color}>{plat.name}</Tag> : p; }},
          { title: "操作类型", dataIndex: "actionType", width: 100 },
          { title: "分类", dataIndex: "actionCategory", width: 80, render: (c: string) => { const m: Record<string, { color: string; label: string }> = { query: { color: "blue", label: "查询" }, create: { color: "green", label: "创建" }, update: { color: "orange", label: "更新" }, delete: { color: "red", label: "删除" }, system: { color: "default", label: "系统" } }; const x = m[c] || { color: "default", label: c }; return <Tag color={x.color}>{x.label}</Tag>; }},
          { title: "原始输入", dataIndex: "rawInput", ellipsis: true, render: (t: string) => t || "—" },
          { title: "结果", dataIndex: "resultStatus", width: 80, render: (s: string) => { const m: Record<string, { color: string; label: string }> = { success: { color: "success", label: "成功" }, error: { color: "error", label: "错误" }, conflict: { color: "warning", label: "冲突" }, blocked: { color: "default", label: "拦截" } }; const x = m[s] || { color: "default", label: s }; return <Tag color={x.color}>{x.label}</Tag>; }},
          { title: "耗时(ms)", dataIndex: "totalMs", width: 90, render: (v: number) => v ? Math.round(v) : "—" },
          { title: "来源IP", dataIndex: "sourceIp", width: 130 },
        ]}
      />
    </div>
  );

  const renderHelp = () => (
    <div>
      <Title level={4}>多平台接入 — 完整使用指南</Title>
      <Collapse defaultActiveKey={["arch"]} items={[
        { key: "arch", label: "架构设计原理", children: (
          <div>
            <Paragraph><Text strong>核心原则：用户隔离 + 全能力 + 冲突检测 + 审计追踪</Text></Paragraph>
            <Steps direction="vertical" current={-1} size="small" items={[
              { title: "平台配置", description: "管理员填写 App ID / Secret，启用平台能力" },
              { title: "用户绑定", description: "每个用户独立绑定自己的 IM 账号，数据严格隔离不串台" },
              { title: "消息入站", description: "IM 消息通过 Webhook 回调到系统，自动识别发送者身份" },
              { title: "AI 解析执行", description: "AI 理解自然语言意图，执行查询/创建/更新/删除等操作" },
              { title: "冲突检测", description: "自动检测并发编辑、资源分配等冲突并实时提示" },
              { title: "审计记录", description: "所有行为完整记录，含操作类型、内容、结果、耗时、IP" },
            ]} />
          </div>
        )},
        { key: "dingtalk", label: <Space><DingtalkOutlined /> 钉钉接入指南</Space>, children: (
          <div>
            <Title level={5}>1. 创建钉钉应用</Title>
            <ol><li>登录钉钉开放平台</li><li>创建企业内部应用或第三方应用</li><li>获取 AppKey 和 AppSecret</li></ol>
            <Title level={5}>2. 配置机器人</Title>
            <ol><li>在应用的机器人功能页添加机器人</li><li>设置消息接收地址为 Webhook URL</li><li>在本页面填入 AppKey 和 AppSecret</li></ol>
            <Title level={5}>3. 绑定账号</Title>
            <ol><li>在钉钉中给机器人发一条消息</li><li>在本页面绑定你的钉钉 UserID</li></ol>
          </div>
        )},
        { key: "feishu", label: <Space><WechatOutlined /> 飞书接入指南</Space>, children: (
          <div>
            <Title level={5}>1. 创建飞书应用</Title>
            <ol><li>登录飞书开放平台</li><li>创建企业自建应用</li><li>获取 App ID 和 App Secret</li></ol>
            <Title level={5}>2. 开启机器人能力</Title>
            <ol><li>应用功能 - 机器人 - 开启</li><li>事件订阅 - 添加接收消息事件</li><li>填入 Webhook URL</li></ol>
          </div>
        )},
        { key: "security", label: <Space><SafetyCertificateOutlined /> 安全机制说明</Space>, children: (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="用户隔离">每个用户的 IM 账号独立绑定，数据严格隔离不串台</Descriptions.Item>
            <Descriptions.Item label="签名校验">所有平台 Webhook 回调均支持 HMAC 签名验证</Descriptions.Item>
            <Descriptions.Item label="冲突检测">自动检测并发编辑冲突、资源分配冲突，实时提示</Descriptions.Item>
            <Descriptions.Item label="审计追踪">所有 IM 操作完整记录：谁、何时、通过哪个平台、执行了什么</Descriptions.Item>
            <Descriptions.Item label="操作权限">遵循 AIPM 原有权限体系</Descriptions.Item>
            <Descriptions.Item label="AI 安全边界">高风险操作时主动要求二次确认</Descriptions.Item>
          </Descriptions>
        )},
      ]} />
    </div>
  );

  /* ===== 主渲染 ===== */
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}><RobotOutlined /> 多平台智能接入网关</Title>
        <Button type="link" icon={<ReloadOutlined spin={loading} />} onClick={loadAll}>刷新</Button>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key: "overview", label: "概览总览", children: renderOverview() },
        { key: "bindings", label: "我的绑定", children: renderBindings() },
        { key: "logs", label: "审计日志", children: renderAuditLogs() },
        { key: "help", label: "使用指南", children: renderHelp() },
      ]} />

      {/* 平台配置弹窗 */}
      <Modal title={`配置 ${configProvider ? PLATFORMS[configProvider as keyof typeof PLATFORMS]?.name || configProvider : "平台"}`}
        open={configModalOpen} onOk={handleSaveConfig} onCancel={() => setConfigModalOpen(false)} okText="保存配置" width={520} destroyOnClose>
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="凭证安全" description="App Secret 将被加密存储，仅展示脱敏信息。" />
        <Form form={configForm} layout="vertical">
          <Form.Item name="app_id" label="App ID / AppKey" rules={[{ required: true }]}>
            <Input placeholder="App ID 或 AppKey" />
          </Form.Item>
          <Form.Item name="app_secret" label="App Secret" rules={[{ required: true }]}>
            <Input.Password placeholder="App Secret" />
          </Form.Item>
          <Form.Item name="verification_token" label="Token"><Input placeholder="可选：签名验证 Token" /></Form.Item>
          <Form.Item name="encrypt_key" label="Encrypt Key"><Input.Password placeholder="可选：加解密密钥" /></Form.Item>
          <Form.Item name="capabilities" label="启用能力">
            <Select mode="multiple" defaultValue={["chat", "command"]} options={[
              { value: "chat", label: "对话" }, { value: "command", label: "指令执行" },
              { value: "notification", label: "通知推送" },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 用户绑定弹窗 */}
      <Modal title={`绑定 ${bindingProvider ? PLATFORMS[bindingProvider as keyof typeof PLATFORMS]?.name || bindingProvider : bindingProvider} 账号`}
        open={bindingModalOpen} onOk={handleCreateBinding} onCancel={() => setBindingModalOpen(false)} okText="确认绑定" width={480} destroyOnClose>
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message="用户隔离原则" description="每个 IM 账号只能绑定一个 AIPM 用户，数据严格隔离。" />
        <Form form={bindingForm} layout="vertical">
          <Form.Item name="provider" hidden><Input /></Form.Item>
          <Form.Item name="im_user_id" label="IM 用户ID" rules={[{ required: true }]}>
            <Input placeholder="钉钉UserID / 飞书OpenID / 企业微信UserID" />
          </Form.Item>
          <Form.Item name="im_user_name" label="昵称"><Input placeholder="显示名称" /></Form.Item>
          <Form.Item name="im_tenant_id" label="租户ID"><Input placeholder="企业ID/团队ID（如有）" /></Form.Item>
          <Form.Item name="default_project_id" label="默认项目"><Input placeholder="默认关联的项目 ID" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default IntegrationsPage;
