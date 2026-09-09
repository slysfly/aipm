import React, { useState, useEffect, useRef } from 'react';
import {
  Tooltip,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  Tag,
  message,
  Popconfirm,
  Typography,
  Card,
  Col,
  Row,
  Statistic,
  InputNumber,
  Tabs,
  Spin,
  Alert,
  Divider,
  Switch,
  Slider,
  Radio,
  Drawer,
} from 'antd';
import {
  PlusOutlined,
  ToolOutlined,
  SearchOutlined,
  DeleteOutlined,
  EditOutlined,
  CheckCircleOutlined,
  PlayCircleOutlined,
  BugOutlined,
  CodeOutlined,
  SettingOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { TextArea } = Input;

// 扩展Skill接口，支持执行配置
interface SkillExecutionConfig {
  enabled: boolean;
  prompt_template: string;
  input_contract: {
    required: string[];
    optional: string[];
    validation: string;
  };
  output_schema: {
    type: string;
    sections: string[];
    format: string;
  };
  execution_mode: string;
  timeout_seconds: number;
}

interface SkillMetadata {
  pmbok_version?: string;
  skill_type?: string;
  difficulty?: string;
  estimated_time?: string;
  version?: string;
  type?: string;
  complexity?: string;
  estimated_tokens?: number;
  tags?: string[];
}

interface Skill {
  id: string;
  name: string;
  name_en: string;
  domain: string;
  process_group: string;
  pmbok_process: string;
  description: string;
  inputs: string[];
  tools: string[];
  outputs: string[];
  metadata: SkillMetadata;
  agent_ids?: string[];
  execution?: SkillExecutionConfig;
}

interface SkillStats {
  total: number;
  by_group: Record<string, number>;
  by_domain: Record<string, number>;
}

const PROCESS_GROUP_COLORS: Record<string, string> = {
  启动: 'blue',
  规划: 'purple',
  执行: 'cyan',
  监控: 'gold',
  结束: 'green',
};

const DIFFICULTY_COLORS: Record<string, string> = {
  基础: 'green',
  中级: 'orange',
  高级: 'red',
};

// Process group-specific prompt templates
const PROMPT_TEMPLATES: Record<string, string> = {
  启动: `你是通维咨询的资深项目经理，精通PMBOK第六/七版知识体系。当前任务是{skill_name}。

## 核心能力要求
- 深刻理解项目立项流程与授权机制
- 熟练运用利益相关方分析技术
- 能够制定清晰的项目章程和假设日志
- 准确把握项目边界与成功标准

## 执行框架
1. **需求洞察**: 理解商业文件、协议等输入材料，识别关键约束条件
2. **利益相关方识别**: 系统分析所有相关方，评估权力-利益矩阵
3. **章程制定**: 编写正式的项目章程，明确项目目标、范围和授权
4. **风险预判**: 识别潜在启动阶段风险，提出应对建议

## 输出标准
请输出结构化报告，包含：
- 任务理解与目标确认
- 利益相关方分析矩阵
- 项目章程草案（含目标、范围、成功标准）
- 假设日志与约束条件
- 风险登记册（初步）

保持专业、务实的风格，语言简洁有力，注重可操作性。`,
  
  规划: `你是通维咨询的高级规划专家，擅长项目规划与计划制定。当前任务是{skill_name}。

## 核心能力要求
- 精通WBS分解与进度网络图技术
- 熟练掌握资源估算与成本预算方法
- 能够有效进行风险评估与应对规划
- 能够制定全面的项目管理计划

## 执行框架
1. **现状评估**: 分析输入材料，理解项目背景与约束
2. **工作分解**: 构建WBS，明确可交付成果与工作包
3. **进度估算**: 应用类比、参数或三点估算技术
4. **资源规划**: 识别所需资源，制定资源分解结构
5. **风险规划**: 识别风险，制定应对策略
6. **计划整合**: 形成综合项目管理计划

## 输出标准
请输出详细规划文档，包含：
- 工作分解结构（WBS）
- 进度计划（甘特图或里程碑表）
- 资源计划与成本预算
- 风险管理计划
- 沟通管理计划
- 质量管理和配置管理计划

确保规划具备可执行性，数据合理，逻辑清晰。`,
  
  执行: `你是通维咨询的执行督导专家，擅长项目执行与团队协调。当前任务是{skill_name}。

## 核心能力要求
- 精通团队管理与冲突解决技术
- 熟练掌握质量保证与控制方法
- 能够有效管理供应商与采购
- 能够协调多方利益，推动项目进展

## 执行框架
1. **团队组建**: 明确角色职责，建立高效团队
2. **任务分配**: 根据技能匹配分配工作
3. **执行监控**: 跟踪进展，识别偏差
4. **质量保证**: 确保交付物符合标准
5. **沟通协调**: 管理利益相关方期望
6. **问题处理**: 及时解决问题，避免累积

## 输出标准
请输出执行报告，包含：
- 团队结构与职责分工
- 任务完成进度
- 质量保证检查结果
- 问题与偏差记录
- 改进建议与后续行动

注重实战性，提供可操作的执行指南。`,
  
  监控: `你是通维咨询的监控控制专家，擅长项目绩效测量与变更管理。当前任务是{skill_name}。

## 核心能力要求
- 精通挣值管理（EVM）技术
- 熟练掌握变更控制流程
- 能够进行有效的绩效报告
- 能够做出准确的预测与决策

## 执行框架
1. **绩效测量**: 收集实际数据，计算EV、PV、AC
2. **偏差分析**: 计算CV、SV、CPI、SPI，分析偏差原因
3. **趋势预测**: 基于当前绩效预测完工估算
4. **变更控制**: 评估变更请求，执行CCB流程
5. **风险再评估**: 监控已识别风险，发现新风险
6. **报告编制**: 生成绩效报告，传达关键信息

## 输出标准
请输出监控报告，包含：
- 绩效测量数据（EVM指标）
- 偏差分析与根本原因
- 完工预测（EAC、ETC、VAC）
- 变更请求处理结果
- 风险状态更新
- 下一步行动建议

强调数据驱动，决策有据。`,
  
  结束: `你是通维咨询的收尾管理专家，擅长项目总结与知识沉淀。当前任务是{skill_name}。

## 核心能力要求
- 精通项目验收与交付流程
- 熟练掌握经验教训总结方法
- 能够有效进行团队解散与资源释放
- 能够沉淀组织过程资产

## 执行框架
1. **产品验收**: 确认可交付成果符合合同要求
2. **合同收尾**: 完成采购结算与合同关闭
3. **知识沉淀**: 总结经验教训，更新知识库
4. **团队释放**: 安排人员归属，表彰贡献
5. **资产移交**: 移交项目文档与资产
6. **庆祝仪式**: 举办项目复盘与庆祝活动

## 输出标准
请输出收尾报告，包含：
- 验收检查清单与结果
- 经验教训总结（成功因素与改进点）
- 团队绩效评估
- 资产移交清单
- 后续维护建议
- 项目归档目录

注重知识传承，为后续项目提供参考。`,
};

const SkillsManagementPage: React.FC = () => {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [stats, setStats] = useState<SkillStats | null>(null);
  const [groups, setGroups] = useState<string[]>([]);
  const [agentRegistry, setAgentRegistry] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<string>('');
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testInputs, setTestInputs] = useState<Record<string, string>>({});
  const [form] = Form.useForm();
  const [activeTab, setActiveTab] = useState('basic');
  const [searchText, setSearchText] = useState('');
  const [filterGroup, setFilterGroup] = useState<string | undefined>();
  const [filterDifficulty, setFilterDifficulty] = useState<string | undefined>();

  useEffect(() => {
    fetchData();
    fetchStats();
    fetchGroups();
    axios.get("/api/v1/agents/registry").then(res => {
      if (res.data && res.data.agents) {
        setAgentRegistry(res.data.agents);
      }
    }).catch(() => {});
  }, []);

  const fetchData = async (group?: string, search?: string) => {
    setLoading(true);
    try {
      const params: any = {};
      if (group) params.process_group = group;
      if (search) params.search = search;
      const res = await axios.get('/api/v1/skills/', { params });
      setSkills(res.data);
    } catch (error) {
      console.error('Failed to load skills:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await axios.get('/api/v1/skills/stats');
      setStats(res.data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const fetchGroups = async () => {
    try {
      const res = await axios.get('/api/v1/skills/groups');
      setGroups(res.data);
    } catch (error) {
      console.error('Failed to load groups:', error);
    }
  };

  const handleSearch = (value: string) => {
    setSearchText(value);
    fetchData(filterGroup, value || undefined);
  };

  const handleFilterGroup = (value: string | undefined) => {
    setFilterGroup(value);
    fetchData(value, searchText || undefined);
  };

  const handleFilterDifficulty = (value: string | undefined) => {
    setFilterDifficulty(value);
    let filtered = skills;
    if (value) {
      filtered = filtered.filter(s => s.metadata?.difficulty === value);
    }
    setSkills(filtered);
  };

  const getAgentNames = (agentIds: string[]) => {
    if (!agentIds || agentIds.length === 0) return [];
    return agentIds.map(id => {
      const agent = agentRegistry.find(a => a.id === id);
      return agent ? agent.name : id;
    }).slice(0, 3);
  };

  const handleCreate = () => {
    setEditingSkill(null);
    form.resetFields();
    setActiveTab('basic');
    setModalVisible(true);
  };

  const handleEdit = (record: Skill) => {
    setEditingSkill(record);
    form.setFieldsValue({
      ...record,
      execution: record.execution || {
        enabled: true,
        prompt_template: PROMPT_TEMPLATES[record.process_group] || PROMPT_TEMPLATES['启动'],
        input_contract: {
          required: record.inputs || [],
          optional: [],
          validation: 'strict'
        },
        output_schema: {
          type: 'structured_text',
          sections: ['summary', 'steps', 'deliverables', 'risks'],
          format: 'markdown'
        },
        execution_mode: 'interactive',
        timeout_seconds: 300
      }
    });
    setActiveTab('basic');
    setModalVisible(true);
  };

  const handleDelete = async (id: string) => {
    try {
      const res = await axios.delete('/api/v1/skills/' + id);
      if (res.status === 200) {
        message.success('删除成功');
        fetchData(filterGroup, searchText);
      }
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const url = editingSkill ? '/api/v1/skills/' + editingSkill.id : '/api/v1/skills/';
      const method = editingSkill ? 'PUT' : 'POST';
      
      const res = await axios({
        method,
        url,
        data: { ...values, id: editingSkill?.id },
      });
      
      message.success(editingSkill ? '更新成功' : '创建成功');
      setModalVisible(false);
      fetchData(filterGroup, searchText);
    } catch (error) {
      message.error('保存失败');
    }
  };

  // Test Skill execution
  const handleTest = async (skillId: string) => {
    setTestLoading(true);
    setTestResult('');
    setTestModalVisible(true);
    
    try {
      const res = await axios.post(`/api/v1/skills/execute/${skillId}`, testInputs);
      setTestResult(res.data.content || JSON.stringify(res.data, null, 2));
    } catch (error: any) {
      setTestResult('Error: ' + (error.response?.data?.detail || error.message));
      message.error('测试执行失败');
    } finally {
      setTestLoading(false);
    }
  };

  const columns: ColumnsType<Skill> = [
    {
      title: 'Skill名称',
      dataIndex: 'name',
      key: 'name',
      width: 150,
      render: (name: string, record: Skill) => (
        <div>
          <div style={{ fontWeight: 500 }}>{name}</div>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.name_en}</Text>
        </div>
      ),
    },
    {
      title: '过程组',
      dataIndex: 'process_group',
      key: 'process_group',
      width: 100,
      render: (group: string) => (
        <Tag color={PROCESS_GROUP_COLORS[group] || 'default'}>{group}</Tag>
      ),
    },
    {
      title: '难度',
      dataIndex: ['metadata', 'difficulty'],
      key: 'difficulty',
      width: 80,
      render: (difficulty: string) => (
        <Tag color={DIFFICULTY_COLORS[difficulty] || 'default'}>{difficulty || '未知'}</Tag>
      ),
    },
    {
      title: '工具数量',
      dataIndex: 'tools',
      key: 'tools',
      width: 100,
      render: (tools: string[]) => (
        <Tag icon={<ToolOutlined />}>{tools?.length || 0}</Tag>
      ),
    },
    {
      title: '关联Agent',
      dataIndex: 'agent_ids',
      key: 'agent_ids',
      width: 120,
      render: (agentIds: string[]) => {
        if (!agentIds || agentIds.length === 0) return <Text type="secondary">-</Text>;
        return (
          <Tooltip title={getAgentNames(agentIds).join(', ')}>
            <Tag color="blue">{agentIds.length}个</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: '执行状态',
      dataIndex: ['execution', 'enabled'],
      key: 'enabled',
      width: 100,
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'default'}>
          {enabled ? '已启用' : '已禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 200,
      render: (_: any, record: Skill) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => {
              setEditingSkill(record);
              setTestInputs({});
              setTestModalVisible(true);
            }}
          >
            测试
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除"
            description="删除后将无法恢复"
            okText="是,删除"
            cancelText="取消"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>
        <CheckCircleOutlined style={{ marginRight: 8, color: '#1890ff' }} />
        PMBOK Skills 智能执行系统
      </Title>
      <Text type="secondary">
        基于PMBOK第6/7版ITTO框架，涵盖{stats?.total || 0}个可执行项目管理Skill · 每个Skill都是独立的AI任务单元
      </Text>

      <Row gutter={[16, 16]} style={{ marginTop: 24, marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总Skill数"
              value={stats?.total || 0}
              prefix={<ToolOutlined />}
              suffix={<Tag color="blue">可执行</Tag>}
            />
          </Card>
        </Col>
        {Object.entries(stats?.by_group || {}).map(([group, count]) => (
          <Col key={group} xs={12} sm={12} lg={6}>
            <Card>
              <Statistic
                title={group + '过程'}
                value={count}
                valueStyle={{ color: '#3f8600' }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Space style={{ marginBottom: 16 }}>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索 Skill..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            onPressEnter={() => handleSearch(searchText)}
            style={{ width: 200 }}
          />
          <Select
            placeholder="过程组"
            value={filterGroup}
            onChange={handleFilterGroup}
            style={{ width: 120 }}
            allowClear
          >
            {groups.map(g => (
              <Option key={g} value={g}>{g}</Option>
            ))}
          </Select>
          <Select
            placeholder="难度"
            value={filterDifficulty}
            onChange={handleFilterDifficulty}
            style={{ width: 100 }}
            allowClear
          >
            <Option value="基础">基础</Option>
            <Option value="中级">中级</Option>
            <Option value="高级">高级</Option>
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建 Skill
          </Button>
        </Space>

        <Table
          columns={columns}
          dataSource={skills}
          loading={loading}
          rowKey="id"
          scroll={{ x: 1000 }}
          size="middle"
          pagination={{ pageSize: 20 }}
        />
      </Card>

      {/* Edit Modal */}
      <Modal
        title={
          <Space>
            <EditOutlined />
            {editingSkill ? `编辑 Skill: ${editingSkill.name}` : '新建 Skill'}
          </Space>
        }
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={900}
        destroyOnClose
        footer={[
          <Button key="cancel" onClick={() => setModalVisible(false)}>
            取消
          </Button>,
          <Button 
            key="apply-template" 
            onClick={() => {
              if (editingSkill?.process_group) {
                const template = PROMPT_TEMPLATES[editingSkill.process_group];
                if (template) {
                  form.setFieldsValue({
                    description: template.replace(/{skill_name}/g, editingSkill.name),
                  });
                  message.success('已应用' + editingSkill.process_group + '过程组模板');
                }
              }
            }}
          >
            应用过程组模板
          </Button>,
          <Button key="submit" type="primary" icon={<CheckCircleOutlined />} onClick={handleSubmit}>
            保存
          </Button>,
        ]}
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <Tabs.TabPane tab={<span><SettingOutlined /> 基本信息</span>} key="basic">
            <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="name" label="Skill名称" rules={[{ required: true }]}>
                    <Input placeholder="请输入Skill中文名称" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="name_en" label="英文名称">
                    <Input placeholder="Enter skill name in English" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="process_group" label="过程组" rules={[{ required: true }]}>
                    <Select placeholder="选择过程组">
                      <Option value="启动">启动</Option>
                      <Option value="规划">规划</Option>
                      <Option value="执行">执行</Option>
                      <Option value="监控">监控</Option>
                      <Option value="结束">结束</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="domain" label="领域">
                    <Input placeholder="如: pmbok" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item 
                name="description" 
                label={
                  <span>
                    AI提示词（核心能力描述）
                    <Tooltip title="这是Skill最强大的部分！用自然语言描述Skill的角色、能力、执行框架和输出标准">
                      <SettingOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                    </Tooltip>
                  </span>
                }
                rules={[{ required: true, message: '请输入AI提示词' }]}
              >
                <TextArea 
                  rows={12} 
                  placeholder={`描述这个Skill的核心能力要求。例如：\n\n你是通维咨询的资深项目经理，精通PMBOK第六/七版知识体系。当前任务是制定项目章程。\n\n## 核心能力要求\n- 深刻理解项目立项流程与授权机制\n- 熟练运用利益相关方分析技术\n- 能够制定清晰的项目章程\n\n## 执行框架\n1. 需求洞察...\n2. 利益相关方识别...\n...`}
                />
              </Form.Item>
              <Alert 
                message="💡 提示：描述字段将成为最强力的AI提示词，直接驱动Skill的执行能力。建议详细描述角色、能力、步骤和输出标准。" 
                type="info" 
                showIcon 
                style={{ marginBottom: 16 }}
              />
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name={['metadata', 'difficulty']} label="难度">
                    <Select placeholder="选择难度">
                      <Option value="基础">基础</Option>
                      <Option value="中级">中级</Option>
                      <Option value="高级">高级</Option>
                    </Select>
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={['metadata', 'estimated_time']} label="预计执行时间">
                    <Input placeholder="如: 30分钟" />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane tab={<span><RobotOutlined /> 执行配置</span>} key="execution">
            <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item 
                    name={['execution', 'enabled']} 
                    label="启用执行"
                    valuePropName="checked"
                  >
                    <Switch checkedChildren="启用" unCheckedChildren="禁用" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name={['execution', 'execution_mode']} label="执行模式">
                    <Select>
                      <Option value="interactive">交互式（推荐）</Option>
                      <Option value="batch">批量处理</Option>
                      <Option value="async">异步执行</Option>
                    </Select>
                  </Form.Item>
                </Col>
              </Row>
              
              <Form.Item 
                name={['execution', 'prompt_template']} 
                label="Prompt模板（高级配置）"
                extra="使用{skill_name}、{description}、{inputs_str}、{tools_str}等变量"
              >
                <TextArea rows={10} placeholder="Prompt模板内容..." />
              </Form.Item>

              <Divider />
              
              <Title level={5}>输入契约（Input Contract）</Title>
              <Form.Item 
                name={['execution', 'input_contract', 'required']} 
                label="必需输入项"
                extra="逗号分隔，如：商业文件,协议,事业环境因素"
              >
                <Input placeholder="必需输入项" />
              </Form.Item>
              
              <Form.Item 
                name={['execution', 'input_contract', 'optional']} 
                label="可选输入项"
                extra="逗号分隔，如：context,prefereces"
              >
                <Input placeholder="可选输入项" />
              </Form.Item>
              
              <Form.Item 
                name={['execution', 'input_contract', 'validation']} 
                label="验证模式"
              >
                <Select>
                  <Option value="strict">严格模式（必需项缺失时报错）</Option>
                  <Option value="lenient">宽松模式（自动填充默认值）</Option>
                  <Option value="auto">自动模式（根据上下文判断）</Option>
                </Select>
              </Form.Item>

              <Divider />
              
              <Title level={5}>输出Schema</Title>
              <Form.Item 
                name={['execution', 'output_schema', 'type']} 
                label="输出类型"
              >
                <Select>
                  <Option value="structured_text">结构化文本（推荐）</Option>
                  <Option value="markdown">Markdown格式</Option>
                  <Option value="json">JSON格式</Option>
                  <Option value="html">HTML格式</Option>
                </Select>
              </Form.Item>
              
              <Form.Item 
                name={['execution', 'output_schema', 'sections']} 
                label="输出章节"
                extra="逗号分隔，如：summary,steps,deliverables,risks"
              >
                <Input placeholder="输出章节" />
              </Form.Item>
              
              <Form.Item 
                name={['execution', 'timeout_seconds']} 
                label="超时时间（秒）"
              >
                <InputNumber min={30} max={600} defaultValue={300} />
              </Form.Item>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane tab={<span><CodeOutlined /> 关联配置</span>} key="relations">
            <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
              <Form.Item 
                name={['metadata', 'tags']} 
                label="标签"
                extra="逗号分隔的标签，用于检索和分类"
              >
                <Input placeholder="如：启动,章程,授权" />
              </Form.Item>
              
              <Divider />
              
              <Title level={5}>关联Agent</Title>
              <Form.Item label="可用Agent">
                <Select 
                  mode="multiple"
                  placeholder="选择关联Agent"
                  options={agentRegistry.map(a => ({
                    value: a.id,
                    label: `${a.name} (${a.id})`
                  }))}
                />
              </Form.Item>
              <Text type="secondary">
                关联Agent后，Skill可以直接调用这些Agent执行具体任务
              </Text>
            </Form>
          </Tabs.TabPane>
        </Tabs>
      </Modal>

      {/* Test Execution Modal */}
      <Modal
        title={<span><PlayCircleOutlined /> 测试执行 Skill: {editingSkill?.name}</span>}
        open={testModalVisible}
        onOk={() => handleTest(editingSkill?.id || '')}
        onCancel={() => setTestModalVisible(false)}
        width={800}
        confirmLoading={testLoading}
        footer={[
          <Button key="cancel" onClick={() => setTestModalVisible(false)}>
            关闭
          </Button>,
          <Button 
            key="test" 
            type="primary" 
            icon={<PlayCircleOutlined />}
            onClick={() => handleTest(editingSkill?.id || '')}
            loading={testLoading}
          >
            执行测试
          </Button>,
        ]}
      >
        {editingSkill?.execution?.input_contract?.required && (
          <Alert
            message="必需输入项"
            description={editingSkill.execution.input_contract.required.join(', ')}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        
        <Form layout="vertical">
          {editingSkill?.inputs?.map((input, idx) => (
            <Form.Item key={idx} label={input}>
              <Input
                placeholder={`请输入${input}...`}
                value={testInputs[input] || ''}
                onChange={e => setTestInputs({...testInputs, [input]: e.target.value})}
              />
            </Form.Item>
          ))}
        </Form>

        <Divider />
        
        <Title level={5}>执行结果</Title>
        <Spin spinning={testLoading}>
          {testResult ? (
            <div style={{ 
              background: '#f5f5f5', 
              padding: 16, 
              borderRadius: 4,
              maxHeight: 400,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              fontFamily: 'monospace',
              fontSize: 13,
            }}>
              {testResult}
            </div>
          ) : (
            <Text type="secondary">点击"执行测试"按钮运行Skill</Text>
          )}
        </Spin>
      </Modal>
    </div>
  );
};

export default SkillsManagementPage;
