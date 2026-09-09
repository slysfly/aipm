import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Card, Select, Segmented, Button, Tooltip, Empty, Spin, App,
  DatePicker, Progress, Tag, Drawer, Form, Input, InputNumber, Space, Modal, Alert, Divider,
} from "antd";
import {
  LeftOutlined, RightOutlined, ReloadOutlined, CalendarOutlined, TeamOutlined,
  ProjectOutlined, PlusOutlined, ThunderboltOutlined, UndoOutlined, RobotOutlined,
} from "@ant-design/icons";
import { motion } from "framer-motion";
import dayjs from "dayjs";
import { resourceApi, resourceAllocationApi, projectApi, taskApi } from "../api";

const { RangePicker } = DatePicker;

const DAY = 86400000;
const COL_W = 104;
const RES_COL = 220;
const ROW_H = 72;          // 资源行高（增加以便放下工时数字）
const HEAD_H = 56;

const strip = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const diffDays = (a: Date, b: Date) => Math.round((strip(b).getTime() - strip(a).getTime()) / DAY);
const toDateStr = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fmtMD = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`;
const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const isWeekend = (d: Date) => d.getDay() === 0 || d.getDay() === 6;
const withAlpha = (hex: string, a: string) => (/^#[0-9a-fA-F]{6}$/.test(hex) ? `${hex}${a}` : hex);

const STATUS_LABEL: Record<string, string> = {
  backlog: "待办池", todo: "待开始", in_progress: "进行中", in_review: "评审中",
  testing: "测试中", done: "已完成", cancelled: "已取消", planned: "计划中", confirmed: "已确认",
};
const PRIORITY_LABEL: Record<number, string> = { 1: "紧急", 2: "高", 3: "中", 4: "低", 5: "最低" };
const PRIORITY_COLOR: Record<number, string> = { 1: "red", 2: "volcano", 3: "blue", 4: "default", 5: "default" };
const PROJECT_STATUS: Record<string, { label: string; color: string }> = {
  planning: { label: "规划中", color: "blue" },
  active: { label: "进行中", color: "green" },
  paused: { label: "已暂停", color: "orange" },
  completed: { label: "已完成", color: "default" },
  archived: { label: "已归档", color: "default" },
};

interface CalEvent {
  id: string; resourceId: string; taskId: string; title: string;
  projectId: string; projectName: string; projectColor: string;
  start: string; end: string; progress: number; status: string; priority: number;
  isAllocation?: boolean; allocationId?: string; hoursPerDay?: number; isAiMove?: boolean;
}
interface CalResource { id: string; name: string; type: string; department: string | null; skills: string[]; userId: string; resourceId: string | null; capacity?: number; }
interface DailyTotal { resourceId: string; date: string; totalHours: number; capacity: number; overload: number; }

interface Suggestion {
  allocationId: string; reason: string;
  fromStart?: string; fromEnd?: string; fromDailyHours?: number;
  toStart?: string; toEnd?: string; toDailyHours?: number;
  targetDate?: string; overloadDate?: string; freesHours?: number;
}

const MODE_SPAN: Record<string, number> = { week: 7, "2week": 14, month: 30 };

const ResourceCalendar: React.FC = () => {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const [data, setData] = useState<{
    range: { start: string; end: string };
    resources: CalResource[];
    events: CalEvent[];
    dailyTotals?: DailyTotal[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);
  const [resources, setResources] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [projectId, setProjectId] = useState<string | undefined>();
  const [mode, setMode] = useState<string>("2week");
  const [anchor, setAnchor] = useState<Date>(strip(new Date()));
  const [customRange, setCustomRange] = useState<[Date, Date] | null>(null);

  const [projectDetail, setProjectDetail] = useState<any>(null);
  const [projectStats, setProjectStats] = useState<any>(null);

  // 录入排程 Drawer
  const [addOpen, setAddOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const dailyHoursRef = useRef<any>(null); // antd Form.List 引用

  // AI 优化 Modal
  const [optOpen, setOptOpen] = useState(false);
  const [optLoading, setOptLoading] = useState(false);
  const [optResult, setOptResult] = useState<{ suggestions: Suggestion[]; summary: any } | null>(null);
  const [applyLoading, setApplyLoading] = useState(false);

  const span = mode === "custom"
    ? (customRange ? diffDays(customRange[0], customRange[1]) + 1 : 14)
    : (MODE_SPAN[mode] || 14);
  const start = mode === "custom"
    ? (customRange ? customRange[0] : anchor)
    : anchor;
  const end = mode === "custom"
    ? (customRange ? customRange[1] : new Date(anchor.getTime() + 13 * DAY))
    : new Date(start.getTime() + (span - 1) * DAY);

  const load = async () => {
    setLoading(true);
    try {
      const r: any = await resourceApi.calendar({
        start_date: toDateStr(start),
        end_date: toDateStr(end),
        project_id: projectId,
      });
      setData(r || { range: { start: toDateStr(start), end: toDateStr(end) }, resources: [], events: [] });
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载资源日历失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const [pr, rr, tk]: any[] = await Promise.all([
          projectApi.list(),
          resourceApi.list(),
          projectId ? taskApi.list({ project_id: projectId }) : Promise.resolve({ items: [] }),
        ]);
        setProjects(pr?.items || pr || []);
        setResources(rr?.items || rr || []);
        setTasks(tk?.items || tk || []);
      } catch { /* ignore */ }
    })();
  }, [projectId]);

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [anchor, mode, customRange, projectId]);

  useEffect(() => {
    if (!projectId) { setProjectDetail(null); setProjectStats(null); return; }
    let alive = true;
    (async () => {
      try {
        const [detail, stats]: any[] = await Promise.all([
          projectApi.get(projectId),
          projectApi.statistics(projectId),
        ]);
        if (!alive) return;
        setProjectDetail(detail || null);
        setProjectStats(stats || null);
      } catch {
        if (alive) { setProjectDetail(null); setProjectStats(null); }
      }
    })();
    return () => { alive = false; };
  }, [projectId]);

  const days = useMemo(() => Array.from({ length: span }, (_, i) => new Date(start.getTime() + i * DAY)), [start, span]);
  const todayOff = diffDays(start, strip(new Date()));
  const showToday = todayOff >= 0 && todayOff <= span - 1;

  const eventsByRes = useMemo(() => {
    const m = new Map<string, CalEvent[]>();
    (data?.events || []).forEach((ev) => {
      if (!m.has(ev.resourceId)) m.set(ev.resourceId, []);
      m.get(ev.resourceId)!.push(ev);
    });
    return m;
  }, [data]);

  const dailyTotalsByRes = useMemo(() => {
    const m = new Map<string, Map<string, DailyTotal>>();
    (data?.dailyTotals || []).forEach((d) => {
      if (!m.has(d.resourceId)) m.set(d.resourceId, new Map());
      m.get(d.resourceId)!.set(d.date, d);
    });
    return m;
  }, [data]);

  const shift = (dir: number) => {
    if (mode === "custom" && customRange) {
      setCustomRange([
        new Date(customRange[0].getTime() + dir * span * DAY),
        new Date(customRange[1].getTime() + dir * span * DAY),
      ]);
    } else {
      setAnchor(new Date(anchor.getTime() + dir * span * DAY));
    }
  };

  const onRangeChange = (dates: any) => {
    if (dates && dates[0] && dates[1]) {
      setMode("custom");
      setCustomRange([dates[0].toDate(), dates[1].toDate()]);
    }
  };

  const onModeChange = (v: string) => {
    setMode(v);
    if (v !== "custom") setCustomRange(null);
  };

  // ── 录入排程 ─────────────────────────────────────────────
  const onAdd = async () => {
    try {
      const v = await form.validateFields();
      const dr = v.dateRange as [any, any];
      const payload: any = {
        project_id: v.project_id,
        resource_id: v.resource_id,
        task_id: v.task_id || null,
        task_title: v.task_title || "",
        start_date: dr[0].format("YYYY-MM-DD"),
        end_date: dr[1].format("YYYY-MM-DD"),
        hours_per_day: v.hours_per_day,
        priority: v.priority || 3,
        notes: v.notes || "",
        status: "planned",
      };
      // daily_hours 覆盖
      const dhRaw = (v.daily_hours || []).filter((x: any) => x?.date && x?.hours);
      if (dhRaw.length) {
        payload.daily_hours = {};
        dhRaw.forEach((x: any) => { payload.daily_hours[x.date.format("YYYY-MM-DD")] = Number(x.hours); });
      }
      setSubmitting(true);
      await resourceAllocationApi.create(payload);
      message.success("已录入排程");
      setAddOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      if (e?.errorFields) return; // 校验未过
      message.error(e?.response?.data?.detail || e?.message || "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  // ── AI 优化 ─────────────────────────────────────────────
  const onOptimize = async () => {
    setOptLoading(true);
    setOptOpen(true);
    setOptResult(null);
    try {
      const r: any = await resourceAllocationApi.optimize({
        project_id: projectId,
        start_date: toDateStr(start),
        end_date: toDateStr(end),
      });
      setOptResult(r || { suggestions: [], summary: null });
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "AI 优化失败");
      setOptOpen(false);
    } finally {
      setOptLoading(false);
    }
  };

  const onApply = async (suggestions: Suggestion[] | "all") => {
    setApplyLoading(true);
    try {
      const payload: any = { project_id: projectId };
      if (suggestions === "all") {
        payload.suggestion_ids = "all";
      } else {
        payload.suggestions = suggestions;
      }
      const r: any = await resourceAllocationApi.applyOptimization(payload);
      message.success(`已应用 ${r?.appliedCount || 0} 条建议${r?.errors?.length ? `，失败 ${r.errors.length}` : ""}`);
      setOptOpen(false);
      load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "应用失败");
    } finally {
      setApplyLoading(false);
    }
  };

  return (
    <Card
      style={{ borderRadius: 16, marginTop: 16 }}
      className="card-hover"
      title={
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <CalendarOutlined style={{ color: "#7C3AED" }} /> 资源日历
          <span style={{ fontSize: 12, fontWeight: 400, color: "#94a3b8" }}>谁 · 在什么时候 · 干什么事儿 · 多少工时</span>
        </span>
      }
      extra={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Select
            allowClear placeholder="全部项目" style={{ width: 170 }}
            value={projectId} onChange={setProjectId}
            options={projects.map((p) => ({ label: p.name, value: p.id }))}
          />
          <RangePicker
            value={[dayjs(start), dayjs(end)]}
            onChange={onRangeChange}
            allowClear={false}
            style={{ width: 240 }}
            placeholder={["开始日期", "结束日期"]}
          />
          <Segmented
            value={mode}
            onChange={(v) => onModeChange(v as string)}
            options={[
              { label: "周", value: "week" },
              { label: "双周", value: "2week" },
              { label: "月", value: "month" },
              { label: "自定义", value: "custom" },
            ]}
          />
          <Button icon={<LeftOutlined />} onClick={() => shift(-1)} />
          <Button icon={<ReloadOutlined />} onClick={() => { setAnchor(strip(new Date())); setCustomRange(null); }} />
          <Button icon={<RightOutlined />} onClick={() => shift(1)} />
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={onOptimize} loading={optLoading}>
            AI 优化
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setAddOpen(true); }}>
            录入排程
          </Button>
        </div>
      }
    >
      {projectId && projectDetail && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center", padding: "12px 16px", marginBottom: 12, borderRadius: 12, background: "linear-gradient(135deg,#f5f3ff,#eef2ff)", border: "1px solid #e0e7ff" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ProjectOutlined style={{ color: projectDetail.color || "#7C3AED" }} />
            <span style={{ fontSize: 15, fontWeight: 700, color: "#1e293b" }}>{projectDetail.name}</span>
            <Tag color={PROJECT_STATUS[projectDetail.status]?.color}>{PROJECT_STATUS[projectDetail.status]?.label || projectDetail.status}</Tag>
          </div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            计划周期：{projectDetail.start_date || "—"} ~ {projectDetail.end_date || "—"}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 200 }}>
            <span style={{ fontSize: 12, color: "#64748b", whiteSpace: "nowrap" }}>项目进展</span>
            <Progress percent={Math.round(projectStats?.progress || 0)} size="small" style={{ width: 150 }} />
          </div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            任务 {projectStats?.task_count ?? 0} · 完成 {projectStats?.completed_task_count ?? 0} · 逾期{" "}
            <span style={{ color: (projectStats?.overdue_task_count || 0) > 0 ? "#ef4444" : "#64748b", fontWeight: 600 }}>{projectStats?.overdue_task_count ?? 0}</span>
          </div>
          <div style={{ fontSize: 12, color: "#7C3AED" }}>日历 = 该项目的任务计划 + 用户录入排程（按成员显示）</div>
        </div>
      )}

      <Spin spinning={loading && !data}>
        {(!data || data.resources.length === 0) ? (
          <Empty
            description={
              loading ? "加载中..." :
              <span>
                {projectId ? "该项目在此时间范围内暂无资源任务安排" : "该时间范围内暂无资源任务安排"}<br />
                <span style={{ color: "#94a3b8", fontSize: 12 }}>点右上「录入排程」先添加基础信息（谁/哪天/做什么/多少工时），再用「AI 优化」智能排程</span>
              </span>
            }
            style={{ padding: "40px 0" }}
          />
        ) : (
          <div style={{ display: "flex", border: "1px solid #f0f0f0", borderRadius: 12, overflow: "hidden" }}>
            {/* 左侧资源列 */}
            <div style={{ width: RES_COL, flexShrink: 0, borderRight: "1px solid #f0f0f0", background: "#fafafa" }}>
              <div style={{ height: HEAD_H, display: "flex", alignItems: "center", padding: "0 12px", fontWeight: 600, color: "#475569", borderBottom: "1px solid #f0f0f0" }}>
                <TeamOutlined style={{ marginRight: 6 }} /> 资源 / 成员
              </div>
              {data!.resources.map((r) => (
                <div key={r.id} style={{ height: ROW_H, display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 12px", borderBottom: "1px solid #f5f5f5" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 28, height: 28, borderRadius: "50%", flexShrink: 0, background: "linear-gradient(135deg,#4F46E5,#7C3AED)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>
                      {r.name.slice(0, 1)}
                    </div>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</div>
                      <div style={{ fontSize: 11, color: "#94a3b8", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.department || "—"}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 右侧时间轴 */}
            <div style={{ flex: 1, overflowX: "auto" }}>
              <div style={{ width: span * COL_W, position: "relative" }}>
                {/* 表头 */}
                <div style={{ height: HEAD_H, display: "flex", borderBottom: "1px solid #f0f0f0" }}>
                  {days.map((d, i) => (
                    <div key={i} style={{ width: COL_W, flexShrink: 0, textAlign: "center", fontSize: 11, color: isWeekend(d) ? "#ef4444" : "#64748b", borderLeft: i === 0 ? "none" : "1px solid #f5f5f5", paddingTop: 8, background: showToday && i === todayOff ? "#fef2f2" : "transparent" }}>
                      <div style={{ fontWeight: 600 }}>{fmtMD(d)}</div>
                      <div>周{WEEK[d.getDay()]}</div>
                    </div>
                  ))}
                </div>

                {/* 资源行 */}
                {data!.resources.map((r) => {
                  const resTotals = dailyTotalsByRes.get(r.userId) || new Map();
                  return (
                    <div key={r.id} style={{ height: ROW_H, position: "relative", borderBottom: "1px solid #f5f5f5" }}>
                      {/* 网格 + 每日过载高亮 */}
                      {days.map((d, i) => {
                        const ds = toDateStr(d);
                        const tot = resTotals.get(ds);
                        const overload = tot && tot.overload > 0;
                        return (
                          <div
                            key={i}
                            style={{
                              position: "absolute", left: i * COL_W, top: 0, bottom: 0, width: COL_W,
                              borderLeft: i === 0 ? "none" : "1px solid #f8fafc",
                              background: overload ? "rgba(239,68,68,0.12)" : (isWeekend(d) ? "#fafafa" : "transparent"),
                            }}
                            title={tot ? `${ds}：${tot.totalHours}h / 容量 ${tot.capacity}h${overload ? `（过载 ${tot.overload}h）` : ""}` : undefined}
                          />
                        );
                      })}
                      {showToday && (
                        <div style={{ position: "absolute", left: todayOff * COL_W + COL_W / 2, top: 0, bottom: 0, width: 2, background: "#ef4444", opacity: 0.7, zIndex: 5 }} />
                      )}
                      {/* 任务条 / 排程条 */}
                      {(eventsByRes.get(r.userId) || []).map((ev, idx) => {
                        const s = new Date(ev.start);
                        const e = new Date(ev.end);
                        const leftDays = Math.max(0, diffDays(start, s));
                        const rightDays = Math.min(span - 1, diffDays(start, e));
                        if (rightDays < 0 || leftDays > span - 1) return null;
                        const left = leftDays * COL_W + 4;
                        const width = Math.max(COL_W - 10, (rightDays - leftDays + 1) * COL_W - 8);
                        const color = ev.projectColor || (ev.isAllocation ? "#7C3AED" : "#1890ff");
                        return (
                          <motion.div
                            key={ev.id}
                            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.03 }}
                            style={{ position: "absolute", top: 8, height: ROW_H - 18, left, width, zIndex: 6, borderRadius: 8, overflow: "hidden", cursor: "pointer" }}
                          >
                            <Tooltip
                              title={
                                <div style={{ fontSize: 12, lineHeight: 1.7 }}>
                                  <div style={{ fontWeight: 700, fontSize: 13 }}>
                                    {ev.title}
                                    {ev.isAiMove && <Tag color="purple" style={{ marginLeft: 6 }}>AI 调整</Tag>}
                                  </div>
                                  <div><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: color, marginRight: 6 }} />{ev.projectName}</div>
                                  <div>时间：{ev.start.slice(0, 10)} ~ {ev.end.slice(0, 10)}</div>
                                  {ev.isAllocation && ev.hoursPerDay != null && (
                                    <div>每日工时：<b>{ev.hoursPerDay}h</b> · 总计 <b>{(ev.hoursPerDay * (rightDays - leftDays + 1)).toFixed(1)}h</b></div>
                                  )}
                                  {!ev.isAllocation && <div>进度：{ev.progress}%</div>}
                                  <div>状态：{STATUS_LABEL[ev.status] || ev.status} · 优先级：{PRIORITY_LABEL[ev.priority] || ev.priority}</div>
                                </div>
                              }
                            >
                              <div
                                style={{
                                  width: "100%", height: "100%", padding: "4px 8px", color: "#fff",
                                  background: ev.isAllocation
                                    ? (ev.isAiMove
                                      ? `linear-gradient(135deg, #a855f7 0%, #7c3aed 100%)`
                                      : `linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)`)
                                    : `linear-gradient(135deg, ${withAlpha(color, "e0")}, ${withAlpha(color, "b0")})`,
                                  borderLeft: `4px solid ${color}`,
                                  boxShadow: `0 4px 14px ${withAlpha(color, "55")}`,
                                  display: "flex", flexDirection: "column", justifyContent: "center",
                                  position: "relative",
                                }}
                              >
                                <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                  {ev.isAllocation ? "📅 " : ""}{ev.title}
                                </div>
                                <div style={{ fontSize: 10, opacity: 0.9, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                  {ev.projectName}{ev.isAllocation && ev.hoursPerDay != null ? ` · ${ev.hoursPerDay}h/天` : ""}
                                </div>
                                {ev.isAllocation && ev.hoursPerDay != null && (
                                  <div style={{ fontSize: 10, fontWeight: 700, marginTop: 2 }}>
                                    {ev.hoursPerDay}h
                                  </div>
                                )}
                                {!ev.isAllocation && (
                                  <div style={{ position: "absolute", left: 0, bottom: 0, height: 3, width: `${ev.progress}%`, background: "rgba(255,255,255,0.85)" }} />
                                )}
                              </div>
                            </Tooltip>
                          </motion.div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </Spin>

      {/* 录入排程 Drawer */}
      <Drawer
        title={<span><PlusOutlined /> 录入资源排程（基础信息）</span>}
        open={addOpen}
        onClose={() => setAddOpen(false)}
        width={560}
        extra={
          <Space>
            <Button onClick={() => setAddOpen(false)}>取消</Button>
            <Button type="primary" loading={submitting} onClick={onAdd}>保存排程</Button>
          </Space>
        }
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          message="录入基础信息（谁/哪天/做什么/多少工时）后，可用「AI 优化」自动检测过载并给出挪动建议。"
        />
        <Form form={form} layout="vertical" initialValues={{ priority: 3, hours_per_day: 4 }}>
          <Form.Item label="项目" name="project_id" rules={[{ required: true, message: "请选择项目" }]}>
            <Select
              showSearch optionFilterProp="label" placeholder="选择项目"
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
              onChange={async (v) => {
                if (!v) { setTasks([]); return; }
                try {
                  const r: any = await taskApi.list({ project_id: v });
                  setTasks(r?.items || r || []);
                } catch { setTasks([]); }
              }}
            />
          </Form.Item>
          <Form.Item label="资源 / 成员" name="resource_id" rules={[{ required: true, message: "请选择资源" }]}>
            <Select
              showSearch optionFilterProp="label" placeholder="选择资源"
              options={resources.map((r) => ({
                label: `${r.name}${r.department ? `（${r.department}）` : ""}${r.capacity ? ` · 容量 ${r.capacity}h/天` : ""}`,
                value: r.id,
              }))}
            />
          </Form.Item>
          <Form.Item label="关联任务（可选）" name="task_id">
            <Select
              allowClear showSearch optionFilterProp="label" placeholder="不关联则直接填写任务名称"
              options={tasks.map((t) => ({ label: t.name, value: t.id }))}
            />
          </Form.Item>
          <Form.Item label="任务名称" name="task_title" extra="如未关联任务，请填写任务名称">
            <Input placeholder="例如：完成需求评审" maxLength={255} />
          </Form.Item>
          <Form.Item label="日期范围" name="dateRange" rules={[{ required: true, message: "请选择起止日期" }]}>
            <RangePicker style={{ width: "100%" }} placeholder={["开始日期", "结束日期"]} />
          </Form.Item>
          <Form.Item label="每日工时（默认）" name="hours_per_day" rules={[{ required: true, message: "请输入每日工时" }]}>
            <InputNumber min={0.5} max={24} step={0.5} style={{ width: "100%" }} addonAfter="小时/天" />
          </Form.Item>
          <Divider style={{ margin: "12px 0" }}>每日工时覆盖（可选）</Divider>
          <Form.List name="daily_hours">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} align="baseline" style={{ display: "flex", marginBottom: 8 }}>
                    <Form.Item {...rest} name={[name, "date"]} rules={[{ required: true, message: "日期" }]}>
                      <DatePicker placeholder="日期" />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, "hours"]} rules={[{ required: true, message: "工时" }]}>
                      <InputNumber min={0.5} max={24} step={0.5} placeholder="工时" addonAfter="h" />
                    </Form.Item>
                    <Button type="link" danger onClick={() => remove(name)}>删除</Button>
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ date: null, hours: null })} block icon={<PlusOutlined />}>
                  添加某天特殊工时
                </Button>
              </>
            )}
          </Form.List>
          <Divider style={{ margin: "12px 0" }} />
          <Form.Item label="优先级" name="priority">
            <Select
              options={[1, 2, 3, 4, 5].map((p) => ({ label: PRIORITY_LABEL[p], value: p }))}
            />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={2} placeholder="可选" maxLength={500} />
          </Form.Item>
        </Form>
      </Drawer>

      {/* AI 优化 Modal */}
      <Modal
        title={<span><RobotOutlined style={{ color: "#7C3AED" }} /> AI 智能排程</span>}
        open={optOpen}
        onCancel={() => setOptOpen(false)}
        width={780}
        footer={
          optResult && optResult.suggestions.length > 0 ? [
            <Button key="cancel" onClick={() => setOptOpen(false)}>关闭</Button>,
            <Button
              key="applyAll"
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={applyLoading}
              onClick={() => onApply("all")}
            >
              全部应用（{optResult.suggestions.length}）
            </Button>,
          ] : [<Button key="ok" type="primary" onClick={() => setOptOpen(false)}>知道了</Button>]
        }
      >
        {optLoading ? (
          <div style={{ padding: "40px 0", textAlign: "center" }}><Spin tip="AI 正在分析排程..." /></div>
        ) : optResult ? (
          <>
            {optResult.summary && (
              <Alert
                style={{ marginBottom: 12 }}
                type={(optResult.summary.overloadCount || 0) > 0 ? "warning" : "success"}
                showIcon
                message={
                  <span>
                    共发现 <b>{optResult.suggestions.length}</b> 条建议
                    {optResult.summary.overloadCount > 0 && <span> · <b style={{ color: "#ef4444" }}>{optResult.summary.overloadCount}</b> 天过载</span>}
                    {optResult.summary.suggestionCount > 0 && <span> · <b>{optResult.summary.suggestionCount}</b> 条可应用</span>}
                  </span>
                }
              />
            )}
            {optResult.suggestions.length === 0 ? (
              <Empty description="当前排程已经很合理，无需调整 🎉" />
            ) : (
              <div style={{ maxHeight: 480, overflowY: "auto" }}>
                {optResult.suggestions.map((s) => (
                  <Card
                    key={s.allocationId + s.targetDate}
                    size="small"
                    style={{ marginBottom: 10 }}
                    title={<span style={{ fontSize: 13 }}>{s.reason}</span>}
                    extra={
                      <Button
                        size="small" type="primary" loading={applyLoading}
                        onClick={() => onApply([s])}
                      >
                        应用
                      </Button>
                    }
                  >
                    {s.fromStart && s.toStart && (
                      <div style={{ fontSize: 12 }}>
                        <span style={{ color: "#ef4444" }}>{s.fromStart} ~ {s.fromEnd}（{s.fromDailyHours ?? "—"}h/天）</span>
                        <span style={{ margin: "0 8px" }}>→</span>
                        <span style={{ color: "#10b981" }}>{s.toStart} ~ {s.toEnd}（{s.toDailyHours ?? "—"}h/天）</span>
                      </div>
                    )}
                    {s.freesHours != null && (
                      <div style={{ marginTop: 4, fontSize: 11, color: "#94a3b8" }}>
                        预计可释放 {s.freesHours.toFixed(1)}h 负载（{s.overloadDate}）
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </>
        ) : null}
      </Modal>
    </Card>
  );
};

export default ResourceCalendar;
