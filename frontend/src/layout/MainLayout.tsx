import React, { useState, useEffect } from "react";
import { Layout, Avatar, Dropdown, Badge, Button, Tooltip, Space, Typography } from "antd";
import {
  DashboardOutlined, ProjectOutlined, ProfileOutlined, RobotOutlined,
  BarChartOutlined, ThunderboltOutlined, ApiOutlined, LinkOutlined,
  BellOutlined, CloudServerOutlined, SettingOutlined, LogoutOutlined,
  UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined, LayoutOutlined,
  CalendarOutlined, FlagOutlined, PartitionOutlined,
  FundProjectionScreenOutlined, AlertOutlined, SwapOutlined,
  DollarOutlined, AimOutlined,   BranchesOutlined, TeamOutlined, AuditOutlined,
  ApartmentOutlined,
  DatabaseOutlined,
  BookOutlined, ReadOutlined,
  FireOutlined, MoonOutlined, SunOutlined,
} from "@ant-design/icons";
import { useBrandLogo } from "../hooks/useBrandLogo";
import { useAuth } from "../store/AuthContext";
import { useTheme } from "../store/ThemeContext";
import { useTranslation } from "react-i18next";
import i18n, { setLanguage } from "../i18n";
import { notificationApi } from "../api";
import { onDataChanged } from "../realtime/useRealtime";
import { ConnectionStatusBar } from "../realtime/ConnectionStatusBar";
import { ConflictResolver } from "../offline/ConflictResolver";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation, useNavigate } from "react-router-dom";
import PageTour from "../components/PageTour";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const topMenuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "nav.dashboard" },
  { key: "/projects", icon: <ProjectOutlined />, label: "nav.projects" },
  { key: "/tasks", icon: <ProfileOutlined />, label: "nav.tasks" },
  { key: "/kanban", icon: <LayoutOutlined />, label: "nav.kanban" },
  { key: "/portfolio", icon: <FundProjectionScreenOutlined />, label: "nav.portfolio" },
  { key: "/ai-monitor", icon: <BarChartOutlined />, label: "nav.aiMonitor" },
];

const pmbokMenuItems = [
  { key: "/pmbok-skills", icon: <BookOutlined />, label: "PMBOK Skills" },
  { key: "/agents", icon: <RobotOutlined />, label: "Agents" },
  { key: "/workflow", icon: <ApartmentOutlined />, label: "Workflow" },
];

const planMenuItems = [
  { key: "/okrs", icon: <FlagOutlined />, label: "nav.okrs" },
  { key: "/calendar", icon: <CalendarOutlined />, label: "nav.calendar" },
  { key: "/sprints", icon: <BranchesOutlined />, label: "nav.sprints" },
  { key: "/critical-path", icon: <FireOutlined />, label: "nav.criticalPath" },
  { key: "/reports", icon: <BarChartOutlined />, label: "nav.reports" },
];

const twMenuItems = [
  { key: "/evm", icon: <DollarOutlined />, label: "nav.evm" },
  { key: "/risk", icon: <AlertOutlined />, label: "nav.risk" },
  { key: "/changes", icon: <SwapOutlined />, label: "nav.changes" },
  { key: "/resources", icon: <TeamOutlined />, label: "nav.resources" },
];

const toolMenuItems = [
  { key: "/automations", icon: <ThunderboltOutlined />, label: "nav.automations" },
  { key: "/webhooks", icon: <ApiOutlined />, label: "nav.webhooks" },
  { key: "/whiteboard", icon: <PartitionOutlined />, label: "nav.whiteboard" },
  { key: "/knowledge", icon: <DatabaseOutlined />, label: "nav.knowledge" },
  { key: "/notifications", icon: <BellOutlined />, label: "nav.notifications" },
  { key: "/settings", icon: <SettingOutlined />, label: "nav.settings" },
];

const superAdminMenuItems = [
  { key: "/admin/dashboard", icon: <BarChartOutlined />, label: "nav.adminDashboard" },
  { key: "/admin/organizations", icon: <ApartmentOutlined />, label: "nav.organizations" },
  { key: "/admin/users", icon: <TeamOutlined />, label: "nav.users" },
  { key: "/admin/plans", icon: <FundProjectionScreenOutlined />, label: "nav.plans" },
  { key: "/admin/grants", icon: <ApiOutlined />, label: "nav.grants" },
  { key: "/admin/billing", icon: <DollarOutlined />, label: "nav.billing" },
  { key: "/admin/levels", icon: <AimOutlined />, label: "nav.levels" },
];

// \u7528\u6237\u7ba1\u7406\uff08org_admin\uff09\u53ea\u80fd\u770b\u5230\uff1a\u7528\u6237\u7ba1\u7406\u3001\u7528\u6237\u7ea7\u522b\u7ba1\u7406\uff08\u529f\u80fd\u5f00\u901a/\u7ba1\u7406\u6743\u9650\u4ec5\u7cfb\u7edf\u7ba1\u7406\u5458\u53ef\u89c1\uff09
const userAdminMenuItems = [
  { key: "/admin/users", icon: <TeamOutlined />, label: "nav.users" },
  { key: "/admin/levels", icon: <AimOutlined />, label: "nav.levels" },
];

