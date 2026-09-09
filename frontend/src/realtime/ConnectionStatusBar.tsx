import { useEffect, useState } from "react";
import { Tag, Tooltip } from "antd";
import { WifiOutlined, LoadingOutlined, DisconnectOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { motion, AnimatePresence } from "framer-motion";
import { getConnectionState, onConnectionChange, ConnState } from "./socket";

const META: Record<ConnState, { color: string; bg: string; text: string; icon: React.ReactNode; tip: string }> = {
  idle: { color: "#8c8c8c", bg: "rgba(0,0,0,0.04)", text: "未连接", icon: <DisconnectOutlined />, tip: "实时通道未启动" },
  connecting: { color: "#d48806", bg: "rgba(250,173,20,0.12)", text: "连接中", icon: <LoadingOutlined spin />, tip: "正在建立实时通道…" },
  connected: { color: "#389e0d", bg: "rgba(82,196,26,0.12)", text: "实时已连接", icon: <WifiOutlined />, tip: "后台任务进度与多用户变更将实时推送" },
  reconnecting: { color: "#cf1322", bg: "rgba(255,77,79,0.12)", text: "已断开·重连中", icon: <ThunderboltOutlined />, tip: "实时通道断开，正在自动重连，离线操作将在恢复后同步" },
  disconnected: { color: "#cf1322", bg: "rgba(255,77,79,0.12)", text: "已断开", icon: <DisconnectOutlined />, tip: "实时通道已断开" },
};

export function ConnectionStatusBar() {
  const [state, setState] = useState<ConnState>(getConnectionState());

  useEffect(() => {
    return onConnectionChange(setState);
  }, []);

  const m = META[state];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -12 }}
        transition={{ duration: 0.25 }}
        style={{
          position: "fixed",
          top: 8,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 1100,
          pointerEvents: "none",
        }}
      >
        <Tooltip title={m.tip}>
          <Tag
            icon={m.icon}
            style={{
              color: m.color,
              background: m.bg,
              borderColor: m.color,
              fontWeight: 600,
              borderRadius: 999,
              padding: "2px 12px",
              margin: 0,
              boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
              cursor: "default",
            }}
          >
            {m.text}
          </Tag>
        </Tooltip>
      </motion.div>
    </AnimatePresence>
  );
}
