import React, { useEffect, useState, useCallback, useMemo } from "react";
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
import { useTranslation } from "react-i18next";

const { Title, Paragraph, Text } = Typography;

const IntegrationsPage: React.FC = () => {
  const { t } = useTranslation("integrations");
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

  const PLATFORMS: Record<string, { name: string; icon: React.ReactNode; color: string; desc: string }> = useMemo(() => ({
    dingtalk: { name: t("platforms.dingtalk"), icon: <DingtalkOutlined />, color: "#0089FF", desc: t("platforms.dingtalkDesc") },
    feishu: { name: t("platforms.feishu"), icon: <WechatOutlined />, color: "#3370FF", desc: t("platforms.feishuDesc") },
    wecom: { name: t("platforms.wecom"), icon: <WechatOutlined />, color: "#2DC100", desc: t("platforms.wecomDesc") },
    slack: { name: t("platforms.slack"), icon: <SlackOutlined />, color: "#4A154B", desc: t("platforms.slackDesc") },
  }), [t]);

  const CATEGORY_MAP: Record<string, { color: string; label: string }> = useMemo(() => ({
    query: { color: "blue", label: t("categories.query") },
    create: { color: "green", label: t("categories.create") },
    update: { color: "orange", label: t("categories.update") },
    delete: { color: "red", label: t("categories.delete") },
    system: { color: "default", label: t("categories.system") },
  }), [t]);

  const RESULT_MAP: Record<string, { color: string; label: string }> = useMemo(() => ({
    success: { color: "success", label: t("results.success") },
    error: { color: "error", label: t("results.error") },
    conflict: { color: "warning", label: t("results.conflict") },
    blocked: { color: "default", label: t("results.blocked") },
  }), [t]);

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
    } catch (e) { console.error(t("messages.loadErrorLog"), e); }
    finally { setLoading(false); }
  }, [t]);

  useEffect(() => { loadAll(); }, [loadAll]);

  /* \u5e73\u53f0\u914d\u7f6e */
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
      message.success(t("messages.saveSuccess"));
      setConfigModalOpen(false);
      loadAll();
    } catch (e: any) { message.error(e?.response?.data?.detail || t("messages.failed")); }
  };

  /* \u7528\u6237\u7ed1\u5b9a */
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
      message.success(t("messages.bindSuccess"));
      setBindingModalOpen(false);
      loadAll();
    } catch (e: any) { message.error(e?.response?.data?.detail || t("messages.failed")); }
  };
  const handleRemoveBinding = async (id: string) => {
    try {
      await imGatewayApi.removeBinding(id);
      message.success(t("messages.unbindSuccess"));
      loadAll();
    } catch (e: any) { message.error(e?.response?.data?.detail || t("messages.failed")); }
  };

  /* \u5ba1\u8ba1\u65e5\u5fd7 */
  useEffect(() => {
    if (activeTab === "logs") {
      imGatewayApi.listAuditLogs({ page_size: 50 }).then((r: any) => setAuditLogs(r?.items || [])).catch(() => {});
    }
  }, [activeTab]);

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;

  /* ===== Tab \u6e32\u67d3\u51fd\u6570 ===== */

  const renderOverview = () => (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title={t("overview.configuredPlatforms")} value={stats?.configuredPlatforms || 0} prefix={<ApiOutlined />} suffix="/4" /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title={t("overview.activeBindings")} value={stats?.myBindings || 0} prefix={<LinkOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title={t("overview.todayMessages")} value={stats?.todayMessages || 0} prefix={<SendOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title={t("overview.todayConflicts")} value={stats?.todayConflicts || 0}
            valueStyle={{ color: (stats?.todayConflicts || 0) > 0 ? "#cf1322" : "#3f8600" }}
            prefix={<WarningOutlined />} />
          </Card>
        </Col>
      </Row>

      <Title level={4}>{t("overview.platformStatus")}</Title>
      <Row gutter={[16, 16]}>
        {Object.entries(PLATFORMS).map(([key, plat]) => {
          const cfg = providers.find((p: any) => p.provider === key);
          const myBind = bindings.find((b: any) => b.provider === key);
          return (
            <Col xs={24} md={12} key={key}>
              <Card
                title={<Space>{plat.icon} <Text strong>{plat.name}</Text></Space>}
                extra={<Tag color={cfg?.enabled ? "green" : cfg ? "default" : "orange"}>{cfg?.enabled ? t("status.enabled") : cfg ? t("status.configuredButDisabled") : t("status.notConfigured")}</Tag>}
                actions={[
                  !cfg && <Button type="primary" size="small" icon={<KeyOutlined />} onClick={() => { setConfigProvider(key); setConfigModalOpen(true); }}>{t("actions.configure")}</Button>,
                  cfg && <Button size="small" icon={<SettingOutlined />} onClick={() => openConfigModal(key)}>{t("actions.settings")}</Button>,
                  myBind
                    ? <Button size="small" danger icon={<DisconnectOutlined />} onClick={() => handleRemoveBinding(myBind.id)}>{t("actions.unbind")}</Button>
                    : cfg ? <Button size="small" type="primary" icon={<UserOutlined />} onClick={() => openBindingModal(key)}>{t("actions.bindAccount")}</Button> : undefined,
                ].filter(Boolean)}
              >
                <Descriptions column={1} size="small">
                  <Descriptions.Item label={t("overview.capabilityDesc")}>{plat.desc}</Descriptions.Item>
                  <Descriptions.Item label={t("overview.appId")}>{cfg?.config?.appId || "—"}</Descriptions.Item>
                  <Descriptions.Item label={t("overview.myImAccount")}>
                    {myBind ? <Space><Badge status="success" />{myBind.imUserName || myBind.imUserId}</Space> : <Text type="secondary">{t("status.notBound")}</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label={t("overview.webhookUrl")}>
                    {cfg ? <Text copyable={{ text: `${window.location.origin}/api/v1/im-gateway/webhook/${key}` }}>{`/api/v1/im-gateway/webhook/${key}`}</Text> : "—"}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          );
        })}
      </Row>

      <Divider />
      <Alert type="info" showIcon icon={<BulbOutlined />} message={t("guide.title")}
        description={
          <div>
            <p>{t("guide.step1")}</p>
            <p>{t("guide.step2")}</p>
            <p>{t("guide.step3")}</p>
            <p>{t("guide.step4")}</p>
          </div>
        }
      />
    </div>
  );

  const renderBindings = () => (
    <div>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Title level={4} style={{ margin: 0 }}>{t("bindings.title")}</Title>
        <Segmented options={Object.entries(PLATFORMS).map(([k, v]) => ({ label: v.name, value: k }))} onChange={(v) => v && openBindingModal(v as string)} />
      </div>
      {bindings.length === 0
        ? <Empty description={t("bindings.empty")} />
        : <List
            dataSource={bindings}
            renderItem={(item: any) => {
              const plat = PLATFORMS[item.provider as keyof typeof PLATFORMS];
              return (
                <List.Item actions={[
                  <Popconfirm title={t("bindings.confirmUnbind")} onConfirm={() => handleRemoveBinding(item.id)}>
                    <Button size="small" danger icon={<DisconnectOutlined />}>{t("actions.unbind")}</Button>
                  </Popconfirm>,
                ]}>
                  <List.Item.Meta
                    avatar={<Avatar style={{ backgroundColor: plat?.color || "#1890ff" }}>{plat?.icon}</Avatar>}
                    title={<Space><Text strong>{plat?.name || item.provider}</Text><Tag color={item.status === "active" ? "green" : "default"}>{item.status === "active" ? t("bindings.active") : item.status}</Tag></Space>}
                    description={<Space split={<Divider type="vertical" />}><span>{t("bindings.imUser")}: {item.imUserName || item.imUserId}</span>{item.defaultProjectId && <span>{t("bindings.defaultProject")}: {item.defaultProjectId}</span>}<span>{t("bindings.boundAt")}: {item.boundAt ? new Date(item.boundAt).toLocaleDateString() : "—"}</span></Space>}
                  />
                </List.Item>
              );
            }}
          />}
    </div>
  );

  const renderAuditLogs = () => (
    <div>
      <Title level={4}>{t("audit.title")}</Title>
      <Table
        dataSource={auditLogs} rowKey="id" size="middle" pagination={{ pageSize: 20 }} scroll={{ x: 900 }}
        columns={[
          { title: t("audit.columns.time"), dataIndex: "createdAt", width: 160, render: (v: string) => v ? new Date(v).toLocaleString() : "—" },
          { title: t("audit.columns.platform"), dataIndex: "provider", width: 80, render: (p: string) => { const plat = PLATFORMS[p as keyof typeof PLATFORMS]; return plat ? <Tag color={plat.color}>{plat.name}</Tag> : p; }},
          { title: t("audit.columns.actionType"), dataIndex: "actionType", width: 100 },
          { title: t("audit.columns.category"), dataIndex: "actionCategory", width: 80, render: (c: string) => { const x = CATEGORY_MAP[c] || { color: "default", label: c }; return <Tag color={x.color}>{x.label}</Tag>; }},
          { title: t("audit.columns.rawInput"), dataIndex: "rawInput", ellipsis: true, render: (v: string) => v || "—" },
          { title: t("audit.columns.result"), dataIndex: "resultStatus", width: 80, render: (s: string) => { const x = RESULT_MAP[s] || { color: "default", label: s }; return <Tag color={x.color}>{x.label}</Tag>; }},
          { title: t("audit.columns.duration"), dataIndex: "totalMs", width: 90, render: (v: number) => v ? Math.round(v) : "—" },
          { title: t("audit.columns.sourceIp"), dataIndex: "sourceIp", width: 130 },
        ]}
      />
    </div>
  );

  const renderHelp = () => (
    <div>
      <Title level={4}>{t("help.title")}</Title>
      <Collapse defaultActiveKey={["arch"]} items={[
        { key: "arch", label: t("help.archTitle"), children: (
          <div>
            <Paragraph><Text strong>{t("help.corePrinciple")}</Text></Paragraph>
            <Steps direction="vertical" current={-1} size="small" items={[
              { title: t("help.steps.platformConfig"), description: t("help.steps.platformConfigDesc") },
              { title: t("help.steps.userBinding"), description: t("help.steps.userBindingDesc") },
              { title: t("help.steps.messageInbound"), description: t("help.steps.messageInboundDesc") },
              { title: t("help.steps.aiParse"), description: t("help.steps.aiParseDesc") },
              { title: t("help.steps.conflictDetect"), description: t("help.steps.conflictDetectDesc") },
              { title: t("help.steps.audit"), description: t("help.steps.auditDesc") },
            ]} />
          </div>
        )},
        { key: "dingtalk", label: <Space><DingtalkOutlined /> {t("help.dingtalkTitle")}</Space>, children: (
          <div>
            <Title level={5}>{t("help.dingtalkS1Title")}</Title>
            <ol>
              <li>{t("help.dingtalkS1L1")}</li>
              <li>{t("help.dingtalkS1L2")}</li>
              <li>{t("help.dingtalkS1L3")}</li>
            </ol>
            <Title level={5}>{t("help.dingtalkS2Title")}</Title>
            <ol>
              <li>{t("help.dingtalkS2L1")}</li>
              <li>{t("help.dingtalkS2L2")}</li>
              <li>{t("help.dingtalkS2L3")}</li>
            </ol>
            <Title level={5}>{t("help.dingtalkS3Title")}</Title>
            <ol>
              <li>{t("help.dingtalkS3L1")}</li>
              <li>{t("help.dingtalkS3L2")}</li>
            </ol>
          </div>
        )},
        { key: "feishu", label: <Space><WechatOutlined /> {t("help.feishuTitle")}</Space>, children: (
          <div>
            <Title level={5}>{t("help.feishuS1Title")}</Title>
            <ol>
              <li>{t("help.feishuS1L1")}</li>
              <li>{t("help.feishuS1L2")}</li>
              <li>{t("help.feishuS1L3")}</li>
            </ol>
            <Title level={5}>{t("help.feishuS2Title")}</Title>
            <ol>
              <li>{t("help.feishuS2L1")}</li>
              <li>{t("help.feishuS2L2")}</li>
              <li>{t("help.feishuS2L3")}</li>
            </ol>
          </div>
        )},
        { key: "security", label: <Space><SafetyCertificateOutlined /> {t("help.securityTitle")}</Space>, children: (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label={t("help.security.userIsolation")}>{t("help.security.userIsolationDesc")}</Descriptions.Item>
            <Descriptions.Item label={t("help.security.signatureVerify")}>{t("help.security.signatureVerifyDesc")}</Descriptions.Item>
            <Descriptions.Item label={t("help.security.conflictDetect")}>{t("help.security.conflictDetectDesc")}</Descriptions.Item>
            <Descriptions.Item label={t("help.security.auditTracking")}>{t("help.security.auditTrackingDesc")}</Descriptions.Item>
            <Descriptions.Item label={t("help.security.permission")}>{t("help.security.permissionDesc")}</Descriptions.Item>
            <Descriptions.Item label={t("help.security.aiSafety")}>{t("help.security.aiSafetyDesc")}</Descriptions.Item>
          </Descriptions>
        )},
      ]} />
    </div>
  );

  /* ===== \u4e3b\u6e32\u67d3 ===== */
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}><RobotOutlined /> {t("pageTitle")}</Title>
        <Button type="link" icon={<ReloadOutlined spin={loading} />} onClick={loadAll}>{t("actions.refresh")}</Button>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key: "overview", label: t("tabs.overview"), children: renderOverview() },
        { key: "bindings", label: t("tabs.bindings"), children: renderBindings() },
        { key: "logs", label: t("tabs.logs"), children: renderAuditLogs() },
        { key: "help", label: t("tabs.help"), children: renderHelp() },
      ]} />

      {/* Platform config modal */}
      <Modal title={t("configModal.title", { name: configProvider ? PLATFORMS[configProvider as keyof typeof PLATFORMS]?.name || configProvider : t("configModal.platformFallback") })}
        open={configModalOpen} onOk={handleSaveConfig} onCancel={() => setConfigModalOpen(false)} okText={t("configModal.okText")} width={520} destroyOnClose>
        <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={t("configModal.credentialAlert")} description={t("configModal.credentialDesc")} />
        <Form form={configForm} layout="vertical">
          <Form.Item name="app_id" label={t("configModal.appIdLabel")} rules={[{ required: true }]}>
            <Input placeholder={t("configModal.appIdPlaceholder")} />
          </Form.Item>
          <Form.Item name="app_secret" label={t("configModal.appSecretLabel")} rules={[{ required: true }]}>
            <Input.Password placeholder={t("configModal.appSecretPlaceholder")} />
          </Form.Item>
          <Form.Item name="verification_token" label={t("configModal.tokenLabel")}><Input placeholder={t("configModal.tokenPlaceholder")} /></Form.Item>
          <Form.Item name="encrypt_key" label={t("configModal.encryptKeyLabel")}><Input.Password placeholder={t("configModal.encryptKeyPlaceholder")} /></Form.Item>
          <Form.Item name="capabilities" label={t("configModal.capabilitiesLabel")}>
            <Select mode="multiple" defaultValue={["chat", "command"]} options={[
              { value: "chat", label: t("configModal.capabilities.chat") }, { value: "command", label: t("configModal.capabilities.command") },
              { value: "notification", label: t("configModal.capabilities.notification") },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* User binding modal */}
      <Modal title={t("bindingModal.title", { name: bindingProvider ? PLATFORMS[bindingProvider as keyof typeof PLATFORMS]?.name || bindingProvider : bindingProvider })}
        open={bindingModalOpen} onOk={handleCreateBinding} onCancel={() => setBindingModalOpen(false)} okText={t("bindingModal.okText")} width={480} destroyOnClose>
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t("bindingModal.isolationAlert")} description={t("bindingModal.isolationDesc")} />
        <Form form={bindingForm} layout="vertical">
          <Form.Item name="provider" hidden><Input /></Form.Item>
          <Form.Item name="im_user_id" label={t("bindingModal.imUserIdLabel")} rules={[{ required: true }]}>
            <Input placeholder={t("bindingModal.imUserIdPlaceholder")} />
          </Form.Item>
          <Form.Item name="im_user_name" label={t("bindingModal.nicknameLabel")}><Input placeholder={t("bindingModal.nicknamePlaceholder")} /></Form.Item>
          <Form.Item name="im_tenant_id" label={t("bindingModal.tenantIdLabel")}><Input placeholder={t("bindingModal.tenantIdPlaceholder")} /></Form.Item>
          <Form.Item name="default_project_id" label={t("bindingModal.defaultProjectLabel")}><Input placeholder={t("bindingModal.defaultProjectPlaceholder")} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default IntegrationsPage;
