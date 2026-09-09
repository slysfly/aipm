// Agent详情页面 - v2 完整ITTO展示
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Typography, Button, Descriptions, Tag, Space, Spin, Alert,
  Divider, Badge, Tooltip, Row, Col, Progress, Tabs, Modal, Input,
  Form, Select, message,
} from 'antd';
import {
  ArrowLeftOutlined, RocketOutlined, BookOutlined,
  ToolOutlined, CheckCircleOutlined, LoadingOutlined,
  EnvironmentOutlined, FileTextOutlined, ClockCircleOutlined,
  SettingOutlined, ThunderboltOutlined, HistoryOutlined, UploadOutlined, AimOutlined,
} from '@ant-design/icons';
import { agentV2Api } from '../api';

const { Text, Paragraph, Title } = Typography;

const PROC_GROUP_COLORS = {
  启动: { color: '#10B981', bg: '#D1FAE5', text: '#065F46' },
  规划: { color: '#3B82F6', bg: '#DBEAFE', text: '#1E40AF' },
  执行: { color: '#F97316', bg: '#FFF7ED', text: '#9A3412' },
  监控: { color: '#8B5CF6', bg: '#EDE9FE', text: '#5B21B6' },
  结束: { color: '#6B7280', bg: '#F3F4F6', text: '#374151' },
};

const DOMAIN_COLORS: Record<string, string> = {
  stakeholder: 'purple', schedule: 'blue', resource: 'green',
  cost: 'orange', quality: 'cyan', risk: 'red',
  procurement: 'volcano', communication: 'magenta',
  integration: 'gold', pmbok: 'blue', cpmai: 'geekblue',
};

interface Agent {
  id: string;
  name: string;
  name_en: string;
  domain: string;
  pmbok_process: string;
  pmbok_code?: string;
  process_group?: string;
  knowledge_area?: string;
  description: string;
  type: string;
  icon: string;
  color: string;
  accuracy?: number;
  tags: string[];
  input_hints?: string;
  inputs?: string[];
  outputs?: string[];
  tools?: string[];
  techniques?: string[];
  skills_needed?: string[];
  templates?: string[];
  usage?: string;
  expected_output?: string;
  extra?: {
    inputs?: any[];
    outputs?: any[];
    tools?: any[];
    process_group?: string;
    knowledge_area?: string;
  };
}

