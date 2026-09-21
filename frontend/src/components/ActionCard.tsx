import React, { useState } from "react";
import { Card, Table, Button, Space, message, Tag } from "antd";
import { post } from "../api/http";
import type { AiAction } from "../types/aiAction";

interface Props {
  actions: AiAction[];
  project_id?: string;
  onDone?: (created: string[]) => void;
}

const ActionCard: React.FC<Props> = ({ actions, project_id, onDone }) => {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const canRun = !!project_id && !done;

  const handleExecute = async () => {
    if (!project_id) {
      message.warning("请先在上方选择一个项目，再确认执行");
      return;
    }
    if (done) return;
    setLoading(true);
    try {
      const client_token =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `ct-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const res: any = await post("/openclaw/assistant/actions/execute", {
        project_id,
        client_token,
        actions,
      });
      const created = (res?.results || [])
        .map((r: any) => r.created_task_id)
        .filter(Boolean) as string[];
      const ok = res?.succeeded ?? created.length;
      const fail = res?.failed ?? 0;
      setDone(true);
      message.success(`已执行 ${ok} 条操作${fail ? `，${fail} 条失败` : ""}`);
      onDone?.(created);
    } catch (e: any) {
      message.error("执行失败：" + (e?.response?.data?.detail || e?.message || "未知错误"));
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: "操作",
      dataIndex: "action",
      key: "action",
      render: (v: string) =>
        v === "create_task" ? (
          <Tag color="blue">创建任务</Tag>
        ) : v === "update_task_status" ? (
          <Tag color="green">变更状态</Tag>
        ) : (
          <Tag>{v}</Tag>
        ),
    },
    {
      title: "对象",
      key: "target",
      render: (_: any, r: AiAction) =>
        r.action === "create_task"
          ? r.name || "（未命名）"
          : r.action === "update_task_status"
          ? `${r.task_ref || r.task_id || "-"} → ${r.status || "-"}`
          : "-",
    },
    {
      title: "关键字段",
      key: "meta",
      render: (_: any, r: AiAction) =>
        [
          r.priority ? `优先级:${r.priority}` : "",
          r.planned_start ? `起:${r.planned_start}` : "",
          r.planned_end ? `止:${r.planned_end}` : "",
        ]
          .filter(Boolean)
          .join("  ") || "-",
    },
  ];

  return (
    <Card
      size="small"
      style={{ marginTop: 8, borderColor: "#F97316" }}
      title={<span style={{ fontSize: 13 }}>🤖 AI 建议操作（请确认后执行）</span>}
    >
      <Table
        size="small"
        rowKey={(_: any, i: number) => String(i)}
        pagination={false}
        columns={columns as any}
        dataSource={actions}
        style={{ fontSize: 12 }}
      />
      <Space style={{ marginTop: 8 }}>
        <Button type="primary" loading={loading} disabled={!canRun} onClick={handleExecute}>
          {done ? "已执行" : `确认执行 ${actions.length} 条操作`}
        </Button>
        {!project_id && (
          <span style={{ color: "#faad14", fontSize: 12 }}>请先在上方选择项目</span>
        )}
      </Space>
    </Card>
  );
};

export default ActionCard;
