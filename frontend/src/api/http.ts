import axios from "axios";
import { message } from "antd";
import { setAuthToken, getAuthToken, setRefreshToken, getRefreshToken } from "./token";
import { enqueueMutation } from "../offline/sync";
import { setEntityVersion } from "../offline/versionCache";

export { setAuthToken, getAuthToken };

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export const http = axios.create({
  baseURL: `${API_BASE}/v1`,
  timeout: 30000,
  // 鉴权主通道为后端下发的 httpOnly Cookie；开启 withCredentials 让浏览器自动随请求携带，
  // 否则刷新页面后内存态令牌为空、Cookie 又不随请求发送，会出现 401（上传等接口尤为明显）。
  withCredentials: true,
});

// ---------------------------------------------------------------------------
// 1. 全局 Loading 状态跟踪
// ---------------------------------------------------------------------------
let loadingCount = 0;
type LoadingListener = (loading: boolean) => void;
const loadingListeners: LoadingListener[] = [];

export function onLoadingChange(listener: LoadingListener) {
  loadingListeners.push(listener);
  return () => {
    const idx = loadingListeners.indexOf(listener);
    if (idx !== -1) loadingListeners.splice(idx, 1);
  };
}

function notifyLoading(delta: number) {
  loadingCount += delta;
  const isLoading = loadingCount > 0;
  loadingListeners.forEach((fn) => fn(isLoading));
}

// ---------------------------------------------------------------------------
// 2. 网络状态检测（offline / online）
// ---------------------------------------------------------------------------
let _wasOffline = false;

window.addEventListener("offline", () => {
  _wasOffline = true;
  message.warning({ content: "网络已断开，请检查网络连接", key: "net-status", duration: 0 });
});

window.addEventListener("online", () => {
  if (_wasOffline) {
    _wasOffline = false;
    message.success({ content: "网络已恢复", key: "net-status", duration: 3 });
  }
});

