/**
 * BrandSettings - 品牌 Logo 设置（管理员）
 *
 * 在"系统设置 > 品牌设置"中上传品牌 Logo。
 * 一次上传，全局生效：
 *   ✅ 浏览器标签页 Favicon
 *   ✅ 侧边栏 Logo
 *   ✅ 登录页 Logo
 *
 * 文件要求：
 *   格式：PNG / SVG / WebP / JPG
 *   大小：≤ 512 KB
 *   推荐尺寸：正方形 ≥ 128×128 px（自适应缩放）
 */

import React, { useState } from "react";
import {
  Card, Upload, Button, Alert, Space, Typography, Tag, Popconfirm,
  Image as AntImage, message as antdMessage, Spin, App,
} from "antd";
import {
  PictureOutlined, DeleteOutlined, UploadOutlined,
  ReloadOutlined, CheckCircleOutlined,
} from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { useBrandLogo } from "../hooks/useBrandLogo";
import { del as httpDel, http } from "../api/http";

const { Text, Title, Paragraph } = Typography;

const FILE_REQUIREMENTS = [
  "支持格式：PNG、SVG、WebP、JPG",
  "文件大小：≤ 512 KB",
  "推荐尺寸：正方形，≥ 128 × 128 像素",
  "说明：上传后将自动替换系统所有位置 Logo（侧边栏 / 登录页 / Favicon），无需重启服务",
];

const BrandSettings: React.FC = () => {
  const { logoUrl, hasLogo, isLoading: logoLoading, refresh } = useBrandLogo();
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // ── 上传处理 ──
  const handleUpload = async (file: File) => {
    // 前端校验
    if (file.size > 512 * 1024) {
      antdMessage.error(`文件过大：${(file.size / 1024).toFixed(0)} KB，上限 512 KB`);
      return false;
    }

    const allowed = ["image/png", "image/svg+xml", "image/webp", "image/jpeg"];
    if (!allowed.includes(file.type)) {
      antdMessage.error(`不支持格式：${file.type}，请使用 PNG/SVG/WebP/JPG`);
      return false;
    }

    // 预览
    setPreviewUrl(URL.createObjectURL(file));

    const formData = new FormData();
    formData.append("file", file);

    setUploading(true);
    try {
      // 关键修复：不要手动设置 Content-Type。
      // 让 axios/浏览器自动添加 multipart/form-data; boundary=...，
      // 否则覆盖掉 boundary 会导致后端无法解析 multipart 体（422/400）。
      const r = await http.post("/system/brand-logo/upload", formData);
      const body: any = r.data || {};
      message.success(body?.message || "品牌 Logo 已上传");
      setFileList([]);
      refresh();
      // 动态更新 favicon（body.data 为 BrandInfo，含 logo_url）
      if (body?.data?.logo_url) {
        updateFavicon(body.data.logo_url);
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "上传失败");
    } finally {
      setUploading(false);
    }
    return false; // 阻止默认上传行为
  };

  // ── 删除处理 ──
  const handleDelete = async () => {
    try {
      const res = await httpDel("/system/brand-logo");
      message.success(res.message || "已删除");
      refresh();
      // 恢复默认 favicon
      resetFavicon();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "删除失败");
    }
  };

  return (
    <Card
      title={<Space><PictureOutlined /><span>品牌设置（Logo / Favicon）</span></Space>}
      style={{ marginBottom: 16 }}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="品牌 Logo 统一管理"
        description={
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {FILE_REQUIREMENTS.map((req, i) => (
              <li key={i}>{req}</li>
            ))}
          </ul>
        }
      />

      {/* 当前状态 */}
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 24 }}>
        <Spin spinning={logoLoading}>
          <div style={{
            width: 80, height: 80, borderRadius: 12,
            border: "2px dashed #d9d9d9", display: "flex",
            alignItems: "center", justifyContent: "center",
            overflow: "hidden", background: "#fafafa",
          }}>
            {(hasLogo && logoUrl) ? (
              <AntImage src={logoUrl} alt="当前 Logo"
                preview={false}
                style={{ width: "100%", height: "100%", objectFit: "contain" }}
                fallback="/icon.svg"
              />
            ) : (
              <Text type="secondary" style={{ fontSize: 11, textAlign: "center", padding: 8 }}>默认图标</Text>
            )}
          </div>
        </Spin>

        <div>
          <Space size="small">
            <Tag color={hasLogo ? "green" : "default"}>
              {hasLogo ? "已设置" : "未设置"}
            </Tag>
          </Space>
          <div>
            <Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 13 }}>
              {hasLogo
                ? "当前 Logo 已在侧边栏、登录页和浏览器标签页中显示"
                : "尚未设置自定义 Logo，系统使用默认图标。上传后将自动应用到全部位置。"}
            </Paragraph>
          </div>
        </div>
      </div>

      {/* 预览区 */}
      {previewUrl && (
        <Alert
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          closable
          onClose={() => setPreviewUrl(null)}
          style={{ marginBottom: 16 }}
          message="新 Logo 预览"
          description={
            <AntImage src={previewUrl} alt="预览"
              width={48} height={48} style={{ borderRadius: 8 }}
            />
          }
        />
      )}

      {/* 操作区 */}
      <Space wrap>
        <Upload
          fileList={fileList}
          beforeUpload={handleUpload}
          accept=".png,.svg,.webp,.jpg,.jpeg"
          maxCount={1}
          showUploadList={false}
          disabled={uploading}
        >
          <Button icon={<UploadOutlined />} loading={uploading} type="primary">
            {hasLogo ? "更换 Logo" : "上传 Logo"}
          </Button>
        </Upload>

        {hasLogo && (
          <Popconfirm title="确认删除品牌 Logo？" description="删除后系统恢复为默认图标"
            onConfirm={handleDelete} okText="删除" cancelText="取消"
          >
            <Button icon={<DeleteOutlined />} danger>删除 Logo</Button>
          </Popconfirm>
        )}
        <Button icon={<ReloadOutlined />} onClick={refresh} size="small">刷新</Button>
      </Space>
    </Card>
  );
};

// ── 动态更新 Favicon ──

function updateFavicon(url: string) {
  try {
    let link: HTMLLinkElement | null =
      document.querySelector("link[rel*='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.type = "image/x-icon";
    link.href = url + "?t=" + Date.now(); // 破缓存
  } catch { /* 静默失败 */ }
}

function resetFavicon() {
  try {
    const link: HTMLLinkElement | null =
      document.querySelector("link[rel*='icon']");
    if (link) {
      link.href = "/icon.svg?t=" + Date.now();
    }
  } catch { /* 静默失败 */ }
}

export default BrandSettings;
