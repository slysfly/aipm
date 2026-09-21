import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button, message as antdMessage } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { asyncTaskApi } from "../api";
import { useTaskProgress } from "../realtime/useRealtime";

interface Props {
  formType: string;
  // 返回当前表单已填字段（用于补全缺失项）
  getValues: () => Record<string, any>;
  // 将 AI 建议回填到表单
  onApply: (suggestions: Record<string, any>) => void;
  // 补充上下文（如项目名/描述）
  context?: Record<string, any>;
  // 运行时枚举取值（如 project_type 的合法 code），随请求下发给后端，
  // 使模型只在合法选项内选择——这是「回填后下拉框不空白」的关键。
  options?: Record<string, any>;
  // 需要转成 dayjs 才能回填的日期字段（antd DatePicker 只认 dayjs 对象，
  // 直接塞字符串会导致保存时 form 取不到值、日期被静默丢弃）
  dateFields?: string[];
  label?: string;
  // 兜底超时（毫秒）：超过后解除 loading，避免按钮永久转圈
  timeoutMs?: number;
}

const POLL_INTERVAL_MS = 1500;
const DEFAULT_TIMEOUT_MS = 90000;

/**
 * 通用「AI 帮我填」按钮。
 *
 * 两段式回填（2026-09-19 改）：
 *
 * - **第一段 `instant`（规则层，0ms）**：后端按规则算出的默认值（日期跨度、预估工时、
 *   状态/优先级）。HTTP 响应里直接带回来，点下去**立刻**能看到表单有变化。
 * - **第二段 `suggestions`（模型层，2~9s）**：模型写的名称/描述等，异步推送后覆盖补充。
 *
 * 为什么要这么拆：本项目所用网关首字延迟 2~8.9s（生成本身只占约 1s，其余全在排队）。
 * 用户点完要盯着空表单等这么久，体感极差。把规则层提前，等待就被藏起来了。
 *
 * 另：请求里连"可依据的信号"都没有时，后端不会建任务，直接返回 `need_input` +
 * 可操作提示。此时**不该转圈**，要立刻把提示显示出来。
 *
 * 可靠性设计（原先的坑）：
 * - WebSocket 事件在断线/重连窗口内会丢失，此时按钮会永久 loading → 增加轮询兜底；
 * - 结果可能同时从 WS 与轮询到达 → 用 ref 保证只消费一次；
 * - 再加一层硬超时兜底，任何情况下都能解除 loading 并给出可读提示。
 */
