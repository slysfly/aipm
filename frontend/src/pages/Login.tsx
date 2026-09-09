import React, { useState } from "react";
import { Form, Input, Button, Typography, message } from "antd";
import { MailOutlined, LockOutlined, ArrowRightOutlined, RobotOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../store/AuthContext";
import { motion } from "framer-motion";
import { useBrandLogo } from "../hooks/useBrandLogo";

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { logoUrl, hasLogo } = useBrandLogo();
  const { login } = useAuth();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      navigate("/", { replace: true });
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "登录失败，请检查用户名和密码");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      {/* 左侧品牌展示区 */}
      <motion.div
        initial={{ opacity: 0, x: -60 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        style={styles.brandSide}
      >
        {/* 动态粒子背景 */}
        <div style={styles.particleBg}>
          {Array.from({ length: 20 }).map((_, i) => (
            <motion.div
              key={i}
              style={{
                ...styles.particle,
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                width: Math.random() * 6 + 2,
                height: Math.random() * 6 + 2,
              }}
              animate={{
                y: [0, -30, 0],
                opacity: [0.2, 0.8, 0.2],
              }}
              transition={{
                duration: 3 + Math.random() * 4,
                repeat: Infinity,
                delay: Math.random() * 3,
                ease: "easeInOut",
              }}
            />
          ))}
        </div>

        {/* 品牌LOGO - PMI中国AI项目管理社区元素 */}
        <motion.div
          style={styles.logoContainer}
          whileHover={{ scale: 1.05 }}
        >
          <div style={{ ...styles.logoIcon, overflow: "hidden" }}>
            {hasLogo && logoUrl ? (
              <img src={logoUrl} alt="Logo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            ) : (
              <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
                <line x1="6" y1="18" x2="18" y2="6"/>
              </svg>
            )}
          </div>
          <div>
            <div style={styles.brandName}>PMI中国 AIPM管理系统</div>
            <div style={styles.brandTagline}>全球标准 · AI驱动 · PMI中国AI项目管理社区</div>
          </div>
        </motion.div>

        {/* 核心价值展示 */}
        <div style={styles.valueProps}>
          {[
            { number: "85+", label: "AI 智能体" },
            { number: "PMI", label: "主流知识体系" },
            { number: "∞", label: "自定义工作流" },
            { number: "3", label: "三权用户管理" },
          ].map((item, i) => (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 + i * 0.2, duration: 0.6 }}
              style={styles.valueItem}
            >
              <div style={styles.valueNumber}>{item.number}</div>
              <div style={styles.valueLabel}>{item.label}</div>
            </motion.div>
          ))}
        </div>

        {/* 底部引用 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5, duration: 0.8 }}
          style={styles.quote}
        >
          <Text style={{ color: "rgba(255,255,255,0.6)", fontSize: 13, fontStyle: "italic" }}>
            © 2026 北京通维管理咨询有限公司（PMI中国授权机构） 版权所有
          </Text>
        </motion.div>
      </motion.div>

      {/* 右侧登录表单区 */}
      <motion.div
        initial={{ opacity: 0, x: 60 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, ease: "easeOut", delay: 0.2 }}
        style={styles.formSide}
      >
        <div style={styles.formContainer}>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.5 }}
          >
            <Title level={2} style={{ margin: 0, fontWeight: 700 }}>
              欢迎使用 PMI中国 AIPM管理系统
            </Title>
            <Text type="secondary" style={{ display: "block", marginTop: 8, marginBottom: 32, fontSize: 15 }}>
              PMI中国AI项目管理社区 · 全球标准 · AI 驱动
            </Text>
          </motion.div>

          <Form
            name="login"
            layout="vertical"
            onFinish={onFinish}
            autoComplete="off"
            requiredMark={false}
            size="large"
          >
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6, duration: 0.5 }}
            >
              <Form.Item
                label="用户名"
                name="username"
                rules={[{ required: true, message: "请输入用户名" }]}
              >
                <Input
                  prefix={<MailOutlined style={{ color: "#94A3B8" }} />}
                  placeholder="admin"
                  style={{ borderRadius: 10 }}
                />
              </Form.Item>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.5 }}
            >
              <Form.Item
                label="密码"
                name="password"
                rules={[{ required: true, message: "请输入密码" }]}
              >
                <Input.Password
                  prefix={<LockOutlined style={{ color: "#94A3B8" }} />}
                  placeholder="请输入密码"
                  style={{ borderRadius: 10 }}
                />
              </Form.Item>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.9, duration: 0.5 }}
            >
              <Form.Item style={{ marginTop: 32 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  block
                  size="large"
                  style={{
                    height: 48,
                    borderRadius: 12,
                    fontWeight: 600,
                    fontSize: 16,
                    boxShadow: "0 4px 14px 0 rgba(79, 70, 229, 0.35)",
                  }}
                >
                  登录系统
                  <ArrowRightOutlined style={{ marginLeft: 8 }} />
                </Button>
              </Form.Item>
            </motion.div>
          </Form>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.2, duration: 0.5 }}
          >
            <Text type="secondary" style={{ fontSize: 12, display: "block", textAlign: "center" }}>
              PMI中国 项目管理 v1.0.0 · PMI中国AI项目管理社区
            </Text>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    height: "100vh",
    overflow: "hidden",
  },
  brandSide: {
    flex: 1.2,
    background: "linear-gradient(135deg, #0F172A 0%, #1E1B4B 50%, #0F172A 100%)",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    alignItems: "center",
    padding: 60,
    position: "relative",
    overflow: "hidden",
  },
  particleBg: {
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
  },
  particle: {
    position: "absolute",
    borderRadius: "50%",
    background: "rgba(99, 102, 241, 0.6)",
  },
  logoContainer: {
    display: "flex",
    alignItems: "center",
    gap: 16,
    marginBottom: 60,
    zIndex: 1,
    cursor: "pointer",
  },
  logoIcon: {
    width: 56,
    height: 56,
    borderRadius: 16,
    background: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    boxShadow: "0 8px 24px rgba(79, 70, 229, 0.4)",
  },
  brandName: {
    fontSize: 24,
    fontWeight: 800,
    color: "#FFFFFF",
    letterSpacing: "0.02em",
  },
  brandTagline: {
    fontSize: 13,
    color: "rgba(255,255,255,0.5)",
    marginTop: 2,
  },
  valueProps: {
    display: "flex",
    gap: 32,
    flexWrap: "wrap",
    justifyContent: "center",
    zIndex: 1,
  },
  valueItem: {
    textAlign: "center",
  },
  valueNumber: {
    fontSize: 36,
    fontWeight: 800,
    background: "linear-gradient(135deg, #6366F1 0%, #06B6D4 100%)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
    backgroundClip: "text",
    lineHeight: 1.2,
  },
  valueLabel: {
    fontSize: 13,
    color: "rgba(255,255,255,0.5)",
    marginTop: 4,
  },
  quote: {
    position: "absolute",
    bottom: 40,
    zIndex: 1,
  },
  formSide: {
    flex: 0.8,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#F8FAFC",
  },
  formContainer: {
    width: 380,
    padding: 40,
  },
};

export default Login;
