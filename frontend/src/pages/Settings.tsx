import React, { useEffect, useState } from "react";
import {
  Card, Descriptions, Tag, Button, App, Typography, Form, Select, Input, InputNumber, Spin,
  Space, Divider, Alert, Table, Popconfirm, Checkbox, Switch, message as antdMessage,
} from "antd";
import { ReloadOutlined, SaveOutlined, ThunderboltOutlined, ApiOutlined } from "@ant-design/icons";
import { useAuth } from "../store/AuthContext";
import { get, post, put, del } from "../api/http";
import BrandSettings from "../components/BrandSettings";
import ProjectTypeSettings from "../components/ProjectTypeSettings";

const { Title, Text, Paragraph } = Typography;

const SCOPE_OPTIONS = [
  { label: "项目-读", value: "projects:read" },
  { label: "项目-写", value: "projects:write" },
  { label: "任务-读", value: "tasks:read" },
  { label: "任务-写", value: "tasks:write" },
  { label: "AI 对话", value: "ai:chat" },
  { label: "全部权限", value: "*" },
];

const ModelSettings: React.FC = () => {
  const { message } = App.useApp();
  const [providers, setProviders] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>(null);
  const [form] = Form.useForm();
  const [advice, setAdvice] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [apiKeyTouched, setApiKeyTouched] = useState(false);
  const [modelLoading, setModelLoading] = useState(true);

  const loadProviders = async () => {
    try {
      const data = await get("/system/llm-config/providers");
      setProviders(data.providers || []);
    } catch {
      setProviders([]);
    }
  };

  const loadCurrent = async () => {
    setModelLoading(true);
    try {
      const data = await get("/system/llm-config");
      setCurrent(data);
      form.setFieldsValue({
        provider_name: data.provider_name,
        model_name: data.model_name,
        base_url: data.base_url,
        temperature: data.temperature,
        max_tokens: data.max_tokens,
        is_active: data.is_active,
      });
    } catch {
      setCurrent(null);
    } finally {
      setModelLoading(false);
    }
  };

  useEffect(() => {
    loadProviders();
    loadCurrent();
  }, []);

  const onProviderChange = (name: string) => {
    const p = providers.find((x) => x.name === name);
    if (!p) return;
    form.setFieldsValue({
      base_url: p.default_base_url,
      model_name: p.default_model,
    });
    setAdvice(p.config_advice || "");
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const payload: any = {
      provider_name: values.provider_name,
      base_url: values.base_url,
      model_name: values.model_name,
      temperature: values.temperature,
      max_tokens: values.max_tokens,
      is_active: values.is_active !== false,
    };
    // 仅当用户实际填写了 key 才发送（避免清空已有密文）
    if (apiKeyTouched && values.api_key) {
      payload.api_key = values.api_key;
    }
    setLoading(true);
    try {
      await put("/system/llm-config", payload);
      message.success("系统大模型已保存，全局 AI 能力将立即生效");
      setApiKeyTouched(false);
      await loadCurrent();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await post("/system/llm-config/test", { message: "你好，这是一次连接测试。" });
      if (res.success) {
        message.success(`连接成功（${res.latency_ms}ms）：${res.response?.slice(0, 60)}`);
      } else {
        message.error(res.message || "连接失败");
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "测试失败");
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card title={<Space><ThunderboltOutlined /><span>大模型设置（系统默认 AI 引擎）</span></Space>} style={{ marginBottom: 16 }}>
      <Spin spinning={modelLoading}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="该配置为系统级默认大模型，所有 AI 能力（WBS 生成 / 项目分析 / 风险预测 / AI 对话 / 表单辅助填写）将自动使用。"
        description="系统已内置默认 MiniMax M2.7（含密钥）。API Key 以密文存储，列表与表单均不回显明文。"
      />

      {current && (
        <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
          <Descriptions.Item label="当前模型">
            <Tag color="blue">{current.provider_name}</Tag> {current.model_name}
          </Descriptions.Item>
          <Descriptions.Item label="API Key">
            {current.has_api_key ? <Tag color="green">已配置（密文）</Tag> : <Tag color="red">未配置</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {current.is_active ? <Tag color="green">生效中</Tag> : <Tag>未激活</Tag>}
          </Descriptions.Item>
        </Descriptions>
      )}

      <Form form={form} layout="vertical" initialValues={{ temperature: 0.7, max_tokens: 2000, is_active: true }}>
        <Space size="large" wrap>
          <Form.Item name="provider_name" label="大模型厂商" rules={[{ required: true }]} style={{ width: 240 }}>
            <Select
              placeholder="选择厂商"
              showSearch
              onChange={onProviderChange}
              options={providers.map((p) => ({ label: p.display_name, value: p.name }))}
            />
          </Form.Item>
          <Form.Item name="model_name" label="模型名称" rules={[{ required: true }]} style={{ width: 240 }}>
            <Input placeholder="如 MiniMax-M2.7" />
          </Form.Item>
        </Space>
        <Form.Item name="base_url" label="Base URL" style={{ maxWidth: 520 }}>
          <Input placeholder="https://api.minimax.chat/v1" />
        </Form.Item>
        <Form.Item
          name="api_key"
          label="API Key（留空表示不修改已保存的密文）"
          style={{ maxWidth: 520 }}
        >
          <Input.Password
            placeholder="sk-...（密文存储）"
            onChange={() => setApiKeyTouched(true)}
            visibilityToggle
          />
        </Form.Item>
        <Space size="large" wrap>
          <Form.Item name="temperature" label="温度" style={{ width: 160 }}>
            <InputNumber min={0} max={2} step={0.1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_tokens" label="最大 Token" style={{ width: 160 }}>
            <InputNumber min={1} max={32000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="is_active" label="设为生效" valuePropName="checked" style={{ width: 100 }}>
            <Checkbox>生效</Checkbox>
          </Form.Item>
        </Space>

        {advice && (
          <Alert type="success" showIcon style={{ marginBottom: 12 }} message="配置建议" description={<pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{advice}</pre>} />
        )}

        <Space>
          <Button type="primary" icon={<SaveOutlined />} loading={loading} onClick={handleSave}>保存并激活</Button>
          <Button icon={<ReloadOutlined />} loading={testing} onClick={handleTest}>连接测试</Button>
        </Space>
      </Form>
      </Spin>
    </Card>
  );
};

const ApiKeySettings: React.FC = () => {
  const { message } = App.useApp();
  const [keys, setKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      setKeys(await get("/system/api-keys"));
    } catch {
      setKeys([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    const values = await form.validateFields();
    try {
      const res = await post("/system/api-keys", values);
      setCreatedKey(res.plain_key);
      form.resetFields();
      setModal(false);
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await del(`/system/api-keys/${id}`);
      message.success("已删除");
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "删除失败");
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name" },
    { title: "前缀", dataIndex: "key_prefix" },
    { title: "权限范围", dataIndex: "scopes", render: (s: string[]) => (s || []).map((x) => <Tag key={x}>{x}</Tag>) },
    { title: "状态", dataIndex: "is_active", render: (a: boolean) => (a ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag>) },
    {
      title: "操作",
      render: (_: any, r: any) => (
        <Popconfirm title="确认删除该 API Key？" onConfirm={() => handleDelete(r.id)}>
          <Button danger size="small">删除</Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <Card
      title={<Space><ApiOutlined /><span>对外 API 密钥（外部系统免登录调用）</span></Space>}
      style={{ marginBottom: 16 }}
      extra={<Button type="primary" onClick={() => { setCreatedKey(null); setModal(true); }}>创建密钥</Button>}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="外部系统凭此 Key 调用 /api/v1/external/* （项目/任务读写、AI 对话），按 scopes 限制权限，无需登录本系统。"
      />
      <Table rowKey="id" size="small" loading={loading} dataSource={keys} columns={columns} pagination={false} />

      {modal && (
        <div style={{ marginTop: 16, padding: 16, border: "1px solid #f0f0f0", borderRadius: 8 }}>
          <Form form={form} layout="vertical">
            <Form.Item name="name" label="密钥名称" rules={[{ required: true }]}>
              <Input placeholder="例如：飞书机器人 / 外部系统集成" />
            </Form.Item>
            <Form.Item name="scopes" label="权限范围" rules={[{ required: true }]}>
              <Checkbox.Group options={SCOPE_OPTIONS} />
            </Form.Item>
            <Space>
              <Button type="primary" onClick={handleCreate}>创建</Button>
              <Button onClick={() => setModal(false)}>取消</Button>
            </Space>
          </Form>
        </div>
      )}

      {createdKey && (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 12 }}
          message="密钥已创建（仅显示一次，请妥善保存）"
          description={<Text copyable code>{createdKey}</Text>}
        />
      )}
    </Card>
  );
};

const ExternalIntegrationSettings: React.FC = () => {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState<boolean>(false);
  const [publicBase, setPublicBase] = useState<string>("");
  const [note, setNote] = useState<string>("");

  const deriveEndpoint = () => {
    const base = publicBase || `${window.location.origin}/api/v1`;
    return `${base.replace(/\/$/, "")}/external`;
  };

  const load = async () => {
    setLoading(true);
    try {
      const cfg = await get("/system/external-api-config");
      setEnabled(!!cfg.enabled);
      setPublicBase(cfg.public_base_url || "");
      setNote(cfg.note || "");
    } catch {
      // 默认未启用
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleToggle = async (checked: boolean) => {
    setSaving(true);
    try {
      await put("/system/external-api-config", {
        enabled: checked,
        public_base_url: publicBase,
        note,
      });
      setEnabled(checked);
      message.success(checked ? "已开放对外 API 端口，外部系统可凭 Key 调用" : "已关闭对外 API 端口");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      title={<Space><ApiOutlined /><span>外部对接（开放 API 端口）</span></Space>}
      style={{ marginBottom: 16 }}
    >
      <Spin spinning={loading}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="开启后，外部系统（如飞书机器人）可凭 API Key 免登录调用本系统；关闭则所有 /api/v1/external/* 请求返回 403。"
          description="下方「对外 API 密钥」中创建的密钥 + 权限范围（可调用字段）即生效。"
        />
        <Form layout="vertical">
          <Form.Item label="启用对外 API（自主开放端口）">
            <Switch
              checked={enabled}
              loading={saving}
              onChange={handleToggle}
              checkedChildren="已开放"
              unCheckedChildren="已关闭"
            />
          </Form.Item>
          <Form.Item label="对外 API 地址（外部系统调用入口）">
            <Text copyable code>{deriveEndpoint()}</Text>
            <div style={{ marginTop: 4 }}>
              <Text type="secondary">
                请求头携带 X-API-Key 或 Authorization: Bearer 即可调用；权限由密钥的「权限范围」限定。
              </Text>
            </div>
          </Form.Item>
          <Form.Item
            label="自定义对外访问地址（可选）"
            extra="留空则自动使用上方地址；若通过反向代理 / 域名暴露，可填写如 https://your-domain.com/api/v1"
          >
            <Input
              value={publicBase}
              onChange={(e) => setPublicBase(e.target.value)}
              placeholder="https://your-domain.com/api/v1"
            />
          </Form.Item>
        </Form>
      </Spin>
    </Card>
  );
};

const Settings: React.FC = () => {
  const { user, logout } = useAuth();
  const { message } = App.useApp();
  const isAdmin = !!user?.is_superuser;

  return (
    <div>
      <Title level={3}>系统设置</Title>

      {isAdmin && (
        <>
          <BrandSettings />
          <ModelSettings />
          <ApiKeySettings />
          <ProjectTypeSettings />
        </>
      )}

      <Card title="当前用户" style={{ marginBottom: 16 }} data-tour="settings-user">
        <Descriptions column={2}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="姓名">{user?.full_name || "—"}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{user?.email || "—"}</Descriptions.Item>
          <Descriptions.Item label="角色">{user?.role || (user?.is_superuser ? "超级管理员" : "成员")}</Descriptions.Item>
        </Descriptions>
      </Card>

      <ExternalIntegrationSettings />

      <Button danger onClick={() => { logout(); message.success("已退出登录"); }}>退出登录</Button>
    </div>
  );
};

export default Settings;
