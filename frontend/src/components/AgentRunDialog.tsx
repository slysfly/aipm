import React, { useEffect, useRef, useState } from "react";
import {
  Modal, Steps, Switch, Button, Space, List, Tag, Spin, Alert, Typography,
  Input, Upload, Tooltip, Select, Card, App,
} from "antd";
import {
  CloudDownloadOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  LoadingOutlined, CheckOutlined, ThunderboltOutlined, ExperimentOutlined,
  FileTextOutlined, UploadOutlined, SendOutlined, RightOutlined,
  PlayCircleOutlined, ReloadOutlined,
} from "@ant-design/icons";
import { agentApi } from "../api";
import { renderMarkdownToHtml } from "../utils/markdown";

const { Text } = Typography;
const { TextArea } = Input;

// 与后端 get_structured_itto / prepare 返回结构对齐（本组件自包含，避免与 PmbokAgents 形成循环依赖）
interface IttoItem { key: string; label: string; optional?: boolean; enabled?: boolean; kind?: string; template_prompt?: string; }
interface PrepareInput extends IttoItem { exists: boolean; ref?: string | null; title?: string | null; source?: string | null; }
interface PrepareResult { agent_id: string; project_id?: string | null; has_project: boolean; inputs: PrepareInput[]; missing_required: string[]; tools: IttoItem[]; outputs: IttoItem[]; }

type RunMode = "slow" | "fast";
type Phase = "retrieval" | "running" | "result" | "error";
type RetrievalStatus = "scanning" | "found" | "missing";
type ToolStatus = "pending" | "running" | "done";

