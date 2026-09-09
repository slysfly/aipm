import type { ThemeConfig } from "antd";
import { theme as antdTheme } from "antd";

// PMI中国AI项目管理社区 · 品牌设计系统
// © PMI中国AI项目管理社区 · 对标 Monday.com / Linear 的设计质量

export const BRAND_COLORS = {
  primary: "#4F46E5",        // 靛蓝 - 主色
  primaryLight: "#6366F1",   // 浅靛蓝
  primaryDark: "#3730A3",    // 深靛蓝
  secondary: "#06B6D4",      // 青色 - 辅助色
  accent: "#8B5CF6",         // 紫色 - 强调色
  success: "#10B981",        // 翠绿
  warning: "#F59E0B",        // 琥珀
  danger: "#EF4444",         // 红色
  info: "#3B82F6",           // 蓝色
  gradient: "linear-gradient(135deg, #4F46E5 0%, #7C3AED 50%, #06B6D4 100%)",
  gradientWarm: "linear-gradient(135deg, #F59E0B 0%, #EF4444 50%, #EC4899 100%)",
  gradientCool: "linear-gradient(135deg, #3B82F6 0%, #6366F1 50%, #8B5CF6 100%)",
  gradientSuccess: "linear-gradient(135deg, #10B981 0%, #06B6D4 100%)",
  darkBg: "#0F172A",         // 深色背景
  darkCard: "#1E293B",       // 深色卡片
  darkBorder: "#334155",     // 深色边框
};

export const LIGHT_THEME: ThemeConfig = {
  token: {
    colorPrimary: BRAND_COLORS.primary,
    colorSuccess: BRAND_COLORS.success,
    colorWarning: BRAND_COLORS.warning,
    colorError: BRAND_COLORS.danger,
    colorInfo: BRAND_COLORS.info,
    borderRadius: 12,
    borderRadiusLG: 16,
    borderRadiusSM: 8,
    colorBgContainer: "#FFFFFF",
    colorBgLayout: "#F8FAFC",
    colorBorderSecondary: "#E2E8F0",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    fontSize: 14,
    fontSizeHeading1: 28,
    fontSizeHeading2: 22,
    fontSizeHeading3: 18,
    boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.06), 0 1px 2px -1px rgba(0, 0, 0, 0.06)",
    boxShadowSecondary: "0 4px 6px -2px rgba(0, 0, 0, 0.06), 0 10px 15px -4px rgba(0, 0, 0, 0.10)",
    colorPrimaryHover: BRAND_COLORS.primaryLight,
    colorPrimaryActive: BRAND_COLORS.primaryDark,
    controlHeight: 40,
    controlHeightLG: 48,
    controlHeightSM: 32,
  },
  components: {
    Layout: {
      headerBg: "#FFFFFF",
      headerHeight: 64,
      siderBg: BRAND_COLORS.darkBg,
      triggerBg: BRAND_COLORS.primary,
      triggerHeight: 48,
    },
    Menu: {
      darkItemBg: "transparent",
      darkItemColor: "#94A3B8",
      darkItemHoverBg: "rgba(255, 255, 255, 0.06)",
      darkItemHoverColor: "#FFFFFF",
      darkItemSelectedBg: BRAND_COLORS.primary + "20",
      darkItemSelectedColor: BRAND_COLORS.primaryLight,
      itemBorderRadius: 10,
      itemMarginInline: 8,
      itemMarginBlock: 2,
      subMenuItemBg: "transparent",
      darkSubMenuItemBg: "transparent",
    },
    Card: {
      paddingLG: 24,
      paddingMD: 20,
      paddingSM: 16,
      borderRadiusLG: 16,
      boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04)",
    },
    Button: {
      borderRadiusLG: 12,
      borderRadius: 10,
      borderRadiusSM: 8,
      controlHeightLG: 48,
      primaryShadow: "0 4px 14px 0 rgba(79, 70, 229, 0.35)",
    },
    Table: {
      borderRadiusLG: 16,
      headerBg: "#F8FAFC",
      headerBorderRadius: 12,
    },
    Modal: {
      borderRadiusLG: 20,
      borderRadiusSM: 16,
      paddingLG: 24,
      paddingMD: 20,
      paddingContentHorizontal: 24,
      paddingContentVertical: 20,
    },
    Input: {
      borderRadius: 10,
      borderRadiusLG: 12,
      borderRadiusSM: 8,
      controlHeightLG: 48,
    },
    Select: {
      borderRadius: 10,
      borderRadiusLG: 12,
      controlHeightLG: 48,
    },
    Tag: {
      borderRadius: 6,
      fontSizeSM: 12,
      lineHeightSM: 1.5,
    },
    Statistic: {
      contentFontSize: 32,
      titleFontSize: 14,
    },
    Tabs: {
      horizontalMargin: "0 24px 0 0",
      cardPadding: "8px 16px",
      horizontalItemPadding: "12px 0",
    },
    Form: {
      verticalLabelPadding: "0 0 6px",
      itemMarginBottom: 20,
    },
    Notification: {
      width: 400,
      borderRadiusLG: 16,
      paddingMD: 16,
      paddingContentHorizontal: 16,
      paddingContentVertical: 16,
    },
    Drawer: {
      borderRadiusLG: 20,
      paddingLG: 24,
    },
    Steps: {
      dotSize: 8,
      descriptionMaxWidth: 200,
      customIconSize: 32,
      iconSize: 32,
    },
  },
};

export const DARK_THEME: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  ...LIGHT_THEME,
  token: {
    ...LIGHT_THEME.token,
    colorBgContainer: BRAND_COLORS.darkCard,
    colorBgLayout: BRAND_COLORS.darkBg,
    colorBorderSecondary: BRAND_COLORS.darkBorder,
    colorText: "#F1F5F9",
    colorTextSecondary: "#94A3B8",
    colorTextTertiary: "#64748B",
    colorBgElevated: "#1E293B",
    colorBgMask: "rgba(0, 0, 0, 0.65)",
  },
  components: {
    ...LIGHT_THEME.components,
    Layout: {
      ...LIGHT_THEME.components?.Layout,
      headerBg: BRAND_COLORS.darkCard,
      siderBg: "#0B1120",
    },
    Menu: {
      ...LIGHT_THEME.components?.Menu,
      darkItemBg: "transparent",
    },
    Table: {
      ...LIGHT_THEME.components?.Table,
      headerBg: "#0F172A",
    },
    Card: {
      ...LIGHT_THEME.components?.Card,
    },
  },
};
