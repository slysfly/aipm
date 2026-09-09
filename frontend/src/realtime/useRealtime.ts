import { useEffect, useState } from "react";
import { onEvent } from "./socket";

// 订阅某个异步任务的实时进度（由后端经 WebSocket 推送）。
export function useTaskProgress(taskId: string | null) {
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (!taskId) return;
    setProgress(0);
    setMessage("");
    setDone(false);
    setFailed(false);
    setError(null);
    setResult(null);

    const offProgress = onEvent("task_progress", (e) => {
      if (e.task_id === taskId) {
        setProgress(e.progress ?? 0);
        setMessage(e.message ?? "");
      }
    });
    const offDone = onEvent("task_done", (e) => {
      if (e.task_id === taskId) {
        setDone(true);
        setProgress(100);
        if (e.result !== undefined) setResult(e.result);
      }
    });
    const offFailed = onEvent("task_failed", (e) => {
      if (e.task_id === taskId) {
        setFailed(true);
        setError(e.error ?? "任务执行失败");
      }
    });
    return () => {
      offProgress();
      offDone();
      offFailed();
    };
  }, [taskId]);

  return { progress, message, done, failed, error, result };
}

// 订阅数据变更事件（多用户协作 / 后台任务完成后的实时刷新）。
export function onDataChanged(entity: string | null, handler: (e: any) => void): () => void {
  return onEvent("data_changed", (e) => {
    if (!entity || e.entity === entity) handler(e);
  });
}
