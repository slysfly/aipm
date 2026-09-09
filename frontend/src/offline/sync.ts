// 离线同步编排：将写操作暂存到 IndexedDB 草稿箱，在联网 / WebSocket 重连后自动重放。
// 重放时若服务端返回 409（乐观锁冲突），则把「本地改动 vs 服务端当前版本」存入冲突箱，
// 由 ConflictResolver 弹窗让用户裁决（保留本地 / 保留服务端 / 手动合并）。
// 与后端「后台异步任务 + 实时事件」体系配合，构成完整的离线→在线→冲突合并闭环。

import {
  putDraft,
  getAllDrafts,
  deleteDraft,
  countDrafts,
  putConflict,
  getAllConflicts,
  deleteConflict,
  Draft,
  ConflictRecord,
} from "./db";
import { getAuthToken } from "../api/token";
import { getEntityVersion } from "./versionCache";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export { countDrafts as countOutbox };

type ConflictHandler = (c: ConflictRecord) => void;
const conflictListeners: ConflictHandler[] = [];

/** 订阅新冲突事件（ConflictResolver 用于实时弹窗）。返回取消订阅函数。 */
export function onConflict(handler: ConflictHandler): () => void {
  conflictListeners.push(handler);
  return () => {
    const i = conflictListeners.indexOf(handler);
    if (i !== -1) conflictListeners.splice(i, 1);
  };
}

function emitConflict(c: ConflictRecord) {
  conflictListeners.slice().forEach((h) => h(c));
}

/** 从 URL 推断实体类型与 id（目前支持 task，其它实体不触发冲突检测，仅做普通重放）。 */
function inferEntity(url: string, method: string): { entity?: string; entityId?: string; op?: string } {
  const m = url.match(/\/tasks\/([^/]+)$/);
  if (m) return { entity: "task", entityId: m[1], op: method.toLowerCase() };
  if (/\/tasks$/.test(url)) return { entity: "task", op: "create" };
  return {};
}

/** 将一次写操作暂存到草稿箱（离线时由 http 拦截器调用）。 */
export async function enqueueMutation(method: string, url: string, body?: any): Promise<void> {
  const ent = inferEntity(url, method);
  const draft: Draft = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    method: (method || "POST").toUpperCase() as Draft["method"],
    url,
    body,
    entity: ent.entity,
    entityId: ent.entityId,
    op: ent.op as Draft["op"],
    baseVersion: ent.entityId ? getEntityVersion(ent.entityId) : undefined,
    createdAt: Date.now(),
  };
  await putDraft(draft);
}

type ReplayOutcome = "ok" | "conflict" | "stop" | "retry";

async function replay(draft: Draft): Promise<ReplayOutcome> {
  const token = getAuthToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (draft.baseVersion != null) headers["X-Base-Version"] = String(draft.baseVersion);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v1${draft.url}`, {
      method: draft.method,
      headers,
      body: draft.body != null ? JSON.stringify(draft.body) : undefined,
      credentials: "include",
    });
  } catch {
    return "retry"; // 网络不通，保留以便下次重放
  }
  if (res.ok) return "ok";
  if (res.status === 409) return "conflict";
  if (res.status === 401) return "stop"; // 需重新登录，停止重放
  if (res.status >= 500) return "retry"; // 服务端临时错误，保留
  return "ok"; // 其它 4xx 视为业务错误，丢弃以免死循环（全局提示已覆盖）
}

async function fetchServerSnapshot(draft: Draft): Promise<any> {
  if (!draft.entityId) return undefined;
  try {
    const token = getAuthToken();
    const res = await fetch(`${API_BASE}/v1${draft.url}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "include",
    });
    if (!res.ok) return undefined;
    const data = await res.json();
    return data?.data ?? data;
  } catch {
    return undefined;
  }
}

/**
 * 重放草稿箱中的写操作（按顺序、按序推进）。
 * 在以下时机调用：WebSocket 重连成功（见 realtime/socket.ts）、浏览器 online 事件、应用启动。
 */
export async function flushOutbox(): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return;
  let drafts: Draft[] = [];
  try {
    drafts = await getAllDrafts();
  } catch {
    return;
  }
  if (!drafts.length) return;

  for (const draft of drafts) {
    let outcome: ReplayOutcome;
    try {
      outcome = await replay(draft);
    } catch {
      outcome = "retry";
    }

    if (outcome === "ok") {
      await deleteDraft(draft.id);
      continue;
    }
    if (outcome === "stop" || outcome === "retry") {
      break; // 保留剩余草稿，待下次重放
    }
    if (outcome === "conflict") {
      const server = await fetchServerSnapshot(draft);
      const rec: ConflictRecord = {
        id: `cf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        entity: draft.entity,
        entityId: draft.entityId,
        op: draft.op,
        local: {
          method: draft.method,
          url: draft.url,
          body: draft.body,
          baseVersion: draft.baseVersion,
        },
        server,
        serverVersion: server?.version,
        base: draft.base,
        createdAt: Date.now(),
        status: "pending",
      };
      await putConflict(rec);
      await deleteDraft(draft.id);
      emitConflict(rec);
    }
  }
}

export async function getPendingConflicts(): Promise<ConflictRecord[]> {
  try {
    return (await getAllConflicts()).filter((c) => c.status === "pending");
  } catch {
    return [];
  }
}

/**
 * 解决一个冲突。
 * - keep_local：以本地改动覆盖服务端（强制写入，不再带 baseVersion）。
 * - keep_remote：丢弃本地改动，保留服务端版本。
 * - merge：以用户提供的 body 覆盖服务端（强制写入）。
 * 解决后自动触发一次 flush，尝试应用。如果仍冲突（极少见），会再次产生冲突记录。
 */
export async function resolveConflict(
  id: string,
  resolution: { type: "keep_local" | "keep_remote" | "merge"; body?: any },
): Promise<void> {
  const all = await getAllConflicts();
  const rec = all.find((c) => c.id === id);
  if (!rec) return;

  if (resolution.type === "keep_remote") {
    await deleteConflict(id);
    return;
  }

  const body = resolution.type === "merge" ? resolution.body : rec.local.body;
  const d: Draft = {
    id: `re-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    method: rec.local.method.toUpperCase() as Draft["method"],
    url: rec.local.url,
    body,
    entity: rec.entity,
    entityId: rec.entityId,
    op: rec.op as Draft["op"],
    baseVersion: undefined, // 强制覆盖最新版本
    createdAt: Date.now(),
  };
  await putDraft(d);
  await deleteConflict(id);
  await flushOutbox();
}