const AgentDetail: React.FC = () => {
  const { agentId } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [executionHistory, setExecutionHistory] = useState<any[]>([]);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executionStep, setExecutionStep] = useState(0);
  const [executeForm] = Form.useForm();

  useEffect(() => {
    if (agentId) {
      loadAgent();
      loadExecutionHistory();
    }
  }, [agentId]);

  const loadAgent = async () => {
    setLoading(true);
    try {
      const globalAgents = (window as any).__AGENT_DATA__ || [];
      const found = globalAgents.find((a: any) => 
        a.id === agentId || 
        a.pmbok_code === agentId ||
        a.name === decodeURIComponent(agentId)
      );
      
      if (found) {
        setAgent({
          ...found,
          inputs: found.inputs || found.extra?.inputs || [],
          outputs: found.outputs || found.extra?.outputs || [],
          tools: found.tools || found.extra?.tools || [],
          techniques: found.techniques || [],
          skills_needed: found.skills_needed || [],
          templates: found.templates || [],
        });
      } else {
        const res: any = await agentV2Api.list();
        const foundFromApi = res.agents?.find((a: Agent) => a.id === agentId);
        setAgent(foundFromApi || null);
      }
    } catch (err) {
      console.error('Failed to load agent:', err);
      message.error('加载Agent失败');
    } finally {
      setLoading(false);
    }
  };

  const loadExecutionHistory = async () => {
    try {
      const key = 'agent_history_' + agentId;
      const history = localStorage.getItem(key);
      if (history) {
        setExecutionHistory(JSON.parse(history));
      }
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  };

  const handleExecute = async () => {
    if (!agent) return;
    
    setExecuting(true);
    setExecutionStep(1);
    setExecuteModalOpen(false);
    
    try {
      await new Promise(r => setTimeout(r, 500));
      setExecutionStep(2);
      
      await new Promise(r => setTimeout(r, 800));
      setExecutionStep(3);
      
      const res: any = await agentV2Api.execute({
        agent_id: agent.id,
        inputs: executeForm.getFieldsValue(),
        context: { project_id: 'demo' },
      });
      
      setExecutionResult(res);
      setExecutionStep(4);
      
      const newHistory = [
        {
          id: Date.now(),
          time: new Date().toLocaleString('zh-CN'),
          status: 'success',
          duration: '2.3s',
          input: executeForm.getFieldsValue(),
          output: res,
        },
        ...executionHistory,
      ].slice(0, 10);
      
      setExecutionHistory(newHistory);
      const key = 'agent_history_' + agentId;
      localStorage.setItem(key, JSON.stringify(newHistory));
      
      message.success('执行成功');
    } catch (err) {
      console.error('Execution failed:', err);
      message.error('执行失败');
      setExecutionStep(0);
    } finally {
      setExecuting(false);
    }
  };

  const handleCancel = () => {
    setExecuteModalOpen(false);
    setExecutionStep(0);
    setExecuting(false);
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div style={{ padding: 40 }}>
        <Alert
          message="Agent未找到"
          description={'找不到ID为 "' + agentId + '" 的Agent'}
          type="error"
          action={
            <Button onClick={() => navigate(-1)}>返回</Button>
          }
        />
      </div>
    );
  }

  const domainColor = DOMAIN_COLORS[agent.domain] || 'default';
  const procGroup = agent.process_group || agent.extra?.process_group || '其他';
  const procColors = PROC_GROUP_COLORS[procGroup as keyof typeof PROC_GROUP_COLORS] || PROC_GROUP_COLORS.规划;
  
  const inputs = agent.inputs || agent.extra?.inputs || [];
  const outputs = agent.outputs || agent.extra?.outputs || [];
  const tools = agent.tools || agent.extra?.tools || [];
  const techniques = agent.techniques || [];
  const skills = agent.skills_needed || [];
  const templates = agent.templates || [];

  return (
    <div style={{ padding: '24px', background: '#F8FAFC', minHeight: '100vh' }}>
      <Space style={{ marginBottom: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/agents')}>
          返回Agent列表
        </Button>
      </Space>

      <Card style={{ marginBottom: 24, borderRadius: 12 }}>
        <Row align="middle" gutter={[24, 16]}>
          <Col flex="auto">
            <Space wrap>
              <Title level={2} style={{ margin: 0 }}>{agent.name}</Title>
              <Badge color={procColors.color} text={<span style={{ color: procColors.text }}>{procGroup}</span>} />
              <Tag color={domainColor}>{agent.domain}</Tag>
              {agent.knowledge_area && (
                <Tag style={{ background: '#f0f9ff', color: '#0369a1', borderColor: '#bae6fd' }}>
                  {agent.knowledge_area}
                </Tag>
              )}
              {agent.pmbok_code && (
                <Tag style={{ fontFamily: 'monospace' }}>
                  <BookOutlined /> {agent.pmbok_code}
                </Tag>
              )}
            </Space>
            <div style={{ marginTop: 8, color: '#64748B' }}>
              {agent.name_en && <Text>{agent.name_en}</Text>}
            </div>
          </Col>
          <Col>
            <Button
              type="primary"
              size="large"
              icon={executing ? <LoadingOutlined /> : <RocketOutlined />}
              onClick={() => setExecuteModalOpen(true)}
              loading={executing}
              style={{ background: '#FF6B35', borderColor: '#FF6B35' }}
            >
              执行Agent
            </Button>
          </Col>
        </Row>
      </Card>

      <Row gutter={[24, 24]}>
        <Col xs={24} md={12} lg={8}>
          <Card
            title={
              <Space>
                <EnvironmentOutlined style={{ color: '#10B981' }} />
                <span>输入 (Inputs)</span>
                <Badge count={inputs.length} color="#10B981" />
                <Button 
                  size="small" 
                  icon={<UploadOutlined />}
                  style={{ marginLeft: 'auto', background: '#f0fdf4', borderColor: '#bbf7d0', color: '#166534' }}
                  onClick={() => message.info('上传功能开发中')}
                >
                  上传
                </Button>
                <Button 
                  size="small" 
                  icon={<AimOutlined />}
                  type="primary"
                  style={{ background: '#10B981', borderColor: '#10B981' }}
                  onClick={() => message.info('AI生成功能开发中')}
                >
                  AI生成
                </Button>
              </Space>
            }
            styles={{ header: { borderBottom: '2px solid #D1FAE5' } }}
            bodyStyle={{ paddingTop: 16 }}
          >
            {inputs.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {inputs.map((input: any, i: number) => (
                  <div key={i} style={{ padding: '8px 12px', background: '#f0fdf4', borderRadius: 6, border: '1px solid #bbf7d0' }}>
                    <Text strong style={{ color: '#166534' }}>{typeof input === 'string' ? input : input.label || input.key}</Text>
                  </div>
                ))}
              </div>
            ) : (
              <Text type="secondary">暂无输入信息</Text>
            )}
          </Card>
        </Col>

        <Col xs={24} md={12} lg={8}>
          <Card
            title={
              <Space>
                <ToolOutlined style={{ color: '#F59E0B' }} />
                <span>工具与技术</span>
                <Badge count={tools.length + techniques.length} color="#F59E0B" />
              </Space>
            }
            styles={{ header: { borderBottom: '2px solid #FDE68A' } }}
            bodyStyle={{ paddingTop: 16 }}
          >
            {tools.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Text strong style={{ color: '#92400E', fontSize: 12, display: 'block', marginBottom: 8 }}>工具</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {tools.map((tool: any, i: number) => (
                    <Tag key={i} style={{ margin: 0, background: '#fffbeb', color: '#92400E', borderColor: '#fde68a' }}>
                      {typeof tool === 'string' ? tool : tool.name}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
            {techniques.length > 0 && (
              <div>
                <Text strong style={{ color: '#92400E', fontSize: 12, display: 'block', marginBottom: 8 }}>技法</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {techniques.map((tech: string, i: number) => (
                    <Tag key={i} style={{ margin: 0, background: '#fef3c7', color: '#92400E', borderColor: '#fcd34d' }}>
                      {tech}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
            {tools.length === 0 && techniques.length === 0 && (
              <Text type="secondary">暂无工具信息</Text>
            )}
          </Card>
        </Col>

        <Col xs={24} md={12} lg={8}>
          <Card
            title={
              <Space>
                <CheckCircleOutlined style={{ color: '#3B82F6' }} />
                <span>输出 (Outputs)</span>
                <Badge count={outputs.length} color="#3B82F6" />
              </Space>
            }
            styles={{ header: { borderBottom: '2px solid #BFDBFE' } }}
            bodyStyle={{ paddingTop: 16 }}
          >
            {outputs.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {outputs.map((output: any, i: number) => (
                  <div key={i} style={{ padding: '8px 12px', background: '#eff6ff', borderRadius: 6, border: '1px solid #bfdbfe' }}>
                    <Text strong style={{ color: '#1e40af' }}>{typeof output === 'string' ? output : output.label || output.key}</Text>
                  </div>
                ))}
              </div>
            ) : (
              <Text type="secondary">暂无输出信息</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={16}>
          <Card
            title={<Space><BookOutlined />详细说明</Space>}
            styles={{ header: { borderBottom: '2px solid #E5E7EB' } }}
          >
            <Paragraph style={{ lineHeight: 1.8 }}>
              {agent.description || agent.input_hints || '暂无详细说明'}
            </Paragraph>
            
            {agent.usage && (
              <div style={{ marginTop: 16 }}>
                <Text strong style={{ color: '#FF6B35' }}>
                  <ThunderboltOutlined style={{ marginRight: 8 }} />使用方法
                </Text>
                <div style={{ marginTop: 8, padding: 16, background: '#fafafa', borderRadius: 8, lineHeight: 1.8 }}>
                  {agent.usage}
                </div>
              </div>
            )}
            
            {agent.expected_output && (
              <div style={{ marginTop: 16 }}>
                <Text strong style={{ color: '#10B981' }}>
                  <CheckCircleOutlined style={{ marginRight: 8 }} />预期产出
                </Text>
                <div style={{ marginTop: 8, padding: 16, background: '#f0fdf4', borderRadius: 8, border: '1px solid #bbf7d0' }}>
                  {agent.expected_output}
                </div>
              </div>
            )}

            {skills.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <Text strong>所需技能:</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  {skills.map((skill: string, i: number) => (
                    <Tag key={i} style={{ background: '#f5f3ff', color: '#6d28d9', borderColor: '#ddd6fe' }}>
                      {skill}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card
            title={
              <Space>
                <HistoryOutlined />
                <span>执行历史</span>
                <Badge count={executionHistory.length} color="#8B5CF6" />
              </Space>
            }
            styles={{ header: { borderBottom: '2px solid #EDE9FE' } }}
            bodyStyle={{ paddingTop: 16 }}
          >
            {executionHistory.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {executionHistory.map((record) => (
                  <div key={record.id} style={{ padding: 12, background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <Badge status="success" text={<Text strong style={{ color: '#166534' }}>成功</Text>} />
                      <Text type="secondary" style={{ fontSize: 12 }}>{record.time}</Text>
                    </div>
                    <div style={{ fontSize: 12, color: '#64748B' }}>耗时: {record.duration}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#94A3B8' }}>
                <HistoryOutlined style={{ fontSize: 32, marginBottom: 8, display: 'block' }} />
                <div>暂无执行记录</div>
              </div>
            )}
          </Card>

          {templates.length > 0 && (
            <Card
              title={<Space><FileTextOutlined />模板文件</Space>}
              styles={{ header: { borderBottom: '2px solid #E5E7EB' } }}
              bodyStyle={{ paddingTop: 16 }}
              style={{ marginTop: 24 }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {templates.map((tpl: any, i: number) => (
                  <div key={i} onClick={() => window.open(tpl.html_path || tpl, '_blank')} style={{ padding: 12, background: '#f8fafc', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileTextOutlined style={{ color: '#3B82F6' }} />
                    <Text style={{ fontSize: 13 }}>{typeof tpl === 'string' ? tpl : tpl.title || tpl}</Text>
                    <Button type="link" size="small" href={typeof tpl === 'string' ? tpl : tpl.html_path} target="_blank" onClick={(e) => e.stopPropagation()}>
                      打开
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </Col>
      </Row>

      <Modal
        title={<Space><RocketOutlined />执行 {agent.name}</Space>}
        open={executeModalOpen}
        onCancel={handleCancel}
        footer={null}
        width={700}
        destroyOnClose
      >
        <div style={{ padding: '16px 0' }}>
          {executing && (
            <div style={{ marginBottom: 24 }}>
              <Progress 
                percent={executionStep * 25} 
                status="active"
                strokeColor="#FF6B35"
              />
              <div style={{ marginTop: 8, fontSize: 12, color: '#64748B', textAlign: 'center' }}>
                {['理解任务...', '收集输入...', '调用工具...', '生成结果...'][executionStep - 1] || '处理中...'}
              </div>
            </div>
          )}

          <Form form={executeForm} layout="vertical">
            {inputs.length > 0 ? (
              inputs.map((input: any, i: number) => (
                <Form.Item
                  key={i}
                  name={typeof input === 'string' ? input : input.key}
                  label={typeof input === 'string' ? input : input.label}
                  rules={[{ required: (input as any)?.required, message: '此项为必填' }]}
                >
                  {(input as any)?.type === 'textarea' ? (
                    <Input.TextArea rows={3} placeholder="请输入...（此字段为可选输入）" />
                  ) : (
                    <Input placeholder="请输入...（此字段为可选输入）" />
                  )}
                </Form.Item>
              ))
            ) : (
              <Alert
                message="无需输入参数"
                description="此Agent可立即执行，无需额外输入"
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {tools.length > 0 && (
              <Form.Item name="selected_tools" label="选择工具">
                <Select
                  mode="multiple"
                  placeholder="选择要使用的工具（默认全选）"
                  options={tools.map((t: any) => ({
                    value: typeof t === 'string' ? t : t.key,
                    label: typeof t === 'string' ? t : t.name,
                  }))}
                  defaultValue={tools.map((t: any) => typeof t === 'string' ? t : t.key)}
                />
              </Form.Item>
            )}
          </Form>

          <Divider />

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button onClick={handleCancel}>取消</Button>
            <Button
              type="primary"
              icon={<RocketOutlined />}
              onClick={handleExecute}
              loading={executing}
              style={{ background: '#FF6B35', borderColor: '#FF6B35' }}
            >
              开始执行
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default AgentDetail;
