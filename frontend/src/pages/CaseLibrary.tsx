import React, { useState, useEffect } from "react";
import {
  Card, Typography, Select, Row, Col, List, Tag, Button, Space,
  Input, Spin, Empty, App, Modal, Divider, Statistic,
} from "antd";
import {
  BookOutlined, SearchOutlined, TeamOutlined,
  ToolOutlined, FileTextOutlined, CheckCircleOutlined,
} from "@ant-design/icons";
import { caseApi } from "../api";
import { motion } from "framer-motion";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface CaseItem {
  id: string;
  name: string;
  industry: string;
  match_score: number;
  filename: string;
}

interface IndustrySummary {
  industry: string;
  case_count: number;
  cases: string[];
}

const CaseLibrary: React.FC = () => {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [industries, setIndustries] = useState<IndustrySummary[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState<string>("");
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [searchText, setSearchText] = useState("");
  const [selectedCase, setSelectedCase] = useState<CaseItem | null>(null);
  const [caseDetail, setCaseDetail] = useState<string>("");
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    loadIndustries();
  }, []);

  const loadIndustries = async () => {
    try {
      const data = await caseApi.industries();
      setIndustries(data?.industries || []);
    } catch (error) {
      message.error("加载行业列表失败");
    }
  };

  const handleIndustryChange = async (industry: string) => {
    setSelectedIndustry(industry);
    if (!industry) {
      setCases([]);
      return;
    }
    setLoading(true);
    try {
      const data = await caseApi.similar({ industry, top_k: 50 });
      setCases(data || []);
    } catch (error) {
      message.error("加载案例失败");
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (caseItem: CaseItem) => {
    setSelectedCase(caseItem);
    setDetailLoading(true);
    setCaseDetail("");
    try {
      const data = await caseApi.detail(caseItem.id);
      if (data?.content) {
        setCaseDetail(data.content);
      } else {
        setCaseDetail("案例内容加载中...");
      }
    } catch (error) {
      message.error("加载案例详情失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const filteredCases = cases.filter(c =>
    c.name.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div style={{ padding: "24px", background: "#f5f5f5", minHeight: "100vh" }}>
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <Card style={{ marginBottom: 24, borderRadius: 16 }}>
          <Row align="middle" gutter={[16, 16]}>
            <Col>
              <BookOutlined style={{ fontSize: 32, color: "#4F46E5" }} />
            </Col>
            <Col flex="auto">
              <Title level={3} style={{ margin: 0 }}>案例库智能推荐</Title>
              <Text type="secondary">基于OCE-TRANSFORM™方法论，匹配1,414个真实项目案例</Text>
            </Col>
            <Col>
              <Statistic
                title="案例总数"
                value={industries.reduce((sum, ind) => sum + ind.case_count, 0)}
                suffix="个"
                valueStyle={{ color: "#4F46E5" }}
              />
            </Col>
          </Row>
        </Card>

        <Row gutter={[16, 16]}>
          <Col span={24} lg={6}>
            <Card title="行业分类" styles={{ body: { padding: "16px" } }}>
              <Select
                placeholder="选择行业"
                value={selectedIndustry}
                onChange={handleIndustryChange}
                style={{ width: "100%" }}
                size="large"
                showSearch
                optionFilterProp="children"
              >
                {industries.map(ind => (
                  <Select.Option key={ind.industry} value={ind.industry}>
                    {ind.industry.replace(/^M\d+_/, "")} ({ind.case_count}个)
                  </Select.Option>
                ))}
              </Select>
            </Card>

            <Card title="筛选工具" style={{ marginTop: 16 }} styles={{ body: { padding: "16px" } }}>
              <Space direction="vertical" style={{ width: "100%" }}>
                <Input
                  prefix={<SearchOutlined />}
                  placeholder="搜索案例名称..."
                  value={searchText}
                  onChange={e => setSearchText(e.target.value)}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  共 {filteredCases.length} 个案例
                </Text>
              </Space>
            </Card>
          </Col>

          <Col span={24} lg={18}>
            <Card
              title={<Space><FileTextOutlined />推荐案例</Space>}
              extra={
                <Tag color="blue">
                  {selectedIndustry ? selectedIndustry.replace(/^M\d+_/, "") : "全部行业"}
                </Tag>
              }
              loading={loading}
              styles={{ body: { padding: "16px" } }}
            >
              {filteredCases.length === 0 ? (
                <Empty description="请选择行业查看案例" />
              ) : (
                <List
                  grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 2 }}
                  dataSource={filteredCases}
                  renderItem={item => (
                    <List.Item>
                      <Card
                        hoverable
                        onClick={() => handleViewDetail(item)}
                        styles={{ body: { padding: "16px" } }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                          <div style={{ flex: 1 }}>
                            <Title level={5} style={{ margin: "0 0 8px 0", lineHeight: 1.4 }}>
                              {item.name.replace(/^[^_]+_/, "")}
                            </Title>
                            <Space wrap>
                              <Tag color="purple">匹配度: {item.match_score}%</Tag>
                              <Tag color="green">参考价值高</Tag>
                            </Space>
                          </div>
                          <ToolOutlined style={{ fontSize: 20, color: "#4F46E5", marginLeft: 8 }} />
                        </div>
                      </Card>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </Col>
        </Row>

        <Modal
          title={<Space><CheckCircleOutlined style={{ color: "#4F46E5" }} />案例详情</Space>}
          open={!!selectedCase}
          onCancel={() => setSelectedCase(null)}
          footer={null}
          width={900}
          styles={{ body: { maxHeight: "70vh", overflow: "auto" } }}
        >
          {detailLoading ? (
            <div style={{ textAlign: "center", padding: 40 }}>
              <Spin size="large" />
            </div>
          ) : caseDetail ? (
            <div dangerouslySetInnerHTML={{ __html: caseDetail }} />
          ) : (
            <Empty description="暂无详细内容" />
          )}
        </Modal>
      </motion.div>
    </div>
  );
};

export default CaseLibrary;
