// 实体版本缓存：在读取/更新实体时记录服务端乐观锁版本号，
// 供离线编辑回放时携带 X-Base-Version，使服务端能做冲突检测。

const cache = new Map<string, number>();

export function setEntityVersion(id: string | undefined, v: number | undefined): void {
  if (id && typeof v === "number" && !Number.isNaN(v)) {
    cache.set(id, v);
  }
}

export function getEntityVersion(id?: string): number | undefined {
  return id ? cache.get(id) : undefined;
}

export function clearEntityVersions(): void {
  cache.clear();
}
