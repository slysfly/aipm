import React, { useEffect, useState } from "react";
import { Tour, Button } from "antd";
import { BookOutlined } from "@ant-design/icons";
import type { TourProps } from "antd";
import { useLocation } from "react-router-dom";
import { tutorials, resolveTourKey } from "../tutorials";

const SEEN_PREFIX = "tw_tour_v1_";

// === antd Tour target 解析（v51.1 修复） ===
// antd 5.29.3 的 Tour 会把 steps[].target 原样透传给 @rc-component/tour@1.15.1，
// 而 rc-tour 的 useTarget 只接受 HTMLElement 或 () => HTMLElement。
// 若 target 是 CSS 选择器字符串，rc-tour 会把它当元素直接调
// e.getBoundingClientRect() → TypeError: e.getBoundingClientRect is not a function，
// 被 ErrorBoundary 捕获后页面显示"页面出现错误"。
// 因此必须把 target 包成函数：
//   - target 为空 / undefined → 不返回 target，该步居中卡片；
//   - target 以 "text:" 开头 → 在常见可点击元素范围内按文字模糊匹配首个；
//   - 其他 → 视为 CSS 选择器，querySelector 取首个；
//   - 找不到元素 → 返回 null（rc-tour 同样会居中卡片，绝不抛错）。
function locate(sel?: string): (() => HTMLElement | null) | undefined {
  if (!sel) return undefined;
  if (sel.startsWith("text:")) {
    const text = sel.slice(5).trim();
    return () => {
      const nodes = document.querySelectorAll(
        'button, a, [role="button"], [role="tab"], .ant-segmented-item, .ant-menu-item, .ant-select-selector, [data-tour]'
      );
      for (const el of Array.from(nodes)) {
        const t = (el.textContent || "").trim();
        if (t && t.includes(text)) return el as HTMLElement;
      }
      return null;
    };
  }
  return () => document.querySelector(sel) as HTMLElement | null;
}

// 全局教程组件：挂载于 MainLayout，按当前路由自动匹配该页教程。
// - 每个页面常驻悬浮「操作教程」按钮，可随时重看；
// - 首次访问自动播放（localStorage 记录已看，避免反复打扰）；
// - 监听头部「教程」按钮派发的 tw:open-tour 事件。
const PageTour: React.FC = () => {
  const location = useLocation();
  const key = resolveTourKey(location.pathname);
  const entry = tutorials[key];
  const [open, setOpen] = useState(false);

  // 路由切换时关闭教程，避免跨页串台导致步骤错位甚至抛错
  useEffect(() => {
    setOpen(false);
  }, [key]);

  // 监听头部「教程」按钮
  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener("tw:open-tour", handler);
    return () => window.removeEventListener("tw:open-tour", handler);
  }, []);

  if (!entry) return null;

  const steps: TourProps["steps"] = entry.steps.map((s) => ({
    title: s.title,
    description: s.description,
    target: locate(s.target),
    placement: s.placement,
  }));

  const markSeen = () => localStorage.setItem(SEEN_PREFIX + key, "1");

  return (
    <>
      <Button
        type="default"
        icon={<BookOutlined />}
        onClick={() => { setOpen(true); localStorage.setItem(SEEN_PREFIX + key, "1"); }}
        style={{
          position: "fixed",
          right: 24,
          bottom: 24,
          zIndex: 1000,
          boxShadow: "0 6px 20px rgba(79,70,229,0.35)",
          borderRadius: 24,
          height: 44,
          paddingInline: 18,
          background: "linear-gradient(135deg,#4F46E5,#6366F1)",
          color: "#fff",
          border: "none",
          fontWeight: 600,
        }}
      >
        操作教程
      </Button>
      <Tour
        open={open}
        onClose={() => {
          setOpen(false);
          markSeen();
        }}
        onFinish={() => {
          setOpen(false);
          markSeen();
        }}
        steps={steps}
      />
    </>
  );
};

export default PageTour;
