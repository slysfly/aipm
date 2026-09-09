import React, { useEffect, useState } from "react";
import { App, Card, Row, Col, Statistic, Spin, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { getDashboardSummary } from "../../api/ucm";

const { Title } = Typography;

const OperationDashboard: React.FC = () => {
  const { message } = App.useApp();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await getDashboardSummary();
      setData(res || {});
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载失败");
      setData(null);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const items = [
    { title: "组织总数", value: data?.org_total, color: "#1677ff" },
    { title: "活跃组织", value: data?.org_active, color: "#52c41a" },
    { title: "即将到期组织", value: data?.org_expiring, color: "#faad14" },
    { title: "总收入", value: data?.revenue, color: "#1677ff", prefix: "¥" },
    { title: "退款总额", value: data?.refund_total, color: "#ff4d4f", prefix: "¥" },
    { title: "待审退款", value: data?.refund_pending, color: "#faad14" },
    { title: "用户总数", value: data?.user_total, color: "#722ed1" },
  ];

  return (
    <div>
      <Title level={3}>运营看板</Title>
      <Card title="运营概览" data-tour="admin-dash-card" extra={<ReloadOutlined style={{ cursor: "pointer" }} onClick={load} />}>
        <Spin spinning={loading}>
          <Row gutter={[16, 16]}>
            {items.map((it) => (
              <Col xs={12} sm={8} md={6} key={it.title}>
                <Card size="small">
                  <Statistic
                    title={it.title}
                    value={it.value ?? 0}
                    prefix={it.prefix}
                    valueStyle={{ color: it.color }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
        </Spin>
      </Card>
    </div>
  );
};

export default OperationDashboard;