interface AgentRunDialogProps {
  open: boolean;
  onClose: () => void;
  agent: { id: string; name: string; kind: "domain" | "pmbok" } | null;
  projectId?: string;
  projects: { id: string; name: string }[];
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

const AgentRunDialog: React.FC<AgentRunDialogProps> = ({ open, onClose, agent, projectId, projects }) => {
  const { message } = App.useApp();
  const [mode, setMode] = useState<RunMode>(() => {
    const saved = (typeof localStorage !== "undefined" && localStorage.getItem("agent_run_mode")) || "slow";
    return saved === "fast" ? "fast" : "slow";
  });
  const [phase, setPhase] = useState<Phase>("retrieval");
  const [prepare, setPrepare] = useState<PrepareResult | null>(null);
  const [retrieval, setRetrieval] = useState<Record<string, RetrievalStatus>>({});
  const [uploadInputs, setUploadInputs] = useState<Record<string, { basic_info: string; file_content: string; file_name: string }>>({});
  const [genState, setGenState] = useState<Record<string, boolean>>({});
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [userInput, setUserInput] = useState("");
  const [toolAnim, setToolAnim] = useState<{ key: string; label: string; status: ToolStatus }[]>([]);
  const [outputs, setOutputs] = useState<any[] | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [localProjectId, setLocalProjectId] = useState<string | undefined>(projectId);
  const [running, setRunning] = useState(false);

  const cancelledRef = useRef(false);

  useEffect(() => { setLocalProjectId(projectId); }, [projectId]);

  // 阶段一：检索所需输入文件（带动画）+ 展示检索结果
  const startRetrieval = async () => {
    if (!agent) return;
    cancelledRef.current = false;
    setPhase("retrieval");
    setPrepare(null);
    setRetrieval({});
    setOutputs(null);
    setErrorMsg("");
    setUserInput("");
    setUploadInputs({});
    setGenState({});
    setToolAnim([]);
    setRunning(false);
    try {
      const data: PrepareResult = await agentApi.prepare(agent.id, { project_id: localProjectId });
      if (cancelledRef.current) return;
      setPrepare(data);
      const tools = (data.tools || []).filter((t) => t.enabled !== false).map((t) => t.key);
      setSelectedTools(tools);
      // 逐条动画：检索中 → 已找到 / 缺失
      const inputs = (data.inputs || []).filter((i) => i.enabled !== false);
      for (const it of inputs) {
        if (cancelledRef.current) return;
        setRetrieval((s) => ({ ...s, [it.key]: "scanning" }));
        await delay(360);
        if (cancelledRef.current) return;
        setRetrieval((s) => ({ ...s, [it.key]: it.exists ? "found" : "missing" }));
      }
    } catch (e: any) {
      if (cancelledRef.current) return;
      setErrorMsg(e?.message || "运行前物料检索失败");
      setPhase("error");
    }
  };

  useEffect(() => {
    if (open && agent) startRetrieval();
    return () => { cancelledRef.current = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent?.id]);

  // 缺失输入：上传基础信息 → AI 生成统一模板
  const doGenerateTemplate = async (input: PrepareInput) => {
    if (!agent) return;
    const up = uploadInputs[input.key] || { basic_info: "", file_content: "", file_name: "" };
    if (!up.basic_info && !up.file_content) {
      message.warning("请先填写基础信息或上传文件");
      return;
    }
    setGenState((s) => ({ ...s, [input.key]: true }));
    try {
      await agentApi.generateTemplate(agent.id, {
        project_id: localProjectId,
        input_key: input.key,
        input_label: input.label,
        basic_info: up.basic_info,
        file_content: up.file_content,
        file_name: up.file_name,
      });
      message.success(`已生成「${input.label}」统一模板`);
      await startRetrieval();
    } catch (e: any) {
      message.error(e?.message || "生成模板失败");
    } finally {
      setGenState((s) => ({ ...s, [input.key]: false }));
    }
  };

  // 阶段二/三：调用 run-material；慢模式逐条动画工具技术运用过程，快模式直接出结果
  const doExecute = async () => {
    if (!agent || !prepare) return;
    if ((prepare.missing_required || []).length > 0) {
      message.error("仍有必选输入物料缺失，请先上传并生成模板");
      return;
    }
    setRunning(true);
    setPhase("running");
    const input_refs: Record<string, string> = {};
    for (const it of prepare.inputs) {
      if (it.enabled === false) continue;
      if (it.exists && it.ref) input_refs[it.key] = it.ref;
    }
    // 与后端口径一致：启用 ∩ 已勾选
    const toolsToAnimate = (prepare.tools || [])
      .filter((t) => t.enabled !== false && (selectedTools.length === 0 || selectedTools.includes(t.key)))
      .map((t) => ({ key: t.key, label: t.label }));

    const runPromise = agentApi
      .runMaterial(agent.id, {
        project_id: localProjectId,
        input_refs,
        selected_tools: selectedTools,
        user_input: userInput,
      })
      .then((res: any) => res.outputs || [])
      .catch((e: any) => { throw e; });

    try {
      if (mode === "fast") {
        const outs = await runPromise;
        if (cancelledRef.current) return;
        setOutputs(outs);
        setPhase("result");
      } else {
        setToolAnim(toolsToAnimate.map((t) => ({ ...t, status: "pending" as ToolStatus })));
        for (let i = 0; i < toolsToAnimate.length; i++) {
          if (cancelledRef.current) return;
          setToolAnim((arr) => arr.map((t, idx) => (idx === i ? { ...t, status: "running" } : t)));
          await delay(680);
          if (cancelledRef.current) return;
          setToolAnim((arr) => arr.map((t, idx) => (idx === i ? { ...t, status: "done" } : t)));
        }
        const outs = await runPromise;
        if (cancelledRef.current) return;
        setOutputs(outs);
        setPhase("result");
      }
    } catch (e: any) {
      if (cancelledRef.current) return;
      setErrorMsg(e?.message || "执行失败");
      setPhase("error");
    } finally {
      if (!cancelledRef.current) setRunning(false);
    }
  };

  const download = async (out: any) => {
    try {
      const blob = await agentApi.downloadMaterial(out.ref, localProjectId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${out.title || out.ref}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e?.message || "下载失败");
    }
  };

  const onModeChange = (checked: boolean) => {
    const m: RunMode = checked ? "fast" : "slow";
    setMode(m);
    try { localStorage.setItem("agent_run_mode", m); } catch {}
  };

  const stepCurrent = phase === "retrieval" ? 0 : phase === "running" ? 1 : 2;
  const missingCount = prepare?.missing_required?.length || 0;
  const effectiveProjectId = localProjectId || projectId;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={800}
      footer={null}
      destroyOnClose
      title={
        <Space>
          <PlayCircleOutlined style={{ color: "#4F46E5" }} />
          <span>运行 Agent · {agent?.name || ""}</span>
          {agent && <Tag color="purple">{agent.id}</Tag>}
        </Space>
      }
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
        <Steps
          current={stepCurrent}
          size="small"
          items={[
            { title: "检索输入" },
            { title: "运用工具技术" },
            { title: "输出结果" },
          ]}
          style={{ flex: 1, minWidth: 300 }}
        />
        <Tooltip title="快速模式：跳过工具技术运用动画，直接显示最终输出；慢速模式：逐步展示每个工具技术的应用过程">
          <Space size={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>慢速</Text>
            <Switch size="small" checked={mode === "fast"} onChange={onModeChange} />
            <Text type="secondary" style={{ fontSize: 12 }}>快速</Text>
          </Space>
        </Tooltip>
      </div>

      {!effectiveProjectId && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="未选择目标项目"
          description={
            <Space wrap>
              <span>物料工作区按项目隔离；可在下方选择项目后再运行，否则物料存入全局空间：</span>
              <Select
                style={{ width: 220 }}
                placeholder="选择目标项目"
                allowClear
                value={localProjectId}
                onChange={setLocalProjectId}
                options={projects.map((p) => ({ value: p.id, label: p.name }))}
              />
            </Space>
          }
        />
      )}

      {/* 阶段一：检索过程 + 结果 */}
      {phase === "retrieval" && (
        <div>
          {!prepare ? (
            <div style={{ padding: 36, textAlign: "center" }}>
              <Spin />
              <p style={{ marginTop: 10 }}>正在检索所需输入文件…</p>
            </div>
          ) : (
            <>
              <Alert
                type={missingCount ? "error" : "success"}
                showIcon
                style={{ marginBottom: 12 }}
                message={missingCount
                  ? `有 ${missingCount} 项必选输入物料缺失，需先上传并生成模板`
                  : "物料检索完成：所有必选输入均已存在（含项目知识库匹配）"}
              />
              <List
                size="small"
                bordered
                dataSource={(prepare.inputs || []).filter((i) => i.enabled !== false)}
                renderItem={(it: PrepareInput) => {
                  const st = retrieval[it.key] || "scanning";
                  return (
                    <List.Item>
                      <div style={{ width: "100%" }}>
                        <Space style={{ width: "100%", justifyContent: "space-between" }}>
                          <Space>
                            <Text strong>{it.label}</Text>
                            {it.optional && <Tag>可选</Tag>}
                            {st === "scanning" && <Tag icon={<LoadingOutlined />} color="processing">检索中…</Tag>}
                            {st === "found" && <Tag color="green" icon={<CheckCircleOutlined />}>已找到</Tag>}
                            {st === "missing" && <Tag color="red" icon={<ExclamationCircleOutlined />}>缺失</Tag>}
                          </Space>
                          {st === "found" && it.ref && (
                            <Button size="small" type="link" icon={<CloudDownloadOutlined />} onClick={() => download({ ref: it.ref, title: it.title })}>下载</Button>
                          )}
                          {st === "found" && !it.ref && it.source === "project_kb" && <Tag color="blue">来自项目知识库</Tag>}
                        </Space>
                        {st === "missing" && (
                          <div style={{ marginTop: 8, background: "#F8FAFC", padding: 8, borderRadius: 8 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>系统中无此输入材料：手工上传基础信息，由 AI 生成统一格式模板。</Text>
                            <TextArea
                              style={{ marginTop: 4 }}
                              rows={2}
                              placeholder="填写该输入的基础信息（关键字段 / 背景说明）"
                              value={(uploadInputs[it.key] || {}).basic_info || ""}
                              onChange={(e) => setUploadInputs((s) => ({ ...s, [it.key]: { ...(s[it.key] || { basic_info: "", file_content: "", file_name: "" }), basic_info: e.target.value } }))}
                            />
                            <Upload
                              style={{ marginTop: 6 }}
                              beforeUpload={(file) => {
                                const reader = new FileReader();
                                reader.onload = () => {
                                  setUploadInputs((s) => ({ ...s, [it.key]: { ...(s[it.key] || { basic_info: "", file_content: "", file_name: "" }), file_content: String(reader.result || ""), file_name: file.name } }));
                                };
                                reader.readAsText(file);
                                return false;
                              }}
                              showUploadList={false}
                              accept=".txt,.md,.csv,.json,.docx,.pdf"
                            >
                              <Button size="small" icon={<UploadOutlined />}>上传文件（作为基础信息）</Button>
                            </Upload>
                            {(uploadInputs[it.key]?.file_name) && <Tag style={{ marginLeft: 8 }} color="blue">{uploadInputs[it.key].file_name}</Tag>}
                            <Button size="small" type="primary" style={{ marginLeft: 8, marginTop: 6 }} loading={genState[it.key]} icon={<ThunderboltOutlined />} onClick={() => doGenerateTemplate(it)}>AI 生成模板</Button>
                          </div>
                        )}
                      </div>
                    </List.Item>
                  );
                }}
              />
              <div style={{ marginTop: 16, textAlign: "right" }}>
                <Button onClick={onClose}>取消</Button>
                <Button type="primary" style={{ marginLeft: 8 }} disabled={missingCount > 0} loading={running} icon={<SendOutlined />} onClick={doExecute}>
                  执行并生成结果 <RightOutlined />
                </Button>
              </div>
            </>
          )}
        </div>
      )}

      {/* 阶段二：工具技术运用过程（慢速模式动画；快速模式跳过） */}
      {phase === "running" && (
        <div>
          {mode === "fast" ? (
            <div style={{ padding: 40, textAlign: "center" }}>
              <Spin />
              <p style={{ marginTop: 10 }}>快速模式：正在生成结果…</p>
            </div>
          ) : (
            <div>
              <Alert type="info" showIcon style={{ marginBottom: 12 }} message="正在运用工具与技术处理输入物料" />
              <List
                size="small"
                bordered
                dataSource={toolAnim}
                renderItem={(t) => (
                  <List.Item>
                    <Space style={{ width: "100%", justifyContent: "space-between" }}>
                      <Space>
                        <ExperimentOutlined style={{ color: "#4F46E5" }} />
                        <Text strong>{t.label}</Text>
                      </Space>
                      {t.status === "pending" && <Tag>等待中</Tag>}
                      {t.status === "running" && <Tag icon={<LoadingOutlined />} color="processing">执行中…</Tag>}
                      {t.status === "done" && <Tag color="green" icon={<CheckOutlined />}>已完成</Tag>}
                    </Space>
                  </List.Item>
                )}
              />
            </div>
          )}
        </div>
      )}

      {/* 阶段三：最终结果（Markdown） */}
      {phase === "result" && (
        <div>
          <Alert type="success" showIcon style={{ marginBottom: 12 }} message="运行完成，以下为输出结果（Markdown）" />
          {(outputs || []).map((o: any, idx: number) => (
            <Card
              key={o.ref || idx}
              size="small"
              style={{ marginBottom: 12, borderRadius: 12 }}
              title={
                <Space>
                  <FileTextOutlined style={{ color: "#4F46E5" }} />
                  <span>{o.title || "输出"}</span>
                  {o.source === "template" && <Tag>模板物料</Tag>}
                </Space>
              }
              extra={
                <Button size="small" type="link" icon={<CloudDownloadOutlined />} onClick={() => download(o)}>下载</Button>
              }
            >
              <div
                style={{ fontSize: 14, lineHeight: 1.7, maxHeight: 460, overflow: "auto" }}
                dangerouslySetInnerHTML={{ __html: renderMarkdownToHtml(o.content || "") }}
              />
            </Card>
          ))}
          <div style={{ textAlign: "right" }}>
            <Button onClick={onClose}>完成</Button>
            <Button type="primary" style={{ marginLeft: 8 }} icon={<ReloadOutlined />} onClick={() => { setOutputs(null); startRetrieval(); }}>重新运行</Button>
          </div>
        </div>
      )}

      {/* 错误态 */}
      {phase === "error" && (
        <Alert
          type="error"
          showIcon
          message="运行失败"
          description={errorMsg}
          action={<Button size="small" onClick={() => startRetrieval()}>重试</Button>}
        />
      )}
    </Modal>
  );
};

export default AgentRunDialog;