const AIAssistButton: React.FC<Props> = ({
  formType,
  getValues,
  onApply,
  context,
  options,
  dateFields,
  label,
  timeoutMs = DEFAULT_TIMEOUT_MS,
}) => {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // 订阅后台「AI 帮我填」任务的实时进度/结果
  const task = useTaskProgress(taskId);
  // 模型结果只允许被消费一次（WS 与轮询可能同时到达）
  const consumedRef = useRef(false);
  // 本轮已经用规则层填了几个字段（用于把提示文案说准）
  const instantCountRef = useRef(0);

  /** 把后端返回的原始字段转成可直接 setFieldsValue 的对象（日期转 dayjs）。 */
  const toFormPatch = useCallback(
    (raw: Record<string, any>): Record<string, any> => {
      const next: Record<string, any> = {};
      Object.keys(raw || {}).forEach((k) => {
        const v = raw[k];
        if (dateFields?.includes(k) && typeof v === "string") {
          const d = dayjs(v);
          if (d.isValid()) next[k] = d;
          return;
        }
        next[k] = v;
      });
      return next;
    },
    [dateFields]
  );

  const applyResult = useCallback(
    (res: any) => {
      if (consumedRef.current) return;
      consumedRef.current = true;
      setTaskId(null);

      const payload = res || {};
      const raw = (payload.suggestions || {}) as Record<string, any>;
      const tips: string[] = Array.isArray(payload.improve_tips) ? payload.improve_tips : [];
      const instantFilled = instantCountRef.current;

      // 后端已明确报错且没有任何可回填内容 → 如实告知
      if (!Object.keys(raw).length) {
        if (payload.error === "need_input") {
          // 规则层可能已经填了日期/工时，所以这里是"提示"而不是"失败"
          antdMessage.info(payload.message || "先填写一些内容，AI 才能帮你补全");
        } else if (payload.error) {
          antdMessage.warning(payload.message || "AI 未返回可用结果，请重试");
        } else if (tips.length) {
          antdMessage.info("优化建议：" + tips.join("；"));
        } else if (instantFilled > 0) {
          // 规则层已经填过了，别再说"暂无可补全项"，那会让人以为白点了
          antdMessage.info(`已按规则填入 ${instantFilled} 项默认值，AI 未补充更多内容`);
        } else {
          antdMessage.info(payload.message || "暂无可补全项");
        }
        return;
      }

      const next = toFormPatch(raw);
      const n = Object.keys(next).length;
      if (!n) {
        antdMessage.info(payload.message || "暂无可补全项");
        return;
      }

      onApply(next);
      const head = instantFilled > 0 ? `AI 又补全 ${n} 个字段` : `AI 已补全并优化 ${n} 个字段`;
      antdMessage.success(head + (tips.length ? "；建议：" + tips.join("；") : ""));
    },
    [onApply, toFormPatch]
  );

  const failResult = useCallback((msg?: string) => {
    if (consumedRef.current) return;
    consumedRef.current = true;
    setTaskId(null);
    antdMessage.error(msg || "AI 辅助填写失败");
  }, []);

  const handleClick = async () => {
    if (submitting || taskId) return;
    consumedRef.current = false;
    instantCountRef.current = 0;
    setSubmitting(true);
    try {
      const r = await asyncTaskApi.create("assist_fill", {
        form_type: formType,
        fields: getValues() || {},
        context: context || {},
        options: options || {},
      });

      // 第一段：规则层结果，立刻回填，不等模型
      const instant = (r?.instant || {}) as Record<string, any>;
      if (Object.keys(instant).length) {
        const patch = toFormPatch(instant);
        const n = Object.keys(patch).length;
        if (n) {
          instantCountRef.current = n;
          onApply(patch);
        }
      }

      // 依据不足：后端没建任务，也不会有后续推送 —— 立刻给提示并停止转圈
      if (r?.need_input) {
        consumedRef.current = true;
        antdMessage.info(
          (r?.message || "先填写一些内容，AI 才能帮你补全") +
            (instantCountRef.current > 0 ? `（已先填入 ${instantCountRef.current} 项默认值）` : "")
        );
        return;
      }

      const id = r?.task_id || r?.id;
      if (id) {
        setTaskId(id);
      } else if (r?.success === false) {
        consumedRef.current = true;
        antdMessage.warning(r?.message || "AI 未能开始处理，请重试");
      } else {
        consumedRef.current = true;
        antdMessage.error("未能创建后台任务");
      }
    } catch (e: any) {
      consumedRef.current = true;
      antdMessage.error(e?.response?.data?.message || e?.response?.data?.detail || "AI 辅助填写失败");
    } finally {
      setSubmitting(false);
    }
  };

  // 完成 / 失败（WebSocket 实时推送）
  useEffect(() => {
    if (!taskId) return;
    if (task.done) applyResult(task.result);
    else if (task.failed) failResult(task.error);
  }, [taskId, task.done, task.failed, task.result, task.error, applyResult, failResult]);

  // 轮询兜底：WS 未连接或事件丢失时仍能拿到结果，避免按钮永久 loading
  useEffect(() => {
    if (!taskId || task.done || task.failed) return;
    let stopped = false;
    const timer = window.setInterval(async () => {
      if (stopped || consumedRef.current) return;
      try {
        const t = await asyncTaskApi.get(taskId);
        if (stopped || !t) return;
        if (t.status === "success") applyResult(t.result);
        else if (t.status === "failed") failResult(t.error);
      } catch {
        /* 单次轮询失败忽略，等待下一轮 */
      }
    }, POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [taskId, task.done, task.failed, applyResult, failResult]);

  // 硬超时兜底
  useEffect(() => {
    if (!taskId) return;
    const timer = window.setTimeout(() => {
      failResult(`AI 处理超过 ${Math.round(timeoutMs / 1000)} 秒，请重试`);
    }, timeoutMs);
    return () => window.clearTimeout(timer);
  }, [taskId, timeoutMs, failResult]);

  const running = !!taskId;

  return (
    <Button
      icon={<ThunderboltOutlined />}
      loading={running || submitting}
      onClick={handleClick}
      title={running ? task.message || "AI 正在补全…" : undefined}
    >
      {label || "AI 帮我填"}
      {running && task.progress > 0 ? ` ${task.progress}%` : ""}
    </Button>
  );
};

export default AIAssistButton;