// ---------------------------------------------------------------------------
// 3. 请求拦截器
// ---------------------------------------------------------------------------
http.interceptors.request.use((config) => {
  // 排除静默请求（如自动刷新token），不增加 loading
  if (!(config as any)._silent) {
    notifyLoading(1);
  }

  const token = getAuthToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---------------------------------------------------------------------------
// 4. 响应拦截器
// ---------------------------------------------------------------------------
http.interceptors.response.use(
  (resp) => {
    if (!(resp.config as any)._silent) {
      notifyLoading(-1);
    }
    // 缓存实体乐观锁版本号（供离线编辑回放时携带 X-Base-Version）
    try {
      const h = resp.headers as any;
      const ev = h && typeof h.get === "function" ? h.get("X-Entity-Version") : h?.["x-entity-version"];
      if (ev) {
        const um = String(resp.config?.url || "").match(/\/tasks\/([^/]+)$/);
        if (um) setEntityVersion(um[1], parseInt(ev, 10));
      }
    } catch {
      /* ignore */
    }
    return resp;
  },
  (error) => {
    // 减少 loading 计数
    if (!(error.config as any)?._silent) {
      notifyLoading(-1);
    }

    // [401] clear token & redirect (silent requests exempt)
    if (error.response && error.response.status === 401) {
      if (!(error.config || {})._silent) {
        // 尝试自动 refresh token（非静默请求才触发）
        const refreshToken = getRefreshToken();
        if (refreshToken && !(error.config as any)._refreshRetry) {
          (error.config as any)._refreshRetry = true;
          fetch(API_BASE + "/v1/auth/refresh", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
          })
            .then((resp) => {
              if (resp.ok) return resp.json();
              throw new Error("refresh failed");
            })
            .then((data) => {
              if (data?.data?.access_token) {
                setAuthToken(data.data.access_token);
                if (data.data.refresh_token) setRefreshToken(data.data.refresh_token);
                // 重试原请求
                return http.request(error.config);
              }
              throw new Error("no access_token in response");
            })
            .catch(() => {
              setAuthToken(null);
              setRefreshToken(null);
              fetch(API_BASE + "/v1/auth/logout", {
                method: "POST",
                credentials: "same-origin",
              }).catch(function() {});
              if (location.pathname !== "/login") {
                location.href = "/login";
              }
            });
          return Promise.reject(error);
        }
        // refresh 失败或无 refresh token：清除 token 并跳转登录
        setAuthToken(null);
        setRefreshToken(null);
        fetch(API_BASE + "/v1/auth/logout", {
          method: "POST",
          credentials: "same-origin",
        }).catch(function() {});
        if (location.pathname !== "/login") {
          location.href = "/login";
        }
      }
      return Promise.reject(error);
    }

    // --- 将对象/数组类型的 detail 转为可读字符串 ---
    const data = error.response?.data;
    if (data && typeof data.detail !== "undefined" && typeof data.detail !== "string") {
      try {
        data.detail = Array.isArray(data.detail)
          ? data.detail.map((d: any) => d?.msg || JSON.stringify(d)).join("; ")
          : JSON.stringify(data.detail);
      } catch {
        data.detail = "请求失败";
      }
    }

    // --- 统一错误消息提示（静默请求除外） ---
    if (!(error.config as any)?._silent) {
      const status = error.response?.status;
      const errMsg = extractErrorMessage(error);
      const url = error.config?.url || "unknown";

      // 使用 console.warn 记录错误详情，不破坏现有逻辑
      console.warn(`[HTTP Error] ${error.config?.method?.toUpperCase()} ${url} (${status || "NETWORK"})`, {
        message: errMsg,
        status,
        data: error.response?.data,
        timestamp: new Date().toISOString(),
      });

      // 某些状态码不需要全局提示（或已有页面对应处理）
      if (status && status !== 401) {
        message.error({ content: errMsg, key: `http-err-${Date.now()}`, duration: 4 });
      } else if (!status) {
        // 无状态码 → 网络中断 或 请求超时（axios 超时无 response，被误判为断网）
        const isTimeout = error.code === "ECONNABORTED" || /timeout/i.test(error.message || "");

        // 离线场景：将写操作暂存到本地 outbox，联网/WS 重连后自动重放（离线同步骨架）
        if (typeof navigator !== "undefined" && navigator.onLine === false && !error.config?._offlineReplay) {
          const m = (error.config?.method || "post").toUpperCase();
          if (m === "POST" || m === "PUT" || m === "DELETE") {
            enqueueMutation(m, error.config?.url || "", error.config?.data)
              .then(() => message.info({ content: "当前离线，操作已暂存，联网后将自动同步", key: "offline-queue", duration: 3 }))
              .catch(() => {});
          }
        }

        const content = isTimeout
          ? "请求超时：AI 生成较慢，请稍后重试，或精简项目描述后再次生成"
          : "网络连接失败，请检查网络后重试";
        message.error({ content, key: "net-err", duration: 5 });
      }
    }

    return Promise.reject(error);
  }
);

// ---------------------------------------------------------------------------
// 后端接口统一响应格式解析
// ---------------------------------------------------------------------------
export function unwrap<T = any>(data: any): T {
  if (!data || typeof data !== "object") return data as T;

  // 新格式：{ code, data, message }
  if ("code" in data && "data" in data) {
    return data.data as T;
  }

  // 旧格式：{ success, data }
  if ("success" in data && "data" in data) {
    return data.data as T;
  }

  // 登录等特殊接口：{ access_token }
  if ("access_token" in data) return data as T;

  return data as T;
}

// 解析错误信息
export function extractErrorMessage(err: any): string {
  const resp = err?.response?.data;
  if (!resp) return err?.message || "请求失败";

  if (resp.code && resp.message) return resp.message;
  if (resp.error?.message) return resp.error.message;
  if (typeof resp.detail === "string") return resp.detail;
  if (Array.isArray(resp.detail)) {
    return resp.detail.map((d: any) => d?.msg || JSON.stringify(d)).join("; ");
  }
  return JSON.stringify(resp);
}

// ---------------------------------------------------------------------------
// 便捷请求方法
// ---------------------------------------------------------------------------
export async function get<T = any>(url: string, params?: any, timeout?: number, silent?: boolean): Promise<T> {
  const cfg: any = { params };
  if (timeout) cfg.timeout = timeout;
  if (silent) cfg._silent = true;
  const r = await http.get(url, cfg);
  return unwrap<T>(r.data);
}

export async function post<T = any>(url: string, body?: any, silent?: boolean, timeout?: number): Promise<T> {
  const cfg: any = { ...(silent ? { _silent: true } : {}) };
  if (timeout) cfg.timeout = timeout;
  const r = await http.post(url, body, cfg);
  return unwrap<T>(r.data);
}

export async function put<T = any>(url: string, body?: any, silent?: boolean, timeout?: number): Promise<T> {
  const cfg: any = { ...(silent ? { _silent: true } : {}) };
  if (timeout) cfg.timeout = timeout;
  const r = await http.put(url, body, cfg);
  return unwrap<T>(r.data);
}

export async function del<T = any>(url: string, silent?: boolean, timeout?: number): Promise<T> {
  const cfg: any = { ...(silent ? { _silent: true } : {}) };
  if (timeout) cfg.timeout = timeout;
  const r = await http.delete(url, cfg);
  return unwrap<T>(r.data);
}

export async function downloadBlob(url: string, params?: any): Promise<Blob> {
  const r = await http.get(url, { params, responseType: "blob" });
  return r.data;
}

// 多部分表单上传（文件/文件夹）。复用 http 实例的 Bearer 兜底 + withCredentials(Cookie 主通道)
// 与 401 拦截逻辑，避免裸 fetch 在刷新后内存令牌为空时 401（这正是"上传不被 RAG 识别"的根因）。
export async function uploadForm<T = any>(url: string, form: FormData, timeout?: number): Promise<T> {
  const cfg: any = { timeout: timeout ?? 120000, withCredentials: true };
  const r = await http.post(url, form, cfg);
  return unwrap<T>(r.data);
}
