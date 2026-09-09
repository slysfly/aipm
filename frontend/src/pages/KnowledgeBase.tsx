import React, { useEffect, useState } from "react";
import {
  Card, Typography, Select, Button, Tree, Input, Modal, Form, Tag, Space,
  Empty, Spin, Popconfirm, App, Row, Col, List, Divider, Tabs, Checkbox,
  Drawer, Dropdown, Menu,
} from "antd";
import {
  PlusOutlined, SearchOutlined, DatabaseOutlined, DeleteOutlined, FileTextOutlined,
  ShareAltOutlined, FolderOpenOutlined, UploadOutlined, TeamOutlined, EditOutlined,
  FolderOutlined, FileOutlined, EyeOutlined, ProjectOutlined, CloseOutlined,
} from "@ant-design/icons";
import { knowledgeApi, projectApi } from "../api";
import { http } from "../api/http";
import FilePreview from "../components/FilePreview";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface KB {
  id: string; name: string; description?: string; document_count: number;
  access_role: string; visibility: string; is_shared: boolean; created_by: string;
  my_permission?: string;
  project_id?: string | null;
  project_name?: string | null;
}
interface ProjectLite { id: string; name: string; code?: string; }
interface DocItem {
  id: string; title: string; content?: string; source_type: string; status: string;
  chunk_count: number; created_at?: string; file_name?: string; meta_data?: any;
}
interface SearchHit {
  chunk_id: string; document_id: string; document_title: string;
  content: string; score: number; chunk_index: number; search_method: string;
}
interface ShareItem {
  id: string; kb_id: string; share_type: string; target_id?: string;
  target_name?: string; permission: string; created_by: string;
}
interface LiteUser { id: string; username: string; full_name?: string; email?: string; department?: string; }
interface GroupItem { id: string; name: string; description?: string; member_count: number; is_owner: boolean; }

const VISIBILITY_TAG: Record<string, { color: string; label: string }> = {
  private: { color: "default", label: "私有" },
  shared: { color: "blue", label: "已分享" },
  system: { color: "purple", label: "系统共享" },
};

/**
 * 轻量 Markdown → HTML（与文档板块一致的渲染，存储型 XSS 已通过 DOMPurify 防护）。
 * 富文本文档编辑能力从"文档"板块合并而来：点击文本类文档即可在此编辑并重新向量化入库。
 */
