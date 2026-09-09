import React from "react";
import { Button, Typography, Space } from "antd";
import { HomeOutlined, ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

const { Title, Text } = Typography;

const NotFound: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div style={{
      minHeight: "60vh",
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      alignItems: "center",
      textAlign: "center",
      padding: 48,
    }}>
      {/* 装饰性 SVG */}
      <svg viewBox="0 0 240 160" width="200" height="133" style={{ marginBottom: 24 }}>
        <rect x="0" y="0" width="240" height="160" rx="12" fill="#F1F5F9" />
        <circle cx="120" cy="70" r="36" fill="none" stroke="#CBD5E1" strokeWidth="3" strokeDasharray="6 4" />
        <text x="120" y="78" textAnchor="middle" fill="#94A3B8" fontSize="32" fontWeight="700" fontFamily="Inter, sans-serif">404</text>
        <line x1="72" y1="100" x2="168" y2="100" stroke="#E2E8F0" strokeWidth="2" />
        <line x1="60" y1="110" x2="180" y2="110" stroke="#E2E8F0" strokeWidth="2" />
        {/* 小图标记 */}
        <circle cx="84" cy="125" r="4" fill="#CBD5E1" />
        <circle cx="96" cy="125" r="4" fill="#CBD5E1" />
        <circle cx="108" cy="125" r="4" fill="#CBD5E1" />
        <line x1="116" y1="125" x2="160" y2="125" stroke="#CBD5E1" strokeWidth="2" strokeLinecap="round" />
        <path d="M160 125 L166 120 L172 125" fill="none" stroke="#CBD5E1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>

      <Title level={2} style={{ margin: "0 0 8px", color: "#0F172A" }}>
        页面未找到
      </Title>
      <Text type="secondary" style={{ fontSize: 15, maxWidth: 400, marginBottom: 28 }}>
        您访问的页面不存在或已被移除。请检查链接是否正确，或返回首页继续使用。
      </Text>

      <Space size="middle">
        <Button
          type="primary"
          icon={<HomeOutlined />}
          size="large"
          style={{ borderRadius: 10, fontWeight: 600 }}
          onClick={() => navigate("/", { replace: true })}
        >
          返回首页
        </Button>
        <Button
          icon={<ArrowLeftOutlined />}
          size="large"
          style={{ borderRadius: 10 }}
          onClick={() => navigate(-1)}
        >
          后退一步
        </Button>
      </Space>
    </div>
  );
};

export default NotFound;
