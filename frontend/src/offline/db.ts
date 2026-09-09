// 轻量 IndexedDB 封装 —— 离线「草稿箱」(drafts) 与「冲突箱」(conflicts) 存储。
// 不依赖任何第三方库，纯原生实现；网络恢复后由 sync.ts 按序重放草稿，
// 冲突则在 conflicts 中暂存、由 ConflictResolver 弹窗让用户裁决。
// 这是「离线 / 本地与服务器同步 + 冲突合并」能力的存储骨架。

const DB_NAME = "aipm-offline";
const DRAFT_STORE = "drafts";
const CONFLICT_STORE = "conflicts";
const VERSION = 2;

export interface Draft {
  id: string;
  method: "POST" | "PUT" | "DELETE";
  url: string; // 相对路径，如 "/tasks/xxx"
  body?: any;
  entity?: string; // 如 "task"，用于乐观锁冲突检测
  entityId?: string;
  op?: "create" | "update" | "delete";
  base?: any; // 编辑时的服务端快照（可用于三方合并）
  baseVersion?: number; // 编辑时的服务端版本（乐观锁）
  createdAt: number;
}

export interface ConflictRecord {
  id: string;
  entity?: string;
  entityId?: string;
  op?: string;
  local: { method: string; url: string; body?: any; baseVersion?: number };
  server?: any; // 服务端当前版本数据
  serverVersion?: number;
  base?: any;
  createdAt: number;
  status: "pending" | "resolved";
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("indexedDB 不可用"));
      return;
    }
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(DRAFT_STORE)) {
        db.createObjectStore(DRAFT_STORE, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(CONFLICT_STORE)) {
        db.createObjectStore(CONFLICT_STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ---------------------------------------------------------------------------
// drafts
// ---------------------------------------------------------------------------
export async function putDraft(item: Draft): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DRAFT_STORE, "readwrite");
    tx.objectStore(DRAFT_STORE).put(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAllDrafts(): Promise<Draft[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DRAFT_STORE, "readonly");
    const req = tx.objectStore(DRAFT_STORE).getAll();
    req.onsuccess = () => resolve((req.result as Draft[]) || []);
    req.onerror = () => reject(req.error);
  });
}

export async function deleteDraft(id: string): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DRAFT_STORE, "readwrite");
    tx.objectStore(DRAFT_STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function countDrafts(): Promise<number> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DRAFT_STORE, "readonly");
    const req = tx.objectStore(DRAFT_STORE).count();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ---------------------------------------------------------------------------
// conflicts
// ---------------------------------------------------------------------------
export async function putConflict(item: ConflictRecord): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(CONFLICT_STORE, "readwrite");
    tx.objectStore(CONFLICT_STORE).put(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAllConflicts(): Promise<ConflictRecord[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(CONFLICT_STORE, "readonly");
    const req = tx.objectStore(CONFLICT_STORE).getAll();
    req.onsuccess = () => resolve((req.result as ConflictRecord[]) || []);
    req.onerror = () => reject(req.error);
  });
}

export async function deleteConflict(id: string): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(CONFLICT_STORE, "readwrite");
    tx.objectStore(CONFLICT_STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function countConflicts(): Promise<number> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(CONFLICT_STORE, "readonly");
    const req = tx.objectStore(CONFLICT_STORE).count();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(tx.error);
  });
}
