import React, { useState, useEffect } from 'react';
import { Card, Button, Tag, Progress, Timeline, Typography, Space, Alert, Spin, Select, Input } from 'antd';
import { PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { workflowV2Api } from '../api';

const { Text, Title } = Typography;
const { Option } = Select;

interface Workflow {
  id: string;
  name: string;
  description: string;
  agent_count: number;
  version: string;
  status: string;
}

interface NodeResult {
  agent_id: string;
  status: string;
  duration_seconds: number;
  output_preview: string | null;
  error: string;
}

interface Execution {
  execution_id: string;
  workflow_id: string;
  project_id: string | null;
  user_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  nodes: Record<string, NodeResult>;
  metadata: Record<string, any>;
}

const WorkflowCanvasV2: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>('');
  const [execution, setExecution] = useState<Execution | null>(null);
  const [loading, setLoading] = useState(false);
  const [userRequirement, setUserRequirement] = useState('');

  useEffect(() => {
    loadWorkflows();
  }, []);

  const loadWorkflows = async () => {
    try {
      const res = await workflowV2Api.list();
      setWorkflows(res.workflows || []);
      if (res.workflows?.length > 0) {
        setSelectedWorkflow(res.workflows[0].id);
      }
    } catch (err) {
      console.error('Failed to load workflows:', err);
    }
  };

  const handleExecute = async () => {
    if (!selectedWorkflow) return;
    setLoading(true);
    setExecution(null);
    try {
      const res = await workflowV2Api.execute({
        workflow_id: selectedWorkflow,
        context: {
          user_requirement: userRequirement || '请执行工作流任务',
          input_key: 'default',
          input_label: '默认输入',
        },
      });
      setExecution({
        execution_id: res.execution_id,
        workflow_id: res.workflow_id,
        project_id: res.project_id,
        user_id: res.user_id || '',
        status: res.status,
        started_at: res.created_at,
        completed_at: null,
        nodes: {},
        metadata: {},
      });
      pollExecution(res.execution_id);
    } catch (err) {
      Alert.error({ message: '执行失败，请稍后重试' });
      setLoading(false);
    }
  };

  const pollExecution = async (executionId: string) => {
    const poll = async () => {
      try {
        const res = await workflowV2Api.getExecution(executionId);
        setExecution(res);
        if (res.status === 'completed' || res.status === 'failed') {
          setLoading(false);
          return;
        }
        setTimeout(poll, 3000);
      } catch (err) {
        console.error('Failed to poll execution:', err);
        setLoading(false);
      }
    };
    poll();
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'success';
      case 'running': return 'processing';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const getNodeStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'running': return <Spin size="small" />;
      case 'failed': return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
      default: return <ClockCircleOutlined />;
    }
  };

  const getSelectedWorkflow = () => workflows.find(w => w.id === selectedWorkflow);
  const totalDuration = execution?.nodes ? Object.values(execution.nodes).reduce((s: number, n: NodeResult) => s + n.duration_seconds, 0) : 0;
  const completedNodes = execution?.nodes ? Object.values(execution.nodes).filter((n: NodeResult) => n.status === 'completed').length : 0;
  const progressPercent = execution?.nodes && Object.keys(execution.nodes).length > 0 ? Math.round((completedNodes / Object.keys(execution.nodes).length) * 100) : 0;

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>
        <ThunderboltOutlined style={{ marginRight: 8, color: '#4F46E5' }} />
        Workflow V2 - DAG编排引擎
      </Title>
      <Text type="secondary">基于DAG拓扑排序的并行执行引擎，支持17个Agent完整工作流</Text>

      <Space direction="vertical" size="large" style={{ width: '100%', marginTop: 24 }}>
        <Card title="执行配置" loading={loading}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Text strong>选择工作流：</Text>
              <Select style={{ width: 300, marginLeft: 8 }} value={selectedWorkflow} onChange={setSelectedWorkflow} disabled={loading}>
                {workflows.map(wf => (<Option key={wf.id} value={wf.id}>{wf.name} ({wf.agent_count}个Agent)</Option>))}
              </Select>
            </div>
            <div>
              <Text strong>用户需求：</Text>
              <Input.TextArea style={{ width: 500, marginTop: 8 }} rows={3} placeholder="请输入您的需求描述" value={userRequirement} onChange={e => setUserRequirement(e.target.value)} disabled={loading} />
            </div>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleExecute} loading={loading} size="large" disabled={!selectedWorkflow}>
              {loading ? '执行中...' : '开始执行'}
            </Button>
          </Space>
        </Card>

        {execution && (
          <Card title={"执行结果 - " + execution.execution_id.substring(0, 8) + "..."}>
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <div>
                <Text strong>状态：</Text>
                <Tag color={getStatusColor(execution.status)}>
                  {execution.status === 'completed' ? '已完成' : execution.status === 'running' ? '执行中' : '失败'}
                </Tag>
                <Text type="secondary" style={{ marginLeft: 16 }}>开始时间：{new Date(execution.started_at).toLocaleString()}</Text>
                {execution.completed_at && <Text type="secondary">，结束时间：{new Date(execution.completed_at).toLocaleString()}</Text>}
              </div>
              {execution.nodes && Object.keys(execution.nodes).length > 0 && (
                <>
                  <Progress percent={progressPercent} status={execution.status === 'failed' ? 'exception' : 'normal'} strokeColor="#4F46E5" />
                  <Timeline items={Object.entries(execution.nodes).map(([id, node]) => ({
                    dot: getNodeStatusIcon(node.status),
                    color: node.status === 'completed' ? 'green' : node.status === 'failed' ? 'red' : 'blue',
                    children: <div><Text strong>{node.agent_id}</Text><Text type="secondary" style={{ marginLeft: 8 }}>({node.duration_seconds.toFixed(1)}s)</Text>{node.error && <Text type="danger" style={{ marginLeft: 8 }}>Error: {node.error}</Text>}</div>
                  }))} />
                  <div style={{ marginTop: 16 }}><Text strong>总耗时：</Text><Text style={{ fontSize: 18, color: '#4F46E5', fontWeight: 'bold' }}>{totalDuration.toFixed(1)} 秒</Text></div>
                </>
              )}
              {execution.metadata?.error && <Alert type="error" message={"执行失败: " + execution.metadata.error} showIcon />}
            </Space>
          </Card>
        )}

        {getSelectedWorkflow() && (
          <Card title="工作流信息">
            <div><Text strong>名称：</Text><Text>{getSelectedWorkflow()?.name}</Text></div>
            <div><Text strong>描述：</Text><Text type="secondary">{getSelectedWorkflow()?.description}</Text></div>
            <div><Text strong>版本：</Text><Tag>{getSelectedWorkflow()?.version}</Tag><Text strong style={{ marginLeft: 16 }}>Agent数量：</Text><Tag color="blue">{getSelectedWorkflow()?.agent_count}</Tag></div>
          </Card>
        )}
      </Space>
    </div>
  );
};

export default WorkflowCanvasV2;
