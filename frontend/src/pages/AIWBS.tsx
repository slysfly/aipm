import React, { useEffect, useState } from "react";
import {
  Card, Form, Input, Select, Button, Checkbox, App, Table, Tag, Empty, Alert, Typography, Progress, Radio,
} from "antd";
import { useSearchParams, useNavigate } from "react-router-dom";
import { aiApi, projectApi, knowledgeApi } from "../api";
import { useTaskProgress } from "../realtime/useRealtime";

const { Title, Paragraph } = Typography;

const AIWBS: React.FC = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [result, setResult] = useState<any>(null);
  const [projects, setProjects] = useState<any[]>([]);
  // AI 生成参照的知识库（单 scope：公开 / 本人私密 二选一，不可同时使用）
  const [kbList, setKbList] = useState<any[]>([]);
  const [kbChoice, setKbChoice] = useState<string>("none");
  const [taskId, setTaskId] = useState<string | null>(null);
  // 订阅后台 WBS 生成任务的实时进度/结果
  const task = useTaskProgress(taskId);
  const [form] = Form.useForm();

  useEffect(() => {
    projectApi.list({ page_size: 100 }).then((r) => setProjects(r?.items || [])).catch(() => {});
    // 拉取 AI 生成可用的知识库（公开库 + 本人私密库），默认优先使用公开库
    knowledgeApi.listAiSelectable().then((r: any) => {
      const list: any[] = r?.items || r || [];
      setKbList(list);
      const pub = list.find((k) => k.visibility === "public");
      setKbChoice(pub ? pub.id : (list[0]?.id ?? "none"));
    }).catch(() => {});
    const pid = params.get("projectId");
    if (pid) form.setFieldsValue({ project_id: pid, save_to_tasks: true });
  }, []);

  // 后台任务完成后：用结果刷新页面
  useEffect(() => {
    if (taskId && task.done) {
      const res = task.result || {};
      setResult(res);
      const pid = form.getFieldValue("project_id");
      if (pid && res?.created_task_count > 0) {
        message.success(`WBS 已生成并回写为 ${res.created_task_count} 个任务`);
      } else {
        message.success("WBS 已生成");
      }
      setTaskId(null);
    }
  }, [task.done, taskId]);

  useEffect(() => {
    if (taskId && task.failed) {
      message.error(task.error || "生成失败");
      setTaskId(null);
    }
  }, [task.failed, taskId]);

  const submit = async () => {
    try {
      const v = await form.validateFields();
      setResult(null);
      const r = await aiApi.generateWbs({
        project_name: v.project_name,
        project_description: v.project_description || "",
        industry_type: v.industry_type || "it_software",
        project_id: v.project_id || null,
        save_to_tasks: !!v.save_to_tasks,
        kb_id: kbChoice === "none" ? null : kbChoice,
      });
      if (r?.task_id) {
        // 后台异步执行：进度经 WebSocket 实时推送
        setTaskId(r.task_id);
      } else {
        message.error("未能创建后台任务");
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "生成失败");
    }
  };

  const wbs = result?.wbs_structure || [];
  const risks = result?.risk_identification || [];

  return (
    <div>
      <Title level={3}>AI 智能体 · WBS 生成</Title>
      <Paragraph type="secondary">
        输入项目信息，由 AI 生成工作分解结构（WBS），并可一键回写为真实任务与风险，打通 AI 产出与业务数据。
      </Paragraph>

      <Card title="生成参数">
        <Form form={form} layout="vertical">
          <Form.Item name="project_name" label="项目名称" rules={[{ required: true }]}>
            <Input placeholder="例如：PMI中国AI-PM V1.0 研发" data-tour="wbs-input" />
          </Form.Item>
          <Form.Item name="project_description" label="项目描述">
            <Input.TextArea rows={3} placeholder="例如：面向中小企业的项目管理 SaaS，含任务、看板、报表模块，6 人团队 3 个月交付" />
          </Form.Item>
          <Form.Item name="industry_type" label="行业类型" initialValue="it_software">
            <Select options={[
              { value: "it_software", label: "IT软件" },
              { value: "construction", label: "建筑工程" },
              { value: "consulting", label: "咨询" },
            ]} />
          </Form.Item>
          <Form.Item name="project_id" label="保存到项目（可选）">
            <Select allowClear placeholder="选择项目后，WBS 将回写为任务" options={projects.map((p: any) => ({ value: p.id, label: p.name }))} />
          </Form.Item>
          <Form.Item name="save_to_tasks" valuePropName="checked">
            <Checkbox>将生成的 WBS 与风险回写为真实任务/风险数据</Checkbox>
          </Form.Item>
          <Form.Item label="参照知识库（AI 生成将首先依据该库沉淀，公开/私密二选一）">
            <Radio.Group value={kbChoice} onChange={(e) => setKbChoice(e.target.value)}>
              {kbList.map((kb: any) => (
                <Radio key={kb.id} value={kb.id}>
                  {kb.visibility === "public" ? "🌐 " : "🔒 "}
                  {kb.name}
                  <Tag style={{ marginLeft: 6 }} color={kb.visibility === "public" ? "blue" : "default"}>
                    {kb.visibility === "public" ? "公开" : "私密"}
                  </Tag>
                </Radio>
              ))}
              <Radio value="none">不使用知识库</Radio>
            </Radio.Group>
          </Form.Item>
          <Button type="primary" loading={!!taskId && !task.done && !task.failed} onClick={submit} data-tour="wbs-gen">生成 WBS</Button>
        </Form>
      </Card>

      {taskId && !task.done && !task.failed && (
        <div style={{ marginTop: 24, padding: 16, background: "#F5F8FF", borderRadius: 12, border: "1px solid #D6E4FF" }}>
          <Progress percent={task.progress} status="active" />
          <Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            {task.message || "AI 正在后台生成 WBS 与风险清单，大模型推理通常需要 20~90 秒，期间可自由浏览其他页面，完成后将实时通知。"}
          </Paragraph>
        </div>
      )}

      {!loading && result && (
        <div style={{ marginTop: 16 }}>
          {wbs.length > 0 && (
            <Card title="WBS 结构">
              <Table
                rowKey={(r: any) => r.wbs_code || r.name}
                size="small"
                pagination={false}
                columns={[
                  { title: "WBS编码", dataIndex: "wbs_code", width: 100 },
                  { title: "名称", dataIndex: "name" },
                  { title: "工期(天)", dataIndex: "duration_days" },
                  { title: "阶段", dataIndex: "phase" },
                ]}
                dataSource={wbs}
              />
            </Card>
          )}
          {risks.length > 0 && (
            <Card title="识别到的风险" style={{ marginTop: 16 }}>
              <Table
                rowKey={(r: any) => r.name}
                size="small"
                pagination={false}
                columns={[
                  { title: "风险", dataIndex: "name" },
                  { title: "类别", dataIndex: "category", render: (c: string) => <Tag>{c}</Tag> },
                  { title: "概率", dataIndex: "probability" },
                  { title: "影响", dataIndex: "impact" },
                ]}
                dataSource={risks}
              />
            </Card>
          )}
          {result?.created_task_count > 0 && (
            <Alert
              style={{ marginTop: 16 }}
              type="success"
              showIcon
              message={`已回写 ${result.created_task_count} 个任务到项目`}
              action={<a onClick={() => navigate(`/tasks?projectId=${form.getFieldValue("project_id")}`)}>查看任务</a>}
            />
          )}
          {!wbs.length && !risks.length && <Empty description="未返回结构化结果" />}
        </div>
      )}
    </div>
  );
};

export default AIWBS;
