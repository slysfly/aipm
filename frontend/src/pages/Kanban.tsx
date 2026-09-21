import React, { useState, useCallback, useEffect } from "react";
import { Card, Button, Tag, Typography, Spin, Empty, App, Modal, Form, Input, Select, message, Space, Dropdown, Drawer, Progress } from "antd";
import { PlusOutlined, MoreOutlined, EditOutlined, DeleteOutlined, RightCircleOutlined, ZoomInOutlined, ZoomOutOutlined, FullscreenOutlined } from "@ant-design/icons";
import { DndContext, DragOverlay, closestCorners, KeyboardSensor, PointerSensor, useSensor, useSensors, useDroppable, type DragStartEvent, type DragEndEvent, type DragOverEvent } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { motion } from "framer-motion";
import { taskApi, projectApi, sprintApi, membersApi } from "../api";

const { Text, Title } = Typography;

const STATUS_COLUMNS = [
  { key: "backlog", label: "待办池", color: "#64748B", bg: "#F8FAFC" },
  { key: "todo", label: "待办", color: "#94A3B8", bg: "#F1F5F9" },
  { key: "in_progress", label: "进行中", color: "#3B82F6", bg: "#EFF6FF" },
  { key: "in_review", label: "审查", color: "#F59E0B", bg: "#FFFBEB" },
  { key: "testing", label: "测试", color: "#8B5CF6", bg: "#F5F3FF" },
  { key: "done", label: "已完成", color: "#10B981", bg: "#ECFDF5" },
  { key: "cancelled", label: "已取消", color: "#94A3B8", bg: "#F1F5F9" },
];

// 与后端 TaskStatus 枚举保持一致（见 backend/app/models/__init__.py）
const STATUS_MAP: Record<string, string> = {
  backlog: "backlog",
  todo: "todo",
  in_progress: "in_progress",
  in_review: "in_review",
  testing: "testing",
  done: "done",
  cancelled: "cancelled",
};

interface TaskCardProps {
  task: any;
  onClick: (task: any) => void;
  userMap?: Record<string, string>;
}

const TaskCard: React.FC<TaskCardProps> = ({ task, onClick, userMap = {} }) => {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.id,
    data: { type: "task", task },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    cursor: "grab",
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners} onClick={() => onClick(task)}>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        style={{
          background: "#fff", borderRadius: 10, padding: 12, marginBottom: 8,
          border: "1px solid #E2E8F0", boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
          transition: "all 0.2s",
          cursor: "pointer",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.08)"; e.currentTarget.style.borderColor = "#4F46E5"; }}
        onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "0 1px 2px rgba(0,0,0,0.04)"; e.currentTarget.style.borderColor = "#E2E8F0"; }}
      >
        <Text strong style={{ fontSize: 13, display: "block", marginBottom: 6 }}>{task.name}</Text>
        {task.description && (
          <Text type="secondary" style={{ fontSize: 11, display: "block", marginBottom: 8 }} ellipsis>
            {task.description}
          </Text>
        )}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {task.priority && (
            <Tag color={task.priority <= 2 ? "red" : task.priority === 3 ? "orange" : "blue"} style={{ fontSize: 10, lineHeight: "18px", borderRadius: 4 }}>
              {task.priority <= 2 ? "高" : task.priority === 3 ? "中" : "低"}
            </Tag>
          )}
          {task.assignee && (
            <Tag style={{ fontSize: 10, lineHeight: "18px", borderRadius: 4, background: "#EEF2FF", border: "none" }}>
              {(() => {
              const id = typeof task.assignee === 'string' ? task.assignee : task.assignee?.id;
              if (id && userMap[id]) return userMap[id];
              if (task.assignee?.full_name) return task.assignee.full_name;
              if (task.assignee?.name) return task.assignee.name;
              if (task.assignee?.username) return task.assignee.username;
              return id ? id.substring(0, 8) + '...' : '--';
            })()}
            </Tag>
          )}
        </div>
      </motion.div>
    </div>
  );
};

const DroppableColumn: React.FC<{ id: string; children: React.ReactNode }> = ({ id, children }) => {
  const { setNodeRef } = useDroppable({ id });
  return <div ref={setNodeRef} style={{ flex: 1, overflowY: "auto", minHeight: 100 }}>{children}</div>;
};

