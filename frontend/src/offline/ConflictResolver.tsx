import { useEffect, useState } from "react";
import { Modal, Card, Button, Tag, Input, Alert, Space, Typography, message as antdMessage } from "antd";
import { WarningOutlined, CloudUploadOutlined, CloudServerOutlined, MergeCellsOutlined } from "@ant-design/icons";
import { getPendingConflicts, onConflict, resolveConflict, ConflictRecord } from "./sync";

const { Text, Paragraph } = Typography;

function summarize(obj: any): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function EntityTag({ rec }: { rec: ConflictRecord }) {
  const label = rec.entity ? `${rec.entity}${rec.entityId ? " #" + rec.entityId.slice(0, 8) : ""}` : rec.local.url;
  return <Tag color="volcano">{label}</Tag>;
}

export function ConflictResolver() {
  const [conflicts, setConflicts] = useState<ConflictRecord[]>([]);
  const [mergeId, setMergeId] = useState<string | null>(null);
  const [mergeText, setMergeText] = useState<string>("");

  const reload = () => {
    getPendingConflicts().then(setConflicts).catch(() => setConflicts([]));
  };

  useEffect(() => {
    reload();
    const off = onConflict((c) => {
      setConflicts((prev) => (prev.find((x) => x.id === c.id) ? prev : [...prev, c]));
    });
    return off;
  }, []);

  const openMerge = (rec: ConflictRecord) => {
    setMergeId(rec.id);
    setMergeText(summarize(rec.local.body ?? {}));
  };

  const doResolve = async (id: string, type: "keep_local" | "keep_remote" | "merge", body?: any) => {
    try {
      await resolveConflict(id, { type, body });
      antdMessage.success(type === "keep_remote" ? "已保留服务端版本" : "已应用本地版本");
      if (mergeId === id) {
        setMergeId(null);
        setMergeText("");
      }
      reload();
    } catch (e: any) {
      antdMessage.error("解决失败：" + (e?.message || e));
    }
  };

  const current = conflicts[0];

  return (
    <>
      <Modal
        open={conflicts.length > 0}
        title={
          <Space>
            <WarningOutlined style={{ color: "#cf1322" }} />
            <span>检测到 {conflicts.length} 处离线编辑冲突</span>
          </Space>
        }
        footer={null}
        closable={false}
        maskClosable={false}
        width={680}
        style={{ top: 40 }}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="你在离线期间修改的内容，与服务器上的最新版本不一致。请选择处理方式："
        />
        {current && (
          <Card
            key={current.id}
            size="small"
            style={{ marginBottom: 12 }}
            title={
              <Space>
                <EntityTag rec={current} />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {current.op === "update" ? "更新" : current.op} 操作
                </Text>
              </Space>
            }
          >
            <Paragraph style={{ marginBottom: 8 }}>
              <Text strong>服务端当前版本（v{current.serverVersion ?? "?"}）：</Text>
              <br />
              <Text code style={{ fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {current.server ? summarize({
                  name: current.server.name,
                  status: current.server.status,
                  progress: current.server.progress,
                  version: current.server.version,
                }) : "（无法获取，可能已被删除）"}
              </Text>
            </Paragraph>
            <Paragraph style={{ marginBottom: 8 }}>
              <Text strong>你的本地改动：</Text>
              <br />
              <Text code style={{ fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {summarize(current.local.body ?? {})}
              </Text>
            </Paragraph>
            <Space wrap>
              <Button
                type="primary"
                danger
                icon={<CloudUploadOutlined />}
                onClick={() => doResolve(current.id, "keep_local")}
              >
                保留本地（覆盖）
              </Button>
              <Button icon={<CloudServerOutlined />} onClick={() => doResolve(current.id, "keep_remote")}>
                保留服务端
              </Button>
              <Button icon={<MergeCellsOutlined />} onClick={() => openMerge(current)}>
                手动合并
              </Button>
            </Space>
          </Card>
        )}
        {conflicts.length > 1 && (
          <Text type="secondary">还有 {conflicts.length - 1} 处冲突将在解决后依次显示。</Text>
        )}
      </Modal>

      <Modal
        open={mergeId !== null}
        title="手动合并（编辑最终写入内容）"
        onOk={async () => {
          try {
            const parsed = JSON.parse(mergeText);
            await doResolve(mergeId!, "merge", parsed);
          } catch (e: any) {
            antdMessage.error("JSON 解析失败：" + (e?.message || e));
          }
        }}
        onCancel={() => {
          setMergeId(null);
          setMergeText("");
        }}
        okText="应用合并结果"
        width={620}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="基于你的本地改动，修改为最终要写入服务端的字段。若仅覆盖部分字段，请确保 JSON 结构与服务端更新接口一致。"
        />
        <Input.TextArea
          value={mergeText}
          onChange={(e) => setMergeText(e.target.value)}
          autoSize={{ minRows: 10, maxRows: 20 }}
          style={{ fontFamily: "monospace", fontSize: 12 }}
        />
      </Modal>
    </>
  );
}
