import React, { useState, useRef, useEffect } from "react";
import { Card, Button, Typography, Space, Tooltip, message, Input, ColorPicker, Dropdown } from "antd";
import { PlusOutlined, DeleteOutlined, BgColorsOutlined, UndoOutlined, ClearOutlined, DragOutlined, BorderOutlined, MinusOutlined, FontSizeOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { boardApi } from "../api";

const { Title, Text } = Typography;

// 便签对象
interface Note {
  id: string;
  text: string;
  x: number;
  y: number;
  color: string;
  width: number;
  height: number;
}

const CANVAS_WIDTH = 2000;
const CANVAS_HEIGHT = 1500;
const NOTE_WIDTH = 180;
const NOTE_HEIGHT = 140;

const COLORS = [
  "#FEF3C7", "#DBEAFE", "#D1FAE5", "#EDE9FE", "#FCE7F3",
  "#FFE4E6", "#E0E7FF", "#CCFBF1", "#F5F5F4", "#F0F9FF",
];

const Whiteboard: React.FC = () => {
  const [notes, setNotes] = useState<Note[]>([]);
  const boardIdRef = useRef<string | null>(null);
  const loadedRef = useRef(false);
  const historyRef = useRef<Note[][]>([]);
  const dragStartRef = useRef<Note[] | null>(null);
  const [canUndo, setCanUndo] = useState(false);

  const pushHistory = (snapshot: Note[]) => {
    historyRef.current.push(snapshot);
    if (historyRef.current.length > 50) historyRef.current.shift();
    setCanUndo(true);
  };

  // 加载白板：复用首个白板，没有则自动创建
  useEffect(() => {
    (async () => {
      try {
        const r: any = await boardApi.list();
        const items: any[] = r?.items || [];
        if (items.length) {
          boardIdRef.current = items[0].id;
          setNotes(items[0].notes || []);
        } else {
          const created: any = await boardApi.create({ title: "主白板", notes: [] });
          boardIdRef.current = created.id;
        }
      } catch (e) {
        // 忽略加载错误，使用空白画布
      }
      loadedRef.current = true;
    })();
  }, []);

  // 便签变化时防抖持久化（字段与后端 NoteSchema 完全一致）
  useEffect(() => {
    if (!loadedRef.current || !boardIdRef.current) return;
    const t = setTimeout(() => {
      boardApi.save(boardIdRef.current!, { notes }).catch(() => {});
    }, 500);
    return () => clearTimeout(t);
  }, [notes]);

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [editingId, setEditingId] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const handleAddNote = () => {
    const newNote: Note = {
      id: Date.now().toString(),
      text: "新便签",
      x: 100 + Math.random() * 300,
      y: 100 + Math.random() * 200,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      width: NOTE_WIDTH,
      height: NOTE_HEIGHT,
    };
    setNotes((prev) => {
      pushHistory(prev);
      return [...prev, newNote];
    });
  };

  const handleDeleteNote = (id: string) => {
    setNotes((prev) => {
      pushHistory(prev);
      return prev.filter((n) => n.id !== id);
    });
  };

  const handleNoteMouseDown = (e: React.MouseEvent, note: Note) => {
    e.preventDefault();
    setDraggingId(note.id);
    setDragOffset({
      x: e.clientX - note.x,
      y: e.clientY - note.y,
    });

    const handleMouseMove = (e: MouseEvent) => {
      if (!draggingId) return;
      setNotes((prev) =>
        prev.map((n) =>
          n.id === draggingId
            ? { ...n, x: Math.max(0, e.clientX - dragOffset.x), y: Math.max(0, e.clientY - dragOffset.y) }
            : n
        )
      );
    };

    const handleMouseUp = () => {
      setDraggingId(null);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    // Using direct ref to avoid stale closure
    setDragOffset({ x: e.clientX - note.x, y: e.clientY - note.y });

    window.addEventListener("mousemove", (e) => {
      if (!draggingId) return;
      setNotes((prev) =>
        prev.map((n) =>
          n.id === draggingId
            ? { ...n, x: Math.max(0, e.clientX - dragOffset.x), y: Math.max(0, e.clientY - dragOffset.y) }
            : n
        )
      );
    });
    window.addEventListener("mouseup", () => {
      setDraggingId(null);
    });
  };

  const handleColorChange = (noteId: string, color: string) => {
    setNotes((prev) => {
      pushHistory(prev);
      return prev.map((n) => (n.id === noteId ? { ...n, color } : n));
    });
  };

  const handleClearAll = () => {
    if (notes.length === 0) return;
    pushHistory(notes);
    setNotes([]);
  };

  const undo = () => {
    const prev = historyRef.current.pop();
    if (prev === undefined) {
      setCanUndo(false);
      return;
    }
    setNotes(prev);
    setCanUndo(historyRef.current.length > 0);
  };

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>白板</Title>
          <Text type="secondary">自由画布，协作头脑风暴，拖拽便签整理思路</Text>
        </div>
        <Space>
          <Tooltip title="撤销">
            <Button icon={<UndoOutlined />} onClick={undo} disabled={!canUndo}>撤销</Button>
          </Tooltip>
          <Tooltip title="添加便签">
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAddNote} data-tour="whiteboard-add">添加便签</Button>
          </Tooltip>
          <Button icon={<ClearOutlined />} onClick={handleClearAll}>清空</Button>
        </Space>
      </div>

      <Card
        style={{
          borderRadius: 16, overflow: "hidden",
          border: "1px solid #E2E8F0", padding: 0,
        }}
        styles={{ body: { padding: 0 } }}
      >
        <div
          ref={canvasRef}
          data-tour="whiteboard-canvas"
          style={{
            width: "100%",
            height: "calc(100vh - 200px)",
            minHeight: 600,
            overflow: "auto",
            position: "relative",
            background: "linear-gradient(90deg, #F8FAFC 21px, transparent 1%) center, linear-gradient(#F8FAFC 21px, transparent 1%) center, #E2E8F0",
            backgroundSize: "22px 22px",
            borderRadius: 16,
          }}
        >
          <div style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, position: "relative" }}>
            {notes.map((note) => (
              <motion.div
                key={note.id}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.2 }}
                style={{
                  position: "absolute",
                  left: note.x,
                  top: note.y,
                  width: note.width,
                  height: note.height,
                  background: note.color,
                  borderRadius: 12,
                  padding: 12,
                  cursor: draggingId === note.id ? "grabbing" : "grab",
                  boxShadow: draggingId === note.id
                    ? "0 20px 40px rgba(0,0,0,0.15)"
                    : "0 4px 12px rgba(0,0,0,0.08)",
                  zIndex: draggingId === note.id ? 100 : 1,
                  transition: "box-shadow 0.2s",
                  display: "flex", flexDirection: "column",
                }}
                onMouseDown={(e) => {
                  setDraggingId(note.id);
                  setDragOffset({ x: e.clientX - note.x, y: e.clientY - note.y });
                  dragStartRef.current = notes;
                  const mousemove = (ev: MouseEvent) => {
                    setNotes((prev) => prev.map((n) => n.id === note.id ? { ...n, x: ev.clientX - dragOffset.x, y: ev.clientY - dragOffset.y } : n));
                  };
                  const mouseup = () => {
                    setDraggingId(null);
                    window.removeEventListener("mousemove", mousemove);
                    window.removeEventListener("mouseup", mouseup);
                    if (dragStartRef.current) {
                      pushHistory(dragStartRef.current);
                      dragStartRef.current = null;
                    }
                  };
                  window.addEventListener("mousemove", mousemove);
                  window.addEventListener("mouseup", mouseup);
                }}
                onDoubleClick={() => setEditingId(note.id)}
              >
                {/* 便签头部操作 */}
                <div
                  style={{
                    display: "flex", justifyContent: "space-between",
                    marginBottom: 8, opacity: 0, transition: "opacity 0.2s",
                  }}
                  className="note-actions"
                  onMouseEnter={(e) => e.currentTarget.style.opacity = "1"}
                >
                  <Space size={4}>
                    <ColorPicker
                      size="small"
                      value={note.color}
                      onChange={(c) => handleColorChange(note.id, c.toHexString())}
                      presets={[{ label: "Colors", colors: COLORS }]}
                    >
                      <div style={{ width: 16, height: 16, borderRadius: 4, background: note.color, cursor: "pointer", border: "1px solid rgba(0,0,0,0.1)" }} />
                    </ColorPicker>
                  </Space>
                  <DeleteOutlined
                    style={{ color: "#EF4444", fontSize: 12, cursor: "pointer" }}
                    onClick={(e) => { e.stopPropagation(); handleDeleteNote(note.id); }}
                  />
                </div>

                {/* 便签文本 */}
                {editingId === note.id ? (
                  <Input.TextArea
                    autoFocus
                    value={note.text}
                    onChange={(e) => setNotes((prev) => prev.map((n) => n.id === note.id ? { ...n, text: e.target.value } : n))}
                    onBlur={() => setEditingId(null)}
                    variant="borderless"
                    style={{ height: "100%", background: "transparent", fontSize: 12, lineHeight: 1.5, resize: "none" }}
                  />
                ) : (
                  <div style={{ fontSize: 12, lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word", height: "100%", cursor: "text" }}>
                    {note.text}
                  </div>
                )}
              </motion.div>
            ))}

            {/* 空状态 */}
            {notes.length === 0 && (
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div className="enhanced-empty">
                  <div style={{ fontSize: 48, marginBottom: 16 }}>🎨</div>
                  <h3>白板为空</h3>
                  <p>点击「添加便签」开始头脑风暴</p>
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleAddNote}>添加便签</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </Card>

      <style>{`
        .note-actions { opacity: 0; }
        div[style]:hover > .note-actions { opacity: 1 !important; }
      `}</style>
    </div>
  );
};

export default Whiteboard;
