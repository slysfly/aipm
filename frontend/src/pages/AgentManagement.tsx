import React, { useState, useEffect } from 'react';
import { Table, Card, Statistic, Row, Col, Tag, Input, Button, Space, Typography, Alert } from 'antd';
import { ToolOutlined } from '@ant-design/icons';
import { agentV2Api } from '../api';

const { Text } = Typography;
const { Search } = Input;

interface Agent {
  id: string;
  name: string;
  name_en: string;
  domain: string;
  pmbok_process: string;
  description: string;
  type: string;
}

interface Domain {
  name: string;
  count: number;
  agents: Array<{ id: string; name: string }>;
}

const DOMAIN_COLORS: Record<string, string> = {
  stakeholder: 'purple',
  schedule: 'blue',
  resource: 'green',
  cost: 'orange',
  quality: 'cyan',
  risk: 'red',
  procurement: 'volcano',
  communication: 'magenta',
};

const AgentManagement: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);

  useEffect(() => {
    loadAgents();
    loadDomains();
    loadStats();
  }, []);

  const loadAgents = async () => {
    try {
      setLoading(true);
      const res = await agentV2Api.list();
      if (res?.success) {
        setAgents(res.agents || []);
      }
    } catch (e) {
      console.error('Failed to load agents', e);
    } finally {
      setLoading(false);
    }
  };

  const loadDomains = async () => {
    try {
      const res = await agentV2Api.domains();
      if (res?.success) {
        setDomains(res.domains || []);
      }
    } catch (e) {
      console.error('Failed to load domains', e);
    }
  };

  const loadStats = async () => {
    try {
      const res = await agentV2Api.stats();
      if (res?.success) {
        setStats(res.data);
      }
    } catch (e) {
      console.error('Failed to load stats', e);
    }
  };

  const filteredAgents = agents.filter(agent => {
    const matchSearch = !searchText || 
      agent.name.includes(searchText) || 
      agent.name_en.toLowerCase().includes(searchText.toLowerCase()) ||
      agent.id.toLowerCase().includes(searchText.toLowerCase());
    const matchDomain = !selectedDomain || agent.domain === selectedDomain;
    return matchSearch && matchDomain;
  });

  const columns = [
    {
      title: 'Agent ID',
      dataIndex: 'id',
      key: 'id',
      width: 280,
      render: (id: string) => <Text code style={{ fontSize: 12 }}>{id}</Text>,
    },
    {
      title: 'Name CN',
      dataIndex: 'name',
      key: 'name',
      width: 120,
      render: (name: string) => <Text strong>{name}</Text>,
    },
    {
      title: 'Name EN',
      dataIndex: 'name_en',
      key: 'name_en',
      width: 200,
      ellipsis: true,
    },
    {
      title: 'Domain',
      dataIndex: 'domain',
      key: 'domain',
      width: 120,
      render: (domain: string) => (
        <Tag color={DOMAIN_COLORS[domain] || 'default'}>
          {domain}
        </Tag>
      ),
    },
    {
      title: 'PMBOK Process',
      dataIndex: 'pmbok_process',
      key: 'pmbok_process',
      ellipsis: true,
      render: (process: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>{process}</Text>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string) => (
        <Text type="secondary">{desc?.substring(0, 60)}{desc?.length > 60 ? '...' : ''}</Text>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={24}>
          <Card
            title={
              <Space>
                <ToolOutlined style={{ color: '#1890ff' }} />
                <span>PMBOK Agent Expert Library v2.0</span>
              </Space>
            }
            extra={
              <Space>
                <Text type="secondary">Total {stats?.total || agents.length} expert agents</Text>
                <Button type="primary" size="small" onClick={loadAgents} loading={loading}>
                  Refresh
                </Button>
              </Space>
            }
          >
            <Row gutter={16} style={{ marginBottom: 16 }}>
              {stats?.by_domain && Object.entries(stats.by_domain).map(([domain, count]: any) => (
                <Col key={domain}>
                  <Card size="small" style={{ minWidth: 140 }}>
                    <Statistic
                      title={domain}
                      value={count}
                      suffix=" agents"
                      valueStyle={{ color: DOMAIN_COLORS[domain] === 'red' ? '#ff4d4f' : '#3f7afe' }}
                    />
                  </Card>
                </Col>
              ))}
            </Row>
            
            <Space style={{ marginBottom: 16 }}>
              <Search
                placeholder="Search agent name or ID..."
                allowClear
                style={{ width: 300 }}
                onSearch={setSearchText}
                onChange={(e) => setSearchText(e.target.value)}
              />
              <Button
                type={selectedDomain === null ? 'primary' : 'default'}
                onClick={() => setSelectedDomain(null)}
              >
                All
              </Button>
              {domains.map((domain: Domain) => (
                <Button
                  key={domain.name}
                  type={selectedDomain === domain.name ? 'primary' : 'default'}
                  onClick={() => setSelectedDomain(domain.name === selectedDomain ? null : domain.name)}
                >
                  {domain.name} ({domain.count})
                </Button>
              ))}
            </Space>

            <Table
              dataSource={filteredAgents}
              columns={columns}
              rowKey="id"
              loading={loading}
              pagination={{
                pageSize: 20,
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => 'Total ${total' + ' agents',
              }}
              scroll={{ x: 1200 }}
              size="middle"
            />
          </Card>
        </Col>
      </Row>

      <Alert
        message="v2.0 Architecture Overview"
        description={
          <div>
            <p><strong>Core Design Philosophy:</strong></p>
            <ul>
              <li>Each PMBOK tool/technique is an independent expert agent</li>
              <li>Fully based on PMBOK 6th + 7th Edition standards</li>
              <li>Supports ITTO (Inputs/Tools & Techniques/Outputs) structured configuration</li>
              <li>Integrated case library intelligent recommendation</li>
              <li>Built-in brand compliance checking</li>
            </ul>
            <p><strong>Current Domain Coverage:</strong></p>
            <Space wrap>
              {Object.entries(stats?.by_domain || {}).map(([domain, count]: any) => (
                <Tag key={domain} color={DOMAIN_COLORS[domain] || 'default'}>
                  {domain}: {count}
                </Tag>
              ))}
            </Space>
          </div>
        }
        type="info"
        showIcon
        style={{ marginTop: 16 }}
      />
    </div>
  );
};

export default AgentManagement;
