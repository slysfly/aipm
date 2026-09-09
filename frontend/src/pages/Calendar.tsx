import React, { useState, useEffect } from "react";
import { Card, Button, Typography, Tag, Empty, App, Spin, Select, Space, Modal, Form, Input, DatePicker, message } from "antd";
import { PlusOutlined, LeftOutlined, RightOutlined, CalendarOutlined, ClockCircleOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { motion } from "framer-motion";
import { taskApi, projectApi, sprintApi } from "../api";

const { Title, Text } = Typography;

const startOfWeek = (d: dayjs.Dayjs): dayjs.Dayjs => {
  const day = d.day(); // 0=Sun .. 6=Sat
  const diff = day === 0 ? -6 : 1 - day; // 以周一为一周起点
  return d.add(diff, "day").startOf("day");
};

// 日历头部组件
const CalendarHeader: React.FC<{
  title: string;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}> = ({ title, onPrev, onNext, onToday }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
    <Button type="text" icon={<LeftOutlined />} onClick={onPrev} />
    <Title level={4} style={{ margin: 0, minWidth: 200, textAlign: "center" }}>{title}</Title>
    <Button type="text" icon={<RightOutlined />} onClick={onNext} />
    <Button type="default" onClick={onToday} style={{ borderRadius: 8, marginLeft: 8 }}>今天</Button>
  </div>
);

const Calendar: React.FC = () => {
  const { message: msg } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState<any[]>([]);
  const [currentDate, setCurrentDate] = useState(dayjs());
  const [view, setView] = useState<"month" | "week">("month");
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [createOpen, setCreateOpen] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);
  const [sprints, setSprints] = useState<any[]>([]);

  const loadTasks = async () => {
    try {
      const res = await taskApi.list({ page_size: 200 });
      setTasks(res?.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => {
    loadTasks();
    projectApi.list().then((r: any) => setProjects(r?.items || r || [])).catch(() => {});
  }, []);

  const prev = () => setCurrentDate(view === "month" ? currentDate.subtract(1, "month") : currentDate.subtract(1, "week"));
  const next = () => setCurrentDate(view === "month" ? currentDate.add(1, "month") : currentDate.add(1, "week"));
  const goToday = () => setCurrentDate(dayjs());

  // 任务按 planned_end（无则 due_date）落日历；无日期则不在日历显示
  const getTasksForDate = (dateStr: string) => tasks.filter((t) => {
    const d = t.planned_end || t.due_date;
    return d ? dayjs(d).format("YYYY-MM-DD") === dateStr : false;
  });

  const handleDayClick = (day: number, base: dayjs.Dayjs) => {
    const dateStr = base.date(day).format("YYYY-MM-DD");
    setSelectedDate(dateStr);
    setModalOpen(true);
  };

  const openCreate = (date?: string) => {
    form.resetFields();
    form.setFieldsValue({ planned_end: date ? dayjs(date) : dayjs(), priority: 3, status: "todo" });
    setCreateOpen(true);
  };

  // 按选中项目加载可选 Sprint
  const loadSprints = async (pid?: string) => {
    if (!pid) { setSprints([]); return; }
    try {
      const r: any = await sprintApi.list({ project_id: pid, page_size: 200 });
      setSprints(r?.items || []);
    } catch { setSprints([]); }
  };

  const onSubmit = async () => {
    const v = await form.validateFields();
    const payload: any = {
      name: v.name,
      project_id: v.project_id,
      description: v.description || "",
      priority: v.priority ?? 3,
      status: v.status || "todo",
      planned_end: v.planned_end ? v.planned_end.format("YYYY-MM-DDTHH:mm:ss") : undefined,
      sprint_id: v.sprint_id ?? null,
    };
    try {
      await taskApi.create(payload);
      msg.success("任务创建成功");
      setCreateOpen(false);
      loadTasks();
    } catch (e: any) {
      msg.error(e?.response?.data?.detail || "创建失败");
    }
  };

  const today = dayjs();
  const todayStr = today.format("YYYY-MM-DD");
  const weekDays = ["一", "二", "三", "四", "五", "六", "日"];
  const headerTitle = view === "month"
    ? currentDate.format("YYYY年 M月")
    : `${startOfWeek(currentDate).format("M月D日")} - ${startOfWeek(currentDate).add(6, "day").format("M月D日")}`;

  // 构建日期单元格
  const cells: React.ReactNode[] = [];
  if (view === "month") {
    const year = currentDate.year();
    const month = currentDate.month();
    const daysInMonth = currentDate.daysInMonth();
    const firstDayOfWeek = currentDate.startOf("month").day(); // 0=Sun
    const leading = (firstDayOfWeek === 0) ? 6 : firstDayOfWeek - 1; // 周一为起点
    for (let i = 0; i < leading; i++) {
      cells.push(<div key={`empty-${i}`} style={{ minHeight: 100, background: "#FAFAFA", borderRadius: 8, padding: 4 }} />);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      cells.push(renderDayCell(day, currentDate, `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`));
    }
  } else {
    const ws = startOfWeek(currentDate);
    for (let i = 0; i < 7; i++) {
      const d = ws.add(i, "day");
      const dateStr = d.format("YYYY-MM-DD");
      cells.push(renderDayCell(d.date(), d, dateStr, true));
    }
  }

  function renderDayCell(day: number, base: dayjs.Dayjs, dateStr: string, isWeek = false) {
    const isToday = dateStr === todayStr;
    const dayTasks = getTasksForDate(dateStr);
    return (
      <div
        key={isWeek ? `w-${dateStr}` : `m-${day}`}
        onClick={() => handleDayClick(day, base)}
        style={{
          minHeight: isWeek ? 180 : 100, borderRadius: 10, padding: 6,
          background: isToday ? "#EEF2FF" : "#fff",
          border: isToday ? "2px solid #4F46E5" : "1px solid #E2E8F0",
          cursor: "pointer", transition: "all 0.2s",
        }}
        onMouseEnter={(e) => { if (!isToday) e.currentTarget.style.borderColor = "#4F46E5"; }}
        onMouseLeave={(e) => { if (!isToday) e.currentTarget.style.borderColor = "#E2E8F0"; }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <span style={{ fontWeight: isToday ? 700 : 400, fontSize: 13, color: isToday ? "#4F46E5" : "#0F172A" }}>{day}</span>
          {isWeek && <Text type="secondary" style={{ fontSize: 10 }}>{weekDays[(base.day() + 6) % 7]}</Text>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {dayTasks.slice(0, 4).map((t: any) => (
            <div key={t.id} style={{
              fontSize: 10, padding: "1px 6px", borderRadius: 4,
              background: t.status === "done" ? "#ECFDF5" : (t.priority ?? 0) >= 4 ? "#FEF2F2" : "#F1F5F9",
              color: t.status === "done" ? "#10B981" : (t.priority ?? 0) >= 4 ? "#EF4444" : "#475569",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {t.name}
            </div>
          ))}
          {dayTasks.length > 4 && <Text type="secondary" style={{ fontSize: 10 }}>+{dayTasks.length - 4} 更多</Text>}
        </div>
      </div>
    );
  }

  if (loading) {
    return <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spin size="large" /></div>;
  }

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>日历</Title>
          <Text type="secondary">以日历视图查看所有任务的时间分布（按计划结束日期）</Text>
        </div>
        <Space>
          <Select value={view} style={{ width: 100 }} onChange={(v) => setView(v)} data-tour="cal-view"
            options={[{ label: "月视图", value: "month" }, { label: "周视图", value: "week" }]}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate()}>创建任务</Button>
        </Space>
      </div>

      <Card style={{ borderRadius: 16 }} className="card-hover" data-tour="cal-card">
        <CalendarHeader title={headerTitle} onPrev={prev} onNext={next} onToday={goToday} />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, marginBottom: 8 }}>
          {weekDays.map((d) => (
            <div key={d} style={{ textAlign: "center", fontWeight: 600, fontSize: 12, color: "#64748B", padding: "8px 0" }}>{d}</div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
          {cells}
        </div>
      </Card>

      <Modal
        title={`${selectedDate} 的任务`}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setSelectedDate(null); }}
        footer={null}
      >
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate(selectedDate || undefined)} style={{ marginBottom: 12 }}>
          在该日期新建任务
        </Button>
        {selectedDate && getTasksForDate(selectedDate).length === 0 ? (
          <Empty description="该日期暂无任务" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {selectedDate && getTasksForDate(selectedDate).map((t: any) => (
              <div key={t.id} style={{ padding: 12, borderRadius: 10, background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
                <Text strong style={{ fontSize: 13 }}>{t.name}</Text>
                <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                  <Tag style={{ borderRadius: 4, fontSize: 10 }}>{t.status}</Tag>
                  {t.priority && <Tag color={(t.priority ?? 0) >= 4 ? "red" : t.priority === 3 ? "orange" : "blue"} style={{ borderRadius: 4, fontSize: 10 }}>{(t.priority ?? 0) >= 4 ? "高" : t.priority === 3 ? "中" : "低"}</Tag>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Modal>

      <Modal title="新建任务" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={onSubmit} okText="创建" destroyOnClose width={560}>
        <Form form={form} layout="vertical">
          <Form.Item label="所属项目" name="project_id" rules={[{ required: true, message: "请选择项目" }]}>
            <Select
              placeholder="选择项目"
              options={projects.map((p: any) => ({ label: p.name, value: p.id }))}
              onChange={(v: string) => {
                form.setFieldsValue({ sprint_id: undefined });
                loadSprints(v);
              }}
            />
          </Form.Item>
          <Form.Item label="所属 Sprint" name="sprint_id" tooltip="仅显示当前选中项目下的 Sprint，可留空">
            <Select
              allowClear
              disabled={!sprints.length}
              options={sprints.map((s: any) => ({ value: s.id, label: s.name }))}
              placeholder={sprints.length ? "选择 Sprint（可留空）" : "请先选择所属项目"}
            />
          </Form.Item>
          <Form.Item label="任务名称" name="name" rules={[{ required: true, message: "请输入任务名称" }]}>
            <Input placeholder="例如：完成登录模块开发" />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
          <Space size={12}>
            <Form.Item label="计划结束日期" name="planned_end"><DatePicker style={{ width: 180 }} /></Form.Item>
            <Form.Item label="优先级" name="priority">
              <Select style={{ width: 120 }} options={[{ label: "高", value: 1 }, { label: "中", value: 3 }, { label: "低", value: 5 }]} />
            </Form.Item>
            <Form.Item label="状态" name="status">
              <Select style={{ width: 120 }} options={[{ label: "待办", value: "todo" }, { label: "进行中", value: "in_progress" }, { label: "已完成", value: "done" }]} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default Calendar;
