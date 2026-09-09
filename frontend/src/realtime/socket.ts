import { getAuthToken } from "../api/http";
import { flushOutbox } from "../offline/sync";

// 前端实时层：连接后端 /api/v1/ws/events/{token}，接收后台任务进度、数据变更、通知等事件。
// 与 IM 的 WebSocket 相互独立；token 取自内存态（与 axios 同源，不落 localStorage）。

type EventHandler = (event: any) => void;

export type ConnState = "idle" | "connecting" | "connected" | "reconnecting" | "disconnected";
let connState: ConnState = "idle";
const connListeners: ((s: ConnState) => void)[] = [];

function setConnState(s: ConnState) {
  if (connState === s) return;
  connState = s;
  connListeners.slice().forEach((h) => h(s));
}

export function getConnectionState(): ConnState {
  return connState;
}

/** 订阅实时连接状态变化（用于状态指示条）。返回取消订阅函数。 */
export function onConnectionChange(handler: (s: ConnState) => void): () => void {
  connListeners.push(handler);
  return () => {
    const i = connListeners.indexOf(handler);
    if (i !== -1) connListeners.splice(i, 1);
  };
}

const listeners: Record<string, EventHandler[]> = {};
let ws: WebSocket | null = null;
let reconnectTimer: any = null;
let heartbeatTimer: any = null;

function wsBase(): string {
  const base = import.meta.env.VITE_API_BASE || "/api";
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  // VITE_API_BASE 可能是 "/api" 或完整 http(s) 地址
  if (base.startsWith("http")) {
    const u = new URL(base);
    const p = u.protocol === "https:" ? "wss:" : "ws:";
    return `${p}//${u.host}/api/v1/ws/events`;
  }
  return `${proto}//${location.host}${base}/v1/ws/events`;
}

export function connectRealtime() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const token = getAuthToken();
  if (!token) return;
  setConnState("connecting");
  const url = `${wsBase()}/${encodeURIComponent(token)}`;
  try {
    ws = new WebSocket(url);
  } catch {
    setConnState("disconnected");
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    setConnState("connected");
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "heartbeat" }));
      }
    }, 25000);
    // 连接建立（含断线重连）→ 重放离线期间暂存的写操作
    flushOutbox().catch(() => {});
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      dispatch(msg);
    } catch {
      /* ignore malformed */
    }
  };
  ws.onclose = () => {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    setConnState("reconnecting");
    scheduleReconnect();
  };
  ws.onerror = () => {
    if (ws) ws.close();
  };
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectRealtime();
  }, 3000);
}

export function onEvent(type: string, handler: EventHandler): () => void {
  if (!listeners[type]) listeners[type] = [];
  listeners[type].push(handler);
  return () => {
    const arr = listeners[type];
    if (arr) {
      const i = arr.indexOf(handler);
      if (i !== -1) arr.splice(i, 1);
    }
  };
}

function dispatch(msg: any) {
  const arr = listeners[msg?.type];
  if (arr) arr.slice().forEach((h) => h(msg));
}
