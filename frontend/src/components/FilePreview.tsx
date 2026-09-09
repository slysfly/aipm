import React, { useEffect, useState } from "react";
import { Alert, Button, Empty, Skeleton, Space, Spin, Tabs, Tag, message } from "antd";
import {
  DownloadOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  FileWordOutlined,
  FileUnknownOutlined,
} from "@ant-design/icons";
import axios from "axios";
import DOMPurify from "dompurify";

/**
 * 通用文件预览组件 — 通过后端 /preview.json 端点获取结构化数据，
 * 不依赖浏览器原生 PDF 渲染或前端大型库，确保所有格式都能预览。
 *
 *  type=pdf    → 标签页切换显示每页文本
 *  type=docx   → HTML 渲染（DOMPurify 净化）
 *  type=xlsx   → HTML 表格渲染 + sheet 列表
 *  type=image  → <img> 标签
 *  type=text   → <pre> 文本
 *  type=other  → 降级为"下载 / 在新窗口打开"
 */

export interface FilePreviewProps {
  apiBase: string; // 如 /api/v1
  kbId: string;
  docId: string;
  fileName?: string;
  bearerToken?: string;
  height?: number;
}

type PreviewData =
  | { type: "pdf"; file_name: string; file_url: string; pages: { page: number; text: string }[]; total_pages: number; truncated: boolean }
  | { type: "docx"; file_name: string; html: string }
  | { type: "xlsx"; file_name: string; sheets: string[]; html: string }
  | { type: "image"; file_name: string; file_url: string; mime: string }
  | { type: "text"; file_name: string; text: string; mime: string; warning?: string }
  | { type: "other"; file_name: string; file_url: string; mime: string; ext: string; error?: string }
  | { type: "text-no-file"; text: string; file_name: string; warning: string };

const TYPE_ICON: Record<string, React.ReactNode> = {
  pdf: <FilePdfOutlined style={{ color: "#d4380d" }} />,
  docx: <FileWordOutlined style={{ color: "#1d39c4" }} />,
  xlsx: <FileExcelOutlined style={{ color: "#237804" }} />,
  image: <FileImageOutlined style={{ color: "#08979c" }} />,
  text: <FileTextOutlined />,
  other: <FileUnknownOutlined />,
};