interface MenuGroupProps {
  title: string;
  items: typeof topMenuItems;
  collapsed: boolean;
  selectedKey: string;
  onNavigate: (key: string) => void;
}

const MenuGroup: React.FC<MenuGroupProps> = ({ title, items, collapsed, selectedKey, onNavigate }) => {
  const { t } = useTranslation();
  return (
  <div style={{ marginBottom: 8 }}>
    {!collapsed && (
      <Text style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#475569", display: "block", padding: "8px 16px 4px" }}>
        {title}
      </Text>
    )}
    {items.map((item) => {
      const isSelected = item.key === "/" ? selectedKey === "/" : selectedKey.startsWith(item.key) && item.key !== "/";
      const label = t(item.label);
      return (
        <Tooltip key={item.key} title={collapsed ? label : undefined} placement="right" mouseEnterDelay={0.5}>
          <div
            onClick={() => onNavigate(item.key)}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "8px 16px", margin: "2px 8px",
              borderRadius: 10, cursor: "pointer",
              background: isSelected ? "#4F46E520" : "transparent",
              color: isSelected ? "#6366F1" : "#94A3B8",
              fontWeight: isSelected ? 600 : 400,
              fontSize: 13,
              transition: "all 0.15s ease",
              justifyContent: collapsed ? "center" : "flex-start",
            }}
            onMouseEnter={(e) => { if (!isSelected) { e.currentTarget.style.background = "rgba(255,255,255,0.06)"; e.currentTarget.style.color = "#fff"; } }}
            onMouseLeave={(e) => { if (!isSelected) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#94A3B8"; } }}
          >
            <span style={{ fontSize: 16, display: "flex" }}>{item.icon}</span>
            {!collapsed && (
              <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {label}
              </span>
            )}
          </div>
        </Tooltip>
      );
    })}
  </div>
  );
};

const MainLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [unread, setUnread] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { logoUrl, hasLogo } = useBrandLogo();
  const { mode, toggle } = useTheme();
  const { t } = useTranslation();

  const refreshUnread = () =>
    notificationApi.unreadCount().then(r => setUnread(r?.count ?? 0)).catch(() => {});

  useEffect(() => {
    refreshUnread();
    // \u5b9e\u65f6\uff1a\u4efb\u610f\u6570\u636e\u53d8\u66f4\uff08\u4efb\u52a1/\u9879\u76ee/\u901a\u77e5\u7b49\uff09\u540e\u5237\u65b0\u672a\u8bfb\u89d2\u6807
    const off = onDataChanged(null, () => refreshUnread());
    // \u515c\u5e95\uff1a\u6bcf 45s \u8f6e\u8be2\u4e00\u6b21\uff0c\u786e\u4fdd\u5f31\u7f51/\u65ad\u7ebf\u91cd\u8fde\u671f\u95f4\u4e5f\u4e0d\u6f0f
    const timer = setInterval(refreshUnread, 45000);
    return () => { off(); clearInterval(timer); };
  }, []);

  const selectedKey = (() => {
    const allItems = [...topMenuItems, ...pmbokMenuItems, ...planMenuItems, ...twMenuItems, ...toolMenuItems, ...superAdminMenuItems, ...userAdminMenuItems];
    const matched = allItems.find(i => i.key !== "/" && location.pathname.startsWith(i.key));
    return matched?.key || (location.pathname === "/" ? "/" : "/");
  })();

  // \u8fd0\u8425\u7ba1\u7406\u677f\u5757\uff1a\u6839\u636e\u7ba1\u7406\u89d2\u8272\u663e\u793a\u4e0d\u540c\u83dc\u5355
  const isSuper = !!user?.is_superuser;
  const isOrgAdmin = !!user?.is_org_admin && !user?.is_superuser;
  const adminItems = isSuper ? superAdminMenuItems : isOrgAdmin ? userAdminMenuItems : null;
  const adminTitle = isSuper ? t("nav.adminDashboard") : t("nav.users");

  const userMenu = {
    items: [
      { key: "profile", icon: <UserOutlined />, label: "\u4e2a\u4eba\u4fe1\u606f" },
      { key: "logout", icon: <LogoutOutlined />, label: "\u9000\u51fa\u767b\u5f55", danger: true },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === "logout") { logout(); navigate("/login"); }
    },
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <ConnectionStatusBar />
      <ConflictResolver />
      <Sider
        collapsible collapsed={collapsed} onCollapse={setCollapsed}
        theme="dark" width={240} collapsedWidth={60} trigger={null}
        style={{
          background: "linear-gradient(180deg, #0F172A 0%, #0B1120 100%)",
          borderRight: "1px solid #1E293B",
          height: "100vh", position: "sticky", top: 0, left: 0,
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}
      >
        <div onClick={() => navigate("/")} style={{
          height: 64, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: collapsed ? "center" : "flex-start",
          padding: collapsed ? 0 : "0 16px", cursor: "pointer", borderBottom: "1px solid #1E293B", gap: 10,
        }}>
          <div style={{ width: 32, height: 32, borderRadius: 10, background: "linear-gradient(135deg, #0891B2 0%, #06B6D4 100%)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, position: "relative", overflow: "hidden" }}>
            {hasLogo && logoUrl ? (
              <img src={logoUrl} alt="Logo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            ) : (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
                <line x1="6" y1="18" x2="18" y2="6"/>
              </svg>
            )}
          </div>
          {!collapsed && (
            <div>
              <div style={{ color: "#F1F5F9", fontWeight: 700, fontSize: 15, lineHeight: 1.2 }}>PMI中国 项目管理</div>
              <div style={{ color: "#475569", fontSize: 10, lineHeight: 1.2 }}>Powered by PMI中国</div>
            </div>
          )}
        </div>
        <div className="sider-scroll" style={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden", padding: "8px 0", overscrollBehavior: "contain" }}>
          <MenuGroup title="\u6982\u89c8" items={topMenuItems} collapsed={collapsed} selectedKey={selectedKey} onNavigate={navigate} />
          <MenuGroup title="\u0050\u004d\u0042\u004f\u004b\u0020\u667a\u80fd\u4f53" items={pmbokMenuItems} collapsed={collapsed} selectedKey={selectedKey} onNavigate={navigate} />
          <MenuGroup title="\u89c4\u5212" items={planMenuItems} collapsed={collapsed} selectedKey={selectedKey} onNavigate={navigate} />
          <MenuGroup title="\u7ba1\u63a7\u4f53\u7cfb" items={twMenuItems} collapsed={collapsed} selectedKey={selectedKey} onNavigate={navigate} />
          <MenuGroup title="\u5de5\u5177" items={toolMenuItems} collapsed={collapsed} selectedKey={selectedKey} onNavigate={navigate} />
          {adminItems && (
            <MenuGroup title={adminTitle} items={adminItems} collapsed={collapsed} selectedKey={selectedKey} onNavigate={navigate} />
          )}
        </div>
      </Sider>

      <Layout>
        <Header style={{
          background: "rgba(255,255,255,0.8)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
          padding: "0 24px", display: "flex", alignItems: "center", justifyContent: "space-between",
          borderBottom: "1px solid #E2E8F0", height: 64, position: "sticky", top: 0, zIndex: 100,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed(!collapsed)} style={{ fontSize: 16, color: "#64748B" }} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Tooltip title="\u672c\u9875\u64cd\u4f5c\u6559\u7a0b">
              <Button type="text" icon={<BookOutlined style={{ fontSize: 18 }} />} onClick={() => window.dispatchEvent(new CustomEvent("tw:open-tour"))} style={{ color: "#64748B" }} />
            </Tooltip>
            <Tooltip title={mode === "dark" ? "\u5207\u6362\u6d45\u8272\u6a21\u5f0f" : "\u5207\u6362\u6df1\u8272\u6a21\u5f0f"}>
              <Button type="text" icon={mode === "dark" ? <SunOutlined style={{ fontSize: 18 }} /> : <MoonOutlined style={{ fontSize: 18 }} />} onClick={toggle} style={{ color: "#64748B" }} />
            </Tooltip>
            <Tooltip title={t("lang.switch")}>
              <Button type="text" onClick={() => setLanguage(i18n.language === "zh" ? "en" : "zh")}
                style={{ color: "#64748B", fontSize: 13, fontWeight: 600, width: 44 }}>
                {i18n.language === "zh" ? "EN" : "\u4e2d"}
              </Button>
            </Tooltip>
            <Badge count={unread} size="small" offset={[-2, 2]}>
              <Button type="text" icon={<BellOutlined style={{ fontSize: 18 }} />} onClick={() => navigate("/notifications")} style={{ color: "#64748B" }} />
            </Badge>
            <Dropdown menu={userMenu} placement="bottomRight">
              <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", padding: "4px 8px", borderRadius: 8, transition: "all 0.2s" }}
                onMouseEnter={(e) => e.currentTarget.style.background = "#F1F5F9"}
                onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
              >
                <Avatar icon={<UserOutlined />} src={user?.avatar_url} style={{ background: "#4F46E5" }} />
                <span style={{ fontSize: 13, fontWeight: 500, color: "#0F172A" }}>{user?.full_name || user?.username || "\u7528\u6237"}</span>
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ margin: 0, background: "var(--content-bg, #F8FAFC)", minHeight: "calc(100vh - 64px)" }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              style={{ padding: 24 }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </Content>
      </Layout>
      <PageTour />
    </Layout>
  );
};

export default MainLayout;
