import React, { useState, useEffect } from "react";
import { Button, message as antdMessage } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
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
  label?: string;
}

/**
 * 通用「AI 帮我填」按钮：触发后台异步任务 /ai/assist-fill，根据已填字段补全缺失项并优化，
 * 进度经 WebSocket 实时推送；完成后把建议回填到表单。任意 antd Form 均可复用。
 */
const AIAssistButton: React.FC<Props> = ({ formType, getValues, onApply, context, label }) => {
  const [taskId, setTaskId] = useState<string | null>(null);
  // 订阅后台「AI 帮我填」任务的实时进度/结果
  const task = useTaskProgress(taskId);

  const handleClick = async () => {
    try {
      const r = await asyncTaskApi.create("assist_fill", {
        form_type: formType,
        fields: getValues() || {},
        context: context || {},
      });
      if (r?.task_id) {
        setTaskId(r.task_id);
      } else {
        antdMessage.error("未能创建后台任务");
      }
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || "AI 辅助填写失败");
    }
  };

  // 任务完成后回填建议
  useEffect(() => {
    if (taskId && task.done && task.result) {
      const res = task.result || {};
      const tips = res.improve_tips || [];
      if (res.suggestions && Object.keys(res.suggestions).length > 0) {
        onApply(res.suggestions);
        antdMessage.success("AI 已补全并优化字段" + (tips.length ? "；建议：" + tips.join("；") : ""));
      } else {
        antdMessage.info(tips.length ? "优化建议：" + tips.join("；") : "暂无可补全项");
      }
      setTaskId(null);
    }
  }, [task.done, taskId]);

  useEffect(() => {
    if (taskId && task.failed) {
      antdMessage.error(task.error || "AI 辅助填写失败");
      setTaskId(null);
    }
  }, [task.failed, taskId]);

  return (
    <Button icon={<ThunderboltOutlined />} loading={!!taskId && !task.done && !task.failed} onClick={handleClick}>
      {label || "AI 帮我填"}
    </Button>
  );
};

export default AIAssistButton;