const Kanban: React.FC = () => {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [tasks, setTasks] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(undefined);
  const [sprints, setSprints] = useState<any[]>([]);
  const [activeTask, setActiveTask] = useState<any>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<any>(null);
  const [userMap, setUserMap] = useState<Record<string, string>>({});
  const [kanbanScale, setKanbanScale] = useState(1.0);
  const [detailOpen, setDetailOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor)
  );

  const loadMembers = async (projectId: string) => {
    if (!projectId) { setUserMap({}); return; }
    try {
      const res = await membersApi.list(projectId, { page_size: 500 });
      const map: Record<string, string> = {};
      (res?.items || []).forEach((m: any) => {
        if (m.user_id && m.user?.name) {
          map[m.user_id] = m.user.name;
        }
      });
      setUserMap(map);
    } catch (e) {
      setUserMap({});
    }
  };

  const loadTasks = async () => {
    try {
      const res = await taskApi.list({ page_size: 200, project_id: selectedProjectId });
      setTasks(res?.items || []);
    } catch (e: any) {
      message.error("加载任务失败");
    } finally {
      setLoading(false);
    }
  };

  const loadProjects = async () => {
    try {
      const res = await projectApi.list({ page_size: 100 });
      setProjects(res?.items || []);
    } catch (_) {}
  };

  useEffect(() => {
    loadProjects();
    loadTasks();
  }, []);

  useEffect(() => {
    if (selectedProjectId) {
      loadMembers(selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    loadTasks();
  }, [selectedProjectId]);

  // AI 项目经理「直接操作系统」执行成功后自动刷新看板（跨组件 CustomEvent，与组织管理页同一约定）
  useEffect(() => {
    const onTasksChanged = () => { loadTasks(); };
    window.addEventListener("aipm:tasks-changed", onTasksChanged);
    return () => window.removeEventListener("aipm:tasks-changed", onTasksChanged);
  }, [selectedProjectId]);

  // 切换项目时重新加载该项目的 Sprint 列表
  useEffect(() => {
    if (!selectedProjectId) { setSprints([]); return; }
    sprintApi.list({ project_id: selectedProjectId, page_size: 200 }).then((r: any) => setSprints(r?.items || [])).catch(() => setSprints([]));
  }, [selectedProjectId]);

  const getColumnTasks = (status: string) => {
    return tasks.filter((t) => (t.status || "todo") === status);
  };

  const handleDragStart = (event: DragStartEvent) => {
    const task = tasks.find((t) => t.id === event.active.id);
    if (task) setActiveTask(task);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    setActiveTask(null);
    const { active, over } = event;
    if (!over) return;

    const taskId = active.id as string;
    const overId = over.id as string;

    // 若拖到的是某一列（空列拖放区），直接以该列状态为目标
    const targetColumn = STATUS_COLUMNS.find((c) => c.key === overId);
    let overStatus: string;
    if (targetColumn) {
      overStatus = targetColumn.key;
    } else {
      const overTask = tasks.find((t) => t.id === overId);
      if (!overTask) return;
      overStatus = overTask.status || "todo";
    }

    const task = tasks.find((t) => t.id === taskId);
    if (task && task.status !== overStatus) {
      try {
        await taskApi.update(taskId, { status: overStatus });
        setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: overStatus } : t));
      } catch {
        message.error("更新状态失败");
      }
    }
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over) return;
    // We update status during dragEnd, not dragOver for simplicity
  };

  const handleCardClick = (task: any) => {
    setActiveTask(task);
    setDetailOpen(true);
  };

  const handleCreateTask = () => {
    if (!selectedProjectId) {
      message.warning("请先在右上角选择一个项目，再创建任务");
      return;
    }
    setEditingTask({ name: "", description: "", priority: 3, status: "todo", project_id: selectedProjectId });
    setModalOpen(true);
  };

  const handleZoomIn = () => setKanbanScale(s => Math.min(2.0, s + 0.1));
  const handleZoomOut = () => setKanbanScale(s => Math.max(0.5, s - 0.1));
  const handleZoomFit = () => setKanbanScale(1.0);

  const handleSaveTask = async (values: any) => {
    try {
      if (editingTask?.id) {
        const headers: Record<string, string> = {};
        if (editingTask.version) {
          headers['X-Base-Version'] = String(editingTask.version);
        }
        const res = await taskApi.update(editingTask.id, values, headers);
        setTasks((prev) => prev.map((t) => t.id === editingTask.id ? { ...t, ...values, version: res?.version || editingTask.version } : t));
      } else {
        const payload = { ...values, project_id: selectedProjectId };
        const res = await taskApi.create(payload);
        setTasks((prev) => [...prev, res]);
      }
      setModalOpen(false);
      setEditingTask(null);
    } catch (e: any) {
      // 409 乐观锁冲突：提示用户并重新加载最新版本
      if (e?.response?.status === 409) {
        const conflict = e.response.data;
        if (conflict?.server_data) {
          message.warning('任务已被他人修改，已加载最新版本，请重新编辑');
          // 更新editingTask为服务器最新版本
          setEditingTask({ ...conflict.server_data, version: conflict.server_version });
          setTasks((prev) => prev.map((t) => t.id === conflict.entity_id ? { ...t, ...conflict.server_data, version: conflict.server_version } : t));
        } else {
          message.error("操作失败：任务冲突");
        }
      } else {
        message.error(e?.response?.data?.detail || "操作失败");
      }
    }
  };

  if (loading) {
    return <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spin size="large" /></div>;
  }

  // 详情抽屉
  const TaskDetailDrawer = () => (
    <Drawer
      title={<Space><EditOutlined />任务详情</Space>}
      placement="right"
      width={480}
      open={detailOpen}
      onClose={() => setDetailOpen(false)}
      extra={
        <Button type="primary" icon={<EditOutlined />} onClick={() => { setDetailOpen(false); setEditingTask(activeTask); setModalOpen(true); }}>
          编辑
        </Button>
      }
    >
      {activeTask && (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Text type="secondary">标题</Text>
            <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>{activeTask.name || "—"}</div>
          </div>
          <div>
            <Text type="secondary">描述</Text>
            <div style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>{activeTask.description || "—"}</div>
          </div>
          <div style={{ display: "flex", gap: 24 }}>
            <div>
              <Text type="secondary">状态</Text>
              <div style={{ marginTop: 4 }}><Tag color="blue">{activeTask.status || "—"}</Tag></div>
            </div>
            <div>
              <Text type="secondary">优先级</Text>
              <div style={{ marginTop: 4 }}>
                <Tag color={activeTask.priority <= 2 ? "red" : activeTask.priority === 3 ? "orange" : "green"}>
                  {activeTask.priority <= 2 ? "高" : activeTask.priority === 3 ? "中" : "低"}
                </Tag>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 24 }}>
            <div>
              <Text type="secondary">负责人</Text>
              <div style={{ marginTop: 4 }}>
                {(() => {
                  const id = typeof activeTask.assignee === 'string' ? activeTask.assignee : activeTask.assignee?.id;
                  if (id && userMap[id]) return userMap[id];
                  if (activeTask.assignee?.full_name) return activeTask.assignee.full_name;
                  if (activeTask.assignee?.name) return activeTask.assignee.name;
                  return id ? id.substring(0, 8) + '...' : '--';
                })()}
              </div>
            </div>
            <div>
              <Text type="secondary">进度</Text>
              <div style={{ marginTop: 4 }}>
                <Progress percent={activeTask.progress || 0} size="small" />
              </div>
            </div>
          </div>
          <div>
            <Text type="secondary">计划时间</Text>
            <div style={{ marginTop: 4, fontSize: 12 }}>
              {(activeTask.planned_start || activeTask.planned_end) ? (
                `${activeTask.planned_start || '—'} ~ ${activeTask.planned_end || '—'}`
              ) : '—'}
            </div>
          </div>
          <div>
            <Text type="secondary">创建时间</Text>
            <div style={{ marginTop: 4, fontSize: 12 }}>{activeTask.created_at || '—'}</div>
          </div>
        </Space>
      )}
    </Drawer>
  );

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>看板</Title>
          <Text type="secondary">通过拖拽改变任务状态；先选择项目可创建该项目的任务</Text>
        </div>
        <Space>
          <Select
            placeholder="选择项目筛选"
            data-tour="kanban-sel"
            allowClear
            style={{ width: 200 }}
            value={selectedProjectId}
            onChange={(val) => setSelectedProjectId(val)}
            options={projects.map((p: any) => ({ label: p.name, value: p.id }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateTask} disabled={!selectedProjectId} data-tour="kanban-add">
            创建任务
          </Button>
          <span style={{ margin: '0 8px', color: '#d9d9d9' }}>|</span>
          <Button size="small" icon={<ZoomOutOutlined />} onClick={handleZoomOut} title="缩小" />
          <span style={{ margin: '0 4px', fontSize: 12, color: '#666' }}>{Math.round(kanbanScale * 100)}%</span>
          <Button size="small" icon={<ZoomInOutlined />} onClick={handleZoomIn} title="放大" />
          <Button size="small" icon={<FullscreenOutlined />} onClick={handleZoomFit} title="适应" />
        </Space>
      </div>

      <div style={{ transform: `scale(${kanbanScale})`, transformOrigin: 'top left', transition: 'transform 0.2s', width: `${100/kanbanScale}%` }}>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
      >
        <div style={{ display: "flex", gap: 12, overflow: "auto", paddingBottom: 12 }}>
          {STATUS_COLUMNS.map((col, colIdx) => {
            const colTasks = getColumnTasks(col.key);
            return (
              <div
                key={col.key}
                style={{
                  minWidth: 280, maxWidth: 320, flex: 1,
                  background: col.bg, borderRadius: 14,
                  padding: 12, display: "flex", flexDirection: "column",
                  maxHeight: "calc(100vh - 180px)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, padding: "0 4px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", background: col.color }} />
                    <Text strong style={{ fontSize: 13, color: "#0F172A" }}>{col.label}</Text>
                    <Tag style={{ fontSize: 10, borderRadius: 8, lineHeight: "18px" }}>{colTasks.length}</Tag>
                  </div>
                </div>

                <DroppableColumn id={col.key}>
                  <SortableContext items={colTasks.map(t => t.id)} strategy={verticalListSortingStrategy}>
                    {colTasks.length === 0 ? (
                      <div style={{ padding: 20, textAlign: "center" }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>拖拽任务到此处</Text>
                      </div>
                    ) : (
                      colTasks.map((task) => (
                        <TaskCard key={task.id} task={task} onClick={handleCardClick} userMap={userMap} />
                      ))
                    )}
                  </SortableContext>
                </DroppableColumn>
              </div>
            );
          })}
        </div>

        <DragOverlay>
          {activeTask && (
            <div style={{
              background: "#fff", borderRadius: 10, padding: 12,
              border: "2px solid #4F46E5", boxShadow: "0 10px 30px rgba(0,0,0,0.15)",
              width: 260, transform: "rotate(3deg)",
            }}>
              <Text strong>{activeTask.name}</Text>
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {/* 编辑/创建任务弹窗 */}
      <Modal
        title={editingTask?.id ? "编辑任务" : "创建任务"}
        open={modalOpen}
        onCancel={() => { setModalOpen(false); setEditingTask(null); }}
        footer={null}
        destroyOnClose
      >
        <Form
          layout="vertical"
          initialValues={editingTask || {}}
          onFinish={handleSaveTask}
        >
          <Form.Item label="标题" name="name" rules={[{ required: true, message: "请输入任务标题" }]}>
            <Input placeholder="例如：完成登录模块开发" />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} placeholder="例如：实现用户名/密码登录，含表单校验与错误提示" />
          </Form.Item>
          <Form.Item label="优先级" name="priority" initialValue={3}>
            <Select style={{ width: 130 }} options={[{ label: "高", value: 1 }, { label: "中", value: 3 }, { label: "低", value: 5 }]} />
          </Form.Item>
          <Form.Item label="状态" name="status">
            <Select options={STATUS_COLUMNS.map(c => ({ label: c.label, value: c.key }))} />
          </Form.Item>
          <Form.Item label="所属 Sprint" name="sprint_id" tooltip="仅显示当前选中项目下的 Sprint，可留空">
            <Select
              allowClear
              disabled={!sprints.length}
              options={sprints.map((s: any) => ({ value: s.id, label: s.name }))}
              placeholder={sprints.length ? "选择 Sprint（可留空）" : "该项目暂无 Sprint"}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              {editingTask?.id ? "保存" : "创建"}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
      <TaskDetailDrawer />
      </div>
    </div>
  );
};

export default Kanban;