const renderMarkdownToHtml = (content: string): string => {
  const rawHtml = (content || "")
    .replace(/^### (.+)$/gm, '<h3 style="font-size:16px;font-weight:600;margin:16px 0 8px;color:#0F172A">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:18px;font-weight:700;margin:20px 0 10px;color:#0F172A">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:22px;font-weight:700;margin:24px 0 12px;color:#0F172A">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/- (.+)$/gm, '<li style="margin:4px 0;padding-left:8px;list-style-type:disc;margin-left:16px">$1</li>')
    .replace(/\n/g, '<br/>');
  return rawHtml;
};

// 由文档列表构建层级树：文本文档归入"文档"分组；文件按 file_name 中的目录结构归层。
interface TreeNode {
  key: string;
  title: React.ReactNode;
  children?: TreeNode[];
  doc?: DocItem;
  isLeaf?: boolean;
  selectable?: boolean;
}
const buildTreeData = (docs: DocItem[], onDelete: (id: string) => void, canWrite: boolean, onPreview: (d: DocItem) => void) => {
  const folderMap = new Map<string, TreeNode>();
  const rootChildren: TreeNode[] = [];
  const textChildren: TreeNode[] = [];

  const leafTitle = (d: DocItem) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", justifyContent: "space-between" }}>
      <span style={{ cursor: "pointer", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {d.source_type === "text" ? <FileTextOutlined style={{ marginRight: 6, color: "#4F46E5" }} /> : <FileOutlined style={{ marginRight: 6 }} />}
        {d.title || d.file_name || "(无标题)"}
      </span>
      <span style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        {d.source_type !== "text" && (<Button size="small" type="text" icon={<EyeOutlined />} onClick={(e) => { e.stopPropagation(); onPreview(d); }} />)}
        {d.source_type !== "text" && <Tag color={d.status === "completed" ? "green" : d.status === "failed" ? "red" : "orange"}>{d.status}</Tag>}
        {d.source_type !== "text" && <Text type="secondary" style={{ fontSize: 11 }}>{d.chunk_count} 分块</Text>}
        {canWrite && (
          <Popconfirm title="确认删除该文档?" onConfirm={() => onDelete(d.id)} okText="删除" cancelText="取消" okButtonProps={{ danger: true }}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
          </Popconfirm>
        )}
      </span>
    </div>
  );

  const makeLeaf = (d: DocItem): TreeNode => ({
    key: d.id,
    isLeaf: true,
    doc: d,
    title: leafTitle(d),
  });

  for (const d of docs) {
    if (d.source_type === "text") {
      textChildren.push(makeLeaf(d));
      continue;
    }
    const full = d.file_name || d.title || "unknown";
    const idx = full.lastIndexOf("/");
    const dir = idx >= 0 ? full.slice(0, idx) : "";
    const name = idx >= 0 ? full.slice(idx + 1) : full;
    const leaf: DocItem = { ...d, file_name: name };
    if (!dir) {
      rootChildren.push(makeLeaf(leaf));
    } else {
      const segs = dir.split("/");
      let parent = rootChildren;
      let acc = "";
      let container = rootChildren;
      // 逐级创建目录节点
      const ensurePath = () => {
        for (const seg of segs) {
          acc = acc ? `${acc}/${seg}` : seg;
          let node = folderMap.get(acc);
          if (!node) {
            node = {
              key: `dir::${acc}`,
              title: <span><FolderOutlined style={{ marginRight: 6, color: "#F59E0B" }} />{seg}</span>,
              children: [],
            };
            folderMap.set(acc, node);
            container.push(node);
          }
          container = node.children!;
        }
      };
      ensurePath();
      container.push(makeLeaf(leaf));
      void parent;
    }
  }

  const data: TreeNode[] = [];
  if (textChildren.length) {
    data.push({ key: "__docs__", title: <span><FileTextOutlined style={{ marginRight: 6, color: "#4F46E5" }} /><b>文档 ({textChildren.length})</b></span>, selectable: false, children: textChildren });
  }
  // 目录节点排前，零散文件排后
  const folders = rootChildren.filter((c) => c.children);
  const loose = rootChildren.filter((c) => !c.children);
  data.push(...folders, ...loose);
  return data;
};

const KnowledgeBase: React.FC = () => {
  const { message } = App.useApp();
  const [bases, setBases] = useState<KB[]>([]);
  const [current, setCurrent] = useState<string>("");
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [docModal, setDocModal] = useState(false);
  const [kbModal, setKbModal] = useState(false);
  const [shareModal, setShareModal] = useState(false);
  const [form] = Form.useForm();
  const [kbForm] = Form.useForm();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaAnswer, setQaAnswer] = useState("");
  const [qaSources, setQaSources] = useState<any[]>([]);
  const [qaing, setQaing] = useState(false);

  // 分享相关
  const [users, setUsers] = useState<LiteUser[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [shares, setShares] = useState<ShareItem[]>([]);
  const [systemShared, setSystemShared] = useState(false);
  const [selUserIds, setSelUserIds] = useState<string[]>([]);
  const [selGroupIds, setSelGroupIds] = useState<string[]>([]);
  const [sharePerm, setSharePerm] = useState<"read" | "write">("read");
  const [savingShare, setSavingShare] = useState(false);

  // 用户组管理
  const [groupModal, setGroupModal] = useState(false);
  const [groupForm] = Form.useForm();
  const [groupMembers, setGroupMembers] = useState<LiteUser[]>([]);
  const [activeGroup, setActiveGroup] = useState<GroupItem | null>(null);

  // 项目（KB 可关联到项目）
  const [projects, setProjects] = useState<ProjectLite[]>([]);
  const [projFilter, setProjFilter] = useState<string | undefined>(undefined);

  // 批量上传
  const [uploadTab, setUploadTab] = useState("text");
  const [uploading, setUploading] = useState(false);
  // 待上传文件池：用户先在 Zone 里挑文件→进 pendingFiles→点底部「上传并处理」才真正上传
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [pendingFolder, setPendingFolder] = useState<string | undefined>(undefined);
  // 文件在线预览
  const [previewDoc, setPreviewDoc] = useState<any>(null);
  const [previewUrl, setPreviewUrl] = useState<string>("");
  const [uploadResults, setUploadResults] = useState<any[]>([]);

  // 富文本文档编辑器（合并自"文档"板块）
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorDoc, setEditorDoc] = useState<DocItem | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [savingDoc, setSavingDoc] = useState(false);

  const loadBases = async () => {
    try {
      const r = await knowledgeApi.listBases("all", projFilter ? { project_id: projFilter } : undefined);
      const list: KB[] = Array.isArray(r) ? r : (r?.items || []);
      setBases(list);
      if (list.length && !current) setCurrent(list[0].id);
      if (!list.length) setCurrent("");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "加载知识库失败");
    }
  };

  const loadProjects = async () => {
    try {
      const r: any = await projectApi.list();
      const list: ProjectLite[] = Array.isArray(r) ? r : (r?.items || []);
      setProjects(list);
    } catch {
      // 静默：项目列表缺失不影响主流程
    }
  };

  const loadDocs = async (kbId: string) => {
    if (!kbId) { setDocs([]); return; }
    setLoading(true);
    try {
      const r = await knowledgeApi.listDocs(kbId);
      setDocs(Array.isArray(r) ? r : (r?.items || []));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "加载文档失败");
    } finally { setLoading(false); }
  };

  useEffect(() => { loadBases(); loadProjects(); }, [projFilter]);
  useEffect(() => { if (current) loadDocs(current); }, [current]);

  // 新建知识库：先客户端校验名称（与 Cherry Studio 一致），避免 validateFields 异常被吞成"创建失败"
  const onAddKb = async () => {
    let v: any;
    try {
      v = await kbForm.validateFields();
    } catch {
      message.warning("请输入知识库名称");
      return;
    }
    try {
      const payload: any = { name: v.name.trim(), description: v.description };
      if (v.project_id) payload.project_id = v.project_id;
      await knowledgeApi.createBase(payload);
      message.success("知识库已创建（默认私有，可随时分享）");
      setKbModal(false); kbForm.resetFields();
      await loadBases();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "创建失败");
    }
  };

  const onAddDocText = async () => {
    const v = await form.validateFields();
    try {
      const created: any = await knowledgeApi.addDoc(current, { title: v.title, content: v.content });
      message.success("文档已添加，正在向量化入库");
      setDocModal(false); form.resetFields(); setUploadTab("text"); setUploadResults([]);
      setPendingFiles([]); setPendingFolder(undefined);
      await loadDocs(current);
      // 创建后直接打开编辑器，延续"文档"板块的即写即存体验
      if (created?.id) {
        setEditorDoc({ ...created, source_type: "text" });
        setEditTitle(created.title || v.title);
        setEditContent(created.content || v.content);
        setEditorOpen(true);
      }
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "添加失败"); }
  };

  // 统一 Modal OK 处理：text 走富文本创建；files/folder 走 pendingFiles 上传
  const handleUploadOk = async () => {
    if (uploadTab === "text") {
      await onAddDocText();
      return;
    }
    if (uploadTab === "files" || uploadTab === "folder") {
      if (!pendingFiles.length) {
        message.warning("请先选择文件");
        return;
      }
      await doUpload(pendingFiles, uploadTab === "folder" ? pendingFolder : undefined);
    }
  };

  // 关闭/取消上传 Modal 时清掉 pending，避免下次打开残留
  const closeUploadModal = () => {
    setDocModal(false);
    setUploadResults([]);
    setPendingFiles([]);
    setPendingFolder(undefined);
  };

  // 切换 tab 时清 pending，避免 files ↔ folder 串味
  const switchUploadTab = (k: string) => {
    setUploadTab(k);
    setPendingFiles([]);
    setPendingFolder(undefined);
  };

  const onDeleteDoc = async (id: string) => {
    try { await knowledgeApi.deleteDoc(id); message.success("已删除"); loadDocs(current); }
    catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "删除失败"); }
  };

  const onDeleteKb = async (id: string) => {
    try { await knowledgeApi.deleteBase(id); message.success("已删除"); setCurrent(""); await loadBases(); }
    catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "删除失败"); }
  };

  const onSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const r = await knowledgeApi.search(current, { query, top_k: 5 });
      setHits(r?.results || []);
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "检索失败"); }
    finally { setSearching(false); }
  };

  const onQA = async () => {
    if (!qaQuestion.trim() || !current) return;
    setQaing(true);
    try {
      const r: any = await knowledgeApi.qa(current, { question: qaQuestion, top_k: 5 });
      setQaAnswer(r?.answer || "");
      setQaSources(r?.sources || []);
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "问答失败"); }
    finally { setQaing(false); }
  };

  // ===== 分享 =====
  const openShare = async () => {
    if (!current) return;
    setSavingShare(false); setSelUserIds([]); setSelGroupIds([]); setSharePerm("read");
    try {
      const [u, g, s] = await Promise.all([
        knowledgeApi.listUsers(),
        knowledgeApi.listGroups(),
        knowledgeApi.listShares(current),
      ]);
      setUsers(Array.isArray(u) ? u : (u?.items || []));
      setGroups(Array.isArray(g) ? g : (g?.items || []));
      const shareList: ShareItem[] = Array.isArray(s) ? s : (s?.items || []);
      setShares(shareList);
      setSystemShared(shareList.some((x) => x.share_type === "system"));
      setShareModal(true);
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "加载分享信息失败"); }
  };

  const saveShare = async () => {
    if (!current) return;
    setSavingShare(true);
    try {
      const hasSystem = shares.some((x) => x.share_type === "system");
      if (systemShared && !hasSystem) {
        await knowledgeApi.addShare(current, { share_type: "system", permission: "read" });
      } else if (!systemShared && hasSystem) {
        const sys = shares.find((x) => x.share_type === "system");
        if (sys) await knowledgeApi.removeShare(current, sys.id);
      }
      for (const uid of selUserIds) {
        await knowledgeApi.addShare(current, { share_type: "user", target_id: uid, permission: sharePerm });
      }
      for (const gid of selGroupIds) {
        await knowledgeApi.addShare(current, { share_type: "group", target_id: gid, permission: sharePerm });
      }
      message.success("分享已更新");
      const s = await knowledgeApi.listShares(current);
      setShares(Array.isArray(s) ? s : (s?.items || []));
      setSystemShared((Array.isArray(s) ? s : (s?.items || [])).some((x: any) => x.share_type === "system"));
      setSelUserIds([]); setSelGroupIds([]);
      await loadBases();
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "保存分享失败"); }
    finally { setSavingShare(false); }
  };

  const removeShare = async (shareId: string) => {
    if (!current) return;
    try {
      await knowledgeApi.removeShare(current, shareId);
      setShares(shares.filter((x) => x.id !== shareId));
      message.success("已取消该分享");
      await loadBases();
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "移除失败"); }
  };

  // ===== 用户组管理 =====
  const openGroupManage = async () => {
    try {
      const g = await knowledgeApi.listGroups();
      setGroups(Array.isArray(g) ? g : (g?.items || []));
      setGroupModal(true);
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "加载用户组失败"); }
  };

  const createGroup = async () => {
    const v = await groupForm.validateFields();
    try {
      await knowledgeApi.createGroup({ name: v.name, description: v.description });
      message.success("用户组已创建");
      groupForm.resetFields();
      const g = await knowledgeApi.listGroups();
      setGroups(Array.isArray(g) ? g : (g?.items || []));
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "创建失败"); }
  };

  const openGroupDetail = async (g: GroupItem) => {
    setActiveGroup(g);
    try {
      const d: any = await knowledgeApi.getGroup(g.id);
      setGroupMembers(d?.members || []);
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "加载成员失败"); }
  };

  const addMemberToGroup = async (userId: string) => {
    if (!activeGroup) return;
    try {
      await knowledgeApi.addGroupMember(activeGroup.id, userId);
      message.success("已添加成员");
      const d: any = await knowledgeApi.getGroup(activeGroup.id);
      setGroupMembers(d?.members || []);
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "添加失败"); }
  };

  const removeMemberFromGroup = async (userId: string) => {
    if (!activeGroup) return;
    try {
      await knowledgeApi.removeGroupMember(activeGroup.id, userId);
      setGroupMembers(groupMembers.filter((m) => m.id !== userId));
      message.success("已移除成员");
    } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || "移除失败"); }
  };

  // ===== 批量上传（文件/文件夹统一走同一 doUpload → RAG 分块入库）=====
  const doUpload = async (fileList: File[], folder?: string) => {
    if (!current || fileList.length === 0) return;
    setUploading(true); setUploadResults([]);
    try {
      const res: any = await knowledgeApi.uploadBatch(current, fileList, folder);
      setUploadResults(Array.isArray(res) ? res : []);
      const ok = (Array.isArray(res) ? res : []).filter((r: any) => r.status !== "failed").length;
      message.success(`已处理 ${ok}/${fileList.length} 个文件，自动向量化入库`);
      loadDocs(current);
    } catch (e: any) { message.error(e?.message || e?.response?.data?.detail || "上传失败"); }
    finally { setUploading(false); }
  };

  // ===== 富文本文档编辑（合并自"文档"板块）=====
  const openEditor = async (d: DocItem) => {
    try {
      // 拉取详情以拿到正文（列表接口可能不含完整 content）
      const full: any = await knowledgeApi.getDoc(current, d.id);
      setEditorDoc(full);
      setEditTitle(full?.title || d.title || "");
      setEditContent(full?.content || "");
      setEditorOpen(true);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "打开文档失败");
    }
  };
  const saveEditor = async () => {
    if (!editorDoc || !current) return;
    setSavingDoc(true);
    try {
      await knowledgeApi.updateDoc(current, editorDoc.id, { title: editTitle, content: editContent });
      message.success("已保存并重新向量化入库");
      setEditorOpen(false);
      await loadDocs(current);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || "保存失败");
    } finally { setSavingDoc(false); }
  };

  const currentKb = bases.find((b) => b.id === current);
  const vis = VISIBILITY_TAG[currentKb?.visibility || "private"] || VISIBILITY_TAG.private;
  const isOwner = currentKb?.access_role === "owner";
  const canWrite = isOwner || currentKb?.my_permission === "write";

  const openPreview = (doc: any) => {
    setPreviewDoc(doc);
    setPreviewUrl("");
  };

  const treeData = buildTreeData(docs, onDeleteDoc, canWrite, openPreview);

  const addContentMenu = (
    <Menu
      items={[
        { key: "text", icon: <FileTextOutlined />, label: "新建文档（富文本）", onClick: () => { switchUploadTab("text"); setDocModal(true); } },
        { key: "files", icon: <UploadOutlined />, label: "上传文件", onClick: () => { switchUploadTab("files"); setDocModal(true); } },
        { key: "folder", icon: <FolderOpenOutlined />, label: "上传文件夹", onClick: () => { switchUploadTab("folder"); setDocModal(true); } },
      ]}
    />
  );

  return (
    <div>
      <div style={{ display: "flex", gap: 16, alignItems: "stretch" }}>
        {/* 左侧：知识库导航器（层级 1，参考 Cherry Studio） */}
        <div style={{ width: 248, flexShrink: 0 }}>
          <Card
            styles={{ body: { padding: 12 } }}
            style={{ borderRadius: 16, height: "100%" }}
            title={<span><DatabaseOutlined /> 知识库</span>}
            extra={
              <Button data-tour="kb-new" size="small" type="primary" icon={<PlusOutlined />} onClick={() => setKbModal(true)}>
                新建
              </Button>
            }
          >
            <div style={{ marginBottom: 8 }}>
              <Select
                size="small"
                allowClear
                placeholder="按项目筛选"
                style={{ width: "100%" }}
                value={projFilter}
                onChange={setProjFilter}
                options={[
                  { value: "__NONE__", label: "未关联项目" },
                  ...projects.map((p) => ({ value: p.id, label: p.name })),
                ]}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: "60vh", overflow: "auto" }}>
              {bases.length === 0 && <Text type="secondary" style={{ fontSize: 12 }}>尚未创建知识库</Text>}
              {bases.map((b) => {
                const v = VISIBILITY_TAG[b.visibility] || VISIBILITY_TAG.private;
                const active = b.id === current;
                return (
                  <div
                    key={b.id}
                    onClick={() => setCurrent(b.id)}
                    style={{
                      padding: "8px 10px", borderRadius: 8, cursor: "pointer",
                      background: active ? "#EEF2FF" : "transparent",
                      borderLeft: active ? "3px solid #4F46E5" : "3px solid transparent",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: active ? 600 : 400, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.name}</span>
                      <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>{b.document_count}</Text>
                    </div>
                    <div style={{ marginTop: 2, display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                      {b.project_name ? (
                        <Tag color="geekblue" style={{ fontSize: 10, margin: 0 }}>
                          <ProjectOutlined style={{ marginRight: 2 }} />
                          {b.project_name}
                        </Tag>
                      ) : (
                        <Tag style={{ fontSize: 10, margin: 0, color: "#999" }}>未关联项目</Tag>
                      )}
                      {b.access_role !== "owner" && (
                        <Tag color={v.color} style={{ fontSize: 10, margin: 0 }}>{v.label}</Tag>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>

        {/* 右侧：主内容 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!current ? (
            <Card>
              <Empty description={bases.length ? "请选择左侧知识库" : "尚未创建知识库，点击左上角新建"}>
                <Button type="primary" icon={<DatabaseOutlined />} onClick={() => setKbModal(true)}>创建知识库</Button>
              </Empty>
            </Card>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 12 }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>{currentKb?.name}</Title>
                  <div style={{ marginTop: 4 }}>
                    <Tag color={vis.color}>{vis.label}</Tag>
                    {currentKb?.project_name ? (
                      <Tag color="geekblue" icon={<ProjectOutlined />}>
                        服务于项目：{currentKb.project_name}
                      </Tag>
                    ) : (
                      <Tag style={{ color: "#999" }}>未关联项目</Tag>
                    )}
                    {currentKb?.access_role === "owner"
                      ? <Text type="secondary">· 你创建的知识库 · 可分享给指定用户/用户组或全系统</Text>
                      : <Text type="secondary">· 该知识库由他人分享给你（{vis.label}）</Text>}
                  </div>
                </div>
                <Space wrap>
                  <Button icon={<ShareAltOutlined />} disabled={!current || !isOwner} onClick={openShare}>管理分享</Button>
                  <Dropdown overlay={addContentMenu} disabled={!current || !canWrite}>
                    <Button data-tour="kb-upload" type="primary" icon={<PlusOutlined />} disabled={!current || !canWrite}>添加内容</Button>
                  </Dropdown>
                  <Popconfirm
                    title="确认删除该知识库？"
                    description="将同时删除其下全部文档与分块，且不可恢复。"
                    disabled={!current || !isOwner}
                    onConfirm={() => onDeleteKb(current)}
                    okText="删除" cancelText="取消" okButtonProps={{ danger: true }}
                  >
                    <Button danger icon={<DeleteOutlined />} disabled={!current || !isOwner}>删除知识库</Button>
                  </Popconfirm>
                </Space>
              </div>

              <Row gutter={16}>
                <Col xs={24} lg={14}>
                  <Card
                    title="文档与文件（按知识库层级展示）"
                    extra={<Text type="secondary">{docs.length} 篇</Text>}
                  >
                    <Spin spinning={loading}>
                      {docs.length === 0 ? (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无内容，点击右上角「添加内容」上传文件或新建文档" />
                      ) : (
                        <Tree
                          showLine
                          blockNode
                          defaultExpandAll
                          treeData={treeData as any}
                          onSelect={(_keys, info: any) => {
                            const node = info.node;
                            if (node?.doc) {
                              // 文本文档点击进入编辑器；文件文档点击聚焦（删除走 hover 操作）
                              if (node.doc.source_type === "text") openEditor(node.doc);
                              else if (node.doc.source_type === "file") openPreview(node.doc);
                            }
                          }}
                          style={{ maxHeight: "60vh", overflow: "auto" }}
                        />
                      )}
                    </Spin>
                  </Card>
                </Col>
                <Col xs={24} lg={10}>
                  <Card title="智能检索 / 知识问答">
                    <Tabs
                      items={[
                        {
                          key: "search", label: "检索",
                          children: (
                            <>
                              <Space.Compact style={{ width: "100%" }}>
                                <Input
                                  placeholder="输入问题，从知识库检索相关内容"
                                  value={query}
                                  onChange={(e) => setQuery(e.target.value)}
                                  onPressEnter={onSearch}
                                  prefix={<SearchOutlined />}
                                />
                                <Button type="primary" loading={searching} onClick={onSearch}>检索</Button>
                              </Space.Compact>
                              <Divider style={{ margin: "12px 0" }} />
                              {hits.length === 0 ? (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无检索结果" />
                              ) : (
                                <List
                                  dataSource={hits}
                                  renderItem={(h) => (
                                    <List.Item key={h.chunk_id} style={{ display: "block" }}>
                                      <Space style={{ marginBottom: 4 }}>
                                        <FileTextOutlined />
                                        <Text strong>{h.document_title}</Text>
                                        <Tag color="blue">相关度 {h.score.toFixed(2)}</Tag>
                                      </Space>
                                      <Paragraph style={{ margin: 0, fontSize: 13, color: "#475569", whiteSpace: "pre-wrap" }}>
                                        {h.content}
                                      </Paragraph>
                                    </List.Item>
                                  )}
                                />
                              )}
                            </>
                          ),
                        },
                        {
                          key: "qa", label: "RAG 问答",
                          children: (
                            <>
                              <Space.Compact style={{ width: "100%" }}>
                                <Input
                                  placeholder="用自然语言提问，基于知识库生成答案"
                                  value={qaQuestion}
                                  onChange={(e) => setQaQuestion(e.target.value)}
                                  onPressEnter={onQA}
                                  prefix={<SearchOutlined />}
                                />
                                <Button type="primary" loading={qaing} onClick={onQA} disabled={!current}>问答</Button>
                              </Space.Compact>
                              <Divider style={{ margin: "12px 0" }} />
                              {!qaAnswer ? (
                                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="输入问题获取基于知识库的答案" />
                              ) : (
                                <>
                                  <Paragraph style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{qaAnswer}</Paragraph>
                                  {qaSources.length > 0 && (
                                    <>
                                      <Divider style={{ margin: "8px 0" }} />
                                      <Text type="secondary" style={{ fontSize: 12 }}>参考来源：</Text>
                                      <div style={{ marginTop: 4 }}>
                                        {qaSources.map((s, i) => <Tag key={i} color="cyan">{s.title}（{s.score}）</Tag>)}
                                      </div>
                                    </>
                                  )}
                                </>
                              )}
                            </>
                          ),
                        },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
            </>
          )}
        </div>
      </div>

      {/* 新建知识库 */}
      <Modal title="新建知识库" open={kbModal} onOk={onAddKb} onCancel={() => setKbModal(false)} okText="创建" cancelText="取消">
        <Form form={kbForm} layout="vertical">
          <Form.Item name="name" label="知识库名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input placeholder="例如：产品需求知识库" />
          </Form.Item>
          <Form.Item name="project_id" label="关联项目（可选）" tooltip="关联后，项目的 Agent 可优先检索此知识库；项目详情页也会显示该知识库">
            <Select
              allowClear
              placeholder={projects.length ? "选择项目..." : "暂无可关联项目"}
              disabled={!projects.length}
              options={projects.map((p) => ({ value: p.id, label: p.code ? `${p.name}（${p.code}）` : p.name }))}
              showSearch optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={3} placeholder="可选" />
          </Form.Item>
          <Text type="secondary">默认仅你自己可见，创建后可在「管理分享」中分享给指定用户/用户组或全系统。</Text>
        </Form>
      </Modal>

      {/* 添加内容：文本 / 文件 / 文件夹（统一模式，均走 RAG 分块入库） */}
      <Modal
        title="添加内容"
        open={docModal}
        onOk={handleUploadOk}
        okText={uploadTab === "text" ? "添加并编辑" : `上传并处理（已选 ${pendingFiles.length} 个）`}
        onCancel={closeUploadModal}
        confirmLoading={uploading}
        okButtonProps={{
          loading: uploading,
          disabled: uploading || ((uploadTab === "files" || uploadTab === "folder") && pendingFiles.length === 0),
        }}
        cancelText="取消"
      >
        <Tabs activeKey={uploadTab} onChange={switchUploadTab} items={[
          {
            key: "text", label: "新建文档",
            children: (
              <Form form={form} layout="vertical">
                <Form.Item name="title" label="文档标题" rules={[{ required: true, message: "请输入标题" }]}>
                  <Input placeholder="例如：用户登录流程说明" />
                </Form.Item>
                <Form.Item name="content" label="内容" rules={[{ required: true, message: "请输入内容" }]}>
                  <TextArea rows={6} placeholder="粘贴或输入文档正文，将自动分段向量化" />
                </Form.Item>
              </Form>
            ),
          },
          {
            key: "files", label: "上传文件",
            children: (
              <UploadFilesZone
                files={pendingFiles}
                onChange={setPendingFiles}
                uploading={uploading}
                acceptHint="支持 txt/md/csv/json/html/代码/PDF/DOCX/XLSX/PPTX 等"
              />
            ),
          },
          {
            key: "folder", label: "上传文件夹",
            children: (
              <UploadFolderZone
                files={pendingFiles}
                onChange={setPendingFiles}
                folder={pendingFolder}
                onFolderChange={setPendingFolder}
                uploading={uploading}
              />
            ),
          },
        ]} />
        {uploadResults.length > 0 && (
          <>
            <Divider style={{ margin: "8px 0" }} />
            <List
              size="small"
              dataSource={uploadResults}
              renderItem={(r: any) => (
                <List.Item>
                  <Space>
                    {r.status === "failed"
                      ? <Tag color="red">失败</Tag>
                      : <Tag color={r.status === "completed" ? "green" : "orange"}>{r.status}</Tag>}
                    <Text>{r.file_name}</Text>
                    {r.chunk_count ? <Text type="secondary">· {r.chunk_count} 分块</Text> : null}
                    {r.error ? <Text type="danger" style={{ fontSize: 12 }}>{r.error}</Text> : null}
                  </Space>
                </List.Item>
              )}
            />
          </>
        )}
      </Modal>

      {/* 富文本文档编辑器（合并自"文档"板块） */}
      <Drawer
        title="编辑文档"
        width={720}
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setEditorOpen(false)}>取消</Button>
            <Button type="primary" loading={savingDoc} icon={<EditOutlined />} onClick={saveEditor}>保存并重新向量化</Button>
          </Space>
        }
      >
        <Input
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          placeholder="文档标题"
          style={{ fontSize: 18, fontWeight: 700, marginBottom: 12 }}
        />
        <TextArea
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          placeholder="在此输入 Markdown 正文..."
          style={{ minHeight: "calc(100vh - 220px)", border: "1px solid #E2E8F0", borderRadius: 12, padding: 16, fontSize: 14, lineHeight: 1.7, fontFamily: "'Inter', monospace", resize: "vertical" }}
        />
        <Divider style={{ margin: "12px 0" }} />
        <Text type="secondary" style={{ fontSize: 12 }}>预览</Text>
        <div
          style={{ whiteSpace: "pre-wrap", lineHeight: 1.7, fontSize: 14, color: "#334155", minHeight: 120 }}
          dangerouslySetInnerHTML={{ __html: renderMarkdownToHtml(editContent) }}
        />
      </Drawer>

      {/* 管理分享 */}
            <Modal
        title={`预览 · ${previewDoc?.file_name || previewDoc?.title || ""}`}
        open={!!previewDoc}
        footer={null}
        width={960}
        onCancel={() => {
          setPreviewDoc(null);
          setPreviewUrl("");
        }}
        destroyOnClose
      >
        {previewDoc && current && (
          <FilePreview
            apiBase={(http.defaults.baseURL || "/api/v1").replace(/\/$/, "")}
            kbId={current}
            docId={previewDoc.id}
            fileName={previewDoc.file_name || previewDoc.title}
            bearerToken={localStorage.getItem("aipm_token") || undefined}
            height={560}
          />
        )}
      </Modal>

<Modal title="管理知识库分享" open={shareModal} onOk={saveShare} okText="保存分享" onCancel={() => setShareModal(false)} confirmLoading={savingShare} cancelText="取消" width={640}>
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Checkbox checked={systemShared} onChange={(e) => setSystemShared(e.target.checked)}>
              分享给<Text strong> 全系统 </Text>（提供给整个系统使用，所有用户均可检索/问答）
            </Checkbox>
          </div>
          <Divider style={{ margin: 0 }} />
          <div>
            <Text strong>分享给指定用户</Text>
            <Select
              mode="multiple" style={{ width: "100%", marginTop: 8 }} placeholder="选择用户"
              value={selUserIds} onChange={setSelUserIds}
              options={users.map((u) => ({ value: u.id, label: `${u.full_name || u.username}（${u.username}）` }))}
            />
          </div>
          <div>
            <Text strong>分享给指定用户组</Text>
            <Select
              mode="multiple" style={{ width: "100%", marginTop: 8 }} placeholder="选择用户组"
              value={selGroupIds} onChange={setSelGroupIds}
              options={groups.map((g) => ({ value: g.id, label: `${g.name}（${g.member_count}人）` }))}
            />
            <Button type="link" icon={<TeamOutlined />} style={{ paddingLeft: 0, marginTop: 4 }} onClick={openGroupManage}>
              管理用户组
            </Button>
          </div>
          <div>
            <Text strong>权限</Text>
            <Select value={sharePerm} style={{ width: 160, marginLeft: 8 }} onChange={(v) => setSharePerm(v)} options={[
              { value: "read", label: "只读（检索/问答）" },
              { value: "write", label: "可写（可上传/删除文档）" },
            ]} />
          </div>
          <Divider style={{ margin: 0 }} />
          <div>
            <Text strong>当前分享对象</Text>
            {shares.length === 0 ? (
              <div style={{ marginTop: 8 }}><Text type="secondary">尚未分享</Text></div>
            ) : (
              <List
                size="small" style={{ marginTop: 8 }}
                dataSource={shares}
                renderItem={(s) => (
                  <List.Item
                    actions={[<a key="rm" onClick={() => removeShare(s.id)}>取消</a>]}
                  >
                    <Space>
                      <Tag color={s.share_type === "system" ? "purple" : s.share_type === "group" ? "geekblue" : "blue"}>
                        {s.share_type === "system" ? "全系统" : s.share_type === "group" ? "用户组" : "用户"}
                      </Tag>
                      <Text>{s.share_type === "system" ? "所有用户" : (s.target_name || s.target_id)}</Text>
                      <Tag>{s.permission === "write" ? "可写" : "只读"}</Tag>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </div>
        </Space>
      </Modal>

      {/* 用户组管理 */}
      <Modal title="用户组管理" open={groupModal} onCancel={() => setGroupModal(false)} footer={null} width={620}>
        <Form form={groupForm} layout="vertical">
          <Space.Compact style={{ width: "100%" }}>
            <Form.Item name="name" label="新建用户组" rules={[{ required: true, message: "请输入组名" }]} style={{ flex: 1, marginBottom: 8 }}>
              <Input placeholder="例如：研发团队" />
            </Form.Item>
            <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 8, marginLeft: 8 }} onClick={createGroup}>创建</Button>
          </Space.Compact>
        </Form>
        <Divider style={{ margin: "8px 0" }} />
        <Row gutter={16}>
          <Col span={10}>
            <Text type="secondary">我的用户组</Text>
            <List
              size="small" style={{ marginTop: 4 }}
              dataSource={groups}
              renderItem={(g) => (
                <List.Item
                  style={{ cursor: "pointer" }}
                  className={activeGroup?.id === g.id ? "kb-active-group" : ""}
                  onClick={() => openGroupDetail(g)}
                >
                  <Space>
                    <TeamOutlined />
                    <span>{g.name}</span>
                    <Tag>{g.member_count}</Tag>
                  </Space>
                </List.Item>
              )}
            />
          </Col>
          <Col span={14}>
            {activeGroup ? (
              <>
                <Text strong>{activeGroup.name} · 成员</Text>
                {activeGroup?.is_owner ? (
                  <Select
                    style={{ width: "100%", marginTop: 8 }} placeholder="添加成员（搜索用户）"
                    showSearch optionFilterProp="label"
                    options={users
                      .filter((u) => !groupMembers.some((m) => m.id === u.id))
                      .map((u) => ({ value: u.id, label: `${u.full_name || u.username}（${u.username}）` }))}
                    onSelect={(uid) => addMemberToGroup(uid)}
                  />
                ) : (
                  <Text type="secondary" style={{ display: "inline-block", marginTop: 8 }}>
                    仅用户组创建者可添加成员
                  </Text>
                )}
                <List
                  size="small" style={{ marginTop: 8 }}
                  dataSource={groupMembers}
                  renderItem={(m) => (
                    <List.Item actions={[<a key="rm" onClick={() => removeMemberFromGroup(m.id)}>移除</a>]}>
                      <Space>
                        <Text>{m.full_name || m.username}</Text>
                        <Text type="secondary">（{m.username}）</Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </>
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择左侧用户组查看成员" />}
          </Col>
        </Row>
      </Modal>
    </div>
  );
};

// 文件选择区（受控）：用户先挑文件进 files，再点底部「上传并处理」才真正上传
const UploadFilesZone: React.FC<{
  files: File[];
  onChange: (files: File[]) => void;
  uploading: boolean;
  acceptHint: string;
}> = ({ files, onChange, uploading, acceptHint }) => {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = Array.from(e.target.files || []);
    if (f.length) onChange([...files, ...f]);
    e.target.value = "";
  };
  const removeAt = (i: number) => onChange(files.filter((_, idx) => idx !== i));
  const clearAll = () => onChange([]);
  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Button
          icon={<UploadOutlined />}
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
        >
          选择文件
        </Button>
        {files.length > 0 && (
          <Button type="text" danger onClick={clearAll} disabled={uploading}>
            清空
          </Button>
        )}
        <input
          ref={inputRef}
          type="file"
          multiple
          disabled={uploading}
          onChange={onPick}
          style={{ display: "none" }}
        />
      </Space>
      <div><Text type="secondary">{acceptHint}</Text></div>
      <div style={{ marginTop: 4 }}><Text type="secondary">可一次选择多个文件，挑选完成后点击底部「上传并处理」开始向量化入库。</Text></div>
      {files.length > 0 && (
        <div style={{ marginTop: 12, padding: 8, background: "#fafafa", borderRadius: 4, maxHeight: 240, overflowY: "auto" }}>
          <Text type="secondary" style={{ fontSize: 12 }}>已选 {files.length} 个文件：</Text>
          <List
            size="small"
            style={{ marginTop: 4 }}
            dataSource={files}
            renderItem={(f, i) => (
              <List.Item
                actions={[
                  <Button
                    key="del"
                    type="text"
                    size="small"
                    danger
                    icon={<CloseOutlined />}
                    onClick={() => removeAt(i)}
                    disabled={uploading}
                  />,
                ]}
              >
                <List.Item.Meta
                  avatar={<FileOutlined />}
                  title={<span style={{ fontSize: 13 }}>{f.name}</span>}
                  description={<span style={{ fontSize: 12 }}>{(f.size / 1024).toFixed(1)} KB</span>}
                />
              </List.Item>
            )}
          />
        </div>
      )}
    </div>
  );
};

// 文件夹选择区（受控）：保留子目录层级，用户挑完后点底部「上传并处理」才真正上传
const UploadFolderZone: React.FC<{
  files: File[];
  onChange: (files: File[]) => void;
  folder?: string;
  onFolderChange: (folder: string | undefined) => void;
  uploading: boolean;
}> = ({ files, onChange, folder, onFolderChange, uploading }) => {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = Array.from(e.target.files || []);
    if (f.length) {
      // 取首个文件的完整相对目录（去掉文件名），保留子目录层级
      const rel = (f[0] as any).webkitRelativePath || "";
      const dir = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
      onChange(f);
      onFolderChange(dir || undefined);
    }
    e.target.value = "";
  };
  const removeAt = (i: number) => onChange(files.filter((_, idx) => idx !== i));
  const clearAll = () => { onChange([]); onFolderChange(undefined); };
  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Button
          icon={<FolderOpenOutlined />}
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
        >
          选择文件夹
        </Button>
        {files.length > 0 && (
          <Button type="text" danger onClick={clearAll} disabled={uploading}>
            清空
          </Button>
        )}
        <input
          ref={inputRef}
          type="file"
          // @ts-ignore webkitdirectory 非标准属性
          webkitdirectory=""
          directory=""
          multiple
          disabled={uploading}
          onChange={onPick}
          style={{ display: "none" }}
        />
      </Space>
      <div><Text type="secondary">选择一个文件夹，系统将递归上传其中所有文件并自动 RAG 解析，保留目录层级。</Text></div>
      {folder && (
        <div style={{ marginTop: 4 }}>
          <Text type="secondary">当前目录：</Text>
          <Tag color="blue" style={{ marginLeft: 4 }}>{folder}</Tag>
        </div>
      )}
      {files.length > 0 && (
        <div style={{ marginTop: 12, padding: 8, background: "#fafafa", borderRadius: 4, maxHeight: 240, overflowY: "auto" }}>
          <Text type="secondary" style={{ fontSize: 12 }}>已选 {files.length} 个文件：</Text>
          <List
            size="small"
            style={{ marginTop: 4 }}
            dataSource={files}
            renderItem={(f, i) => (
              <List.Item
                actions={[
                  <Button
                    key="del"
                    type="text"
                    size="small"
                    danger
                    icon={<CloseOutlined />}
                    onClick={() => removeAt(i)}
                    disabled={uploading}
                  />,
                ]}
              >
                <List.Item.Meta
                  avatar={<FileOutlined />}
                  title={<span style={{ fontSize: 13 }}>{(f as any).webkitRelativePath || f.name}</span>}
                  description={<span style={{ fontSize: 12 }}>{(f.size / 1024).toFixed(1)} KB</span>}
                />
              </List.Item>
            )}
          />
        </div>
      )}
    </div>
  );
};

export default KnowledgeBase;