const FilePreview: React.FC<FilePreviewProps> = ({
  apiBase,
  kbId,
  docId,
  fileName,
  bearerToken,
  height = 480,
}) => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<PreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    const url = `${apiBase}/knowledge-bases/${kbId}/documents/${docId}/preview.json`;
    const headers: Record<string, string> = {};
    if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`;

    axios
      .get(url, { headers })
      .then((res) => {
        if (cancelled) return;
        setData(res.data);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err?.response?.data?.detail || err?.message || "预览加载失败";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [apiBase, kbId, docId, bearerToken]);

  if (loading) {
    return (
      <div style={{ padding: 16 }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="预览加载失败"
        description={error}
        showIcon
        action={
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => {
              const a = document.createElement("a");
              a.href = `${apiBase}/knowledge-bases/${kbId}/documents/${docId}/download`;
              if (bearerToken) a.href += `?token=${encodeURIComponent(bearerToken)}`;
              a.click();
            }}
          >
            下载文件
          </Button>
        }
      />
    );
  }

  if (!data) return <Empty description="无可预览内容" />;

  const downloadUrl = `${apiBase}/knowledge-bases/${kbId}/documents/${docId}/download`;

  // 通用顶部条
  const Header = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 12px",
        borderBottom: "1px solid #f0f0f0",
        background: "#fafafa",
        borderRadius: 4,
        marginBottom: 8,
      }}
    >
      {TYPE_ICON[data.type] || <FileUnknownOutlined />}
      <span style={{ fontWeight: 500 }}>{fileName || data.file_name || "preview"}</span>
      <Tag color="blue" style={{ marginLeft: 6 }}>
        {data.type.toUpperCase()}
      </Tag>
      <div style={{ flex: 1 }} />
      <Button
        size="small"
        type="link"
        icon={<DownloadOutlined />}
        onClick={() => {
          const a = document.createElement("a");
          a.href = downloadUrl;
          a.click();
        }}
      >
        下载
      </Button>
    </div>
  );

  if (data.type === "pdf") {
    return (
      <div>
        {Header}
        {data.truncated && (
          <Alert
            type="info"
            showIcon
            message={`仅提取前 ${data.pages.length} 页文本（共 ${data.total_pages} 页）`}
            style={{ marginBottom: 8 }}
          />
        )}
        <Tabs
          style={{ height: height - 60 }}
          items={data.pages.map((p) => ({
            key: String(p.page),
            label: `第 ${p.page} 页`,
            children: (
              <div
                style={{
                  height: height - 100,
                  overflow: "auto",
                  padding: "12px 16px",
                  background: "#fff",
                  border: "1px solid #f0f0f0",
                  borderRadius: 4,
                  whiteSpace: "pre-wrap",
                  fontSize: 13,
                  lineHeight: 1.7,
                }}
              >
                {p.text || <span style={{ color: "#999" }}>（本页无提取文本，可能为图片型 PDF）</span>}
              </div>
            ),
          }))}
        />
      </div>
    );
  }

  if (data.type === "docx") {
    return (
      <div>
        {Header}
        <div
          style={{
            height: height - 60,
            overflow: "auto",
            padding: "16px 20px",
            background: "#fff",
            border: "1px solid #f0f0f0",
            borderRadius: 4,
            lineHeight: 1.7,
            fontSize: 14,
          }}
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(data.html) }}
        />
      </div>
    );
  }

  if (data.type === "xlsx") {
    return (
      <div>
        {Header}
        {data.sheets.length > 1 && (
          <Space style={{ marginBottom: 8 }}>
            <span style={{ color: "#666" }}>工作表：</span>
            {data.sheets.map((s) => (
              <Tag key={s}>{s}</Tag>
            ))}
          </Space>
        )}
        <div
          style={{
            height: height - 80,
            overflow: "auto",
            padding: "8px 12px",
            background: "#fff",
            border: "1px solid #f0f0f0",
            borderRadius: 4,
          }}
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(data.html) }}
        />
      </div>
    );
  }

  if (data.type === "image") {
    return (
      <div>
        {Header}
        <div
          style={{
            height: height - 60,
            overflow: "auto",
            textAlign: "center",
            background: "#fafafa",
            border: "1px solid #f0f0f0",
            borderRadius: 4,
            padding: 16,
          }}
        >
          <img
            src={data.file_url}
            alt={data.file_name}
            style={{ maxWidth: "100%", maxHeight: height - 100 }}
            onError={() => message.error("图片加载失败")}
          />
        </div>
      </div>
    );
  }

  if (data.type === "text" || data.type === "text-no-file") {
    return (
      <div>
        {Header}
        {"warning" in data && data.warning && (
          <Alert type="warning" showIcon message={data.warning} style={{ marginBottom: 8 }} />
        )}
        <pre
          style={{
            height: height - 80,
            overflow: "auto",
            padding: "12px 16px",
            background: "#1e1e1e",
            color: "#d4d4d4",
            borderRadius: 4,
            fontSize: 13,
            lineHeight: 1.6,
            fontFamily:
              'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
            margin: 0,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {data.text || "（无内容）"}
        </pre>
      </div>
    );
  }

  // other: 降级为下载
  return (
    <div>
      {Header}
      <Empty
        description={
          <div>
            <div style={{ marginBottom: 8 }}>
              该格式（.{data.ext || "未知"}）暂不支持在线预览
            </div>
            <Space>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={() => {
                  const a = document.createElement("a");
                  a.href = data.file_url;
                  a.click();
                }}
              >
                下载文件
              </Button>
              <Button
                onClick={() => {
                  const win = window.open(data.file_url, "_blank");
                  if (!win) message.warning("浏览器拦截了新窗口，请允许弹窗");
                }}
              >
                在新窗口打开
              </Button>
            </Space>
            {data.error && (
              <div style={{ marginTop: 12, color: "#999", fontSize: 12 }}>{data.error}</div>
            )}
          </div>
        }
      />
    </div>
  );
};

export default FilePreview;
