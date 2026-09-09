import React from "react";
import { Spin, Empty, Alert, Button, Result } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

export type AsyncStatus = "loading" | "error" | "empty" | "success";

interface AsyncStateProps {
  status: AsyncStatus;
  /** error 模式下展示的错误信息 */
  error?: string | null;
  /** empty 模式下的提示文案 */
  emptyText?: string;
  /** empty 模式下可选的操作按钮 */
  emptyAction?: React.ReactNode;
  /** 重试回调（error / empty 模式的"重试"按钮） */
  onRetry?: () => void;
  /** 子内容（status === success 时渲染） */
  children: React.ReactNode;
  /** 自定义 loading 文案 */
  loadingText?: string;
  /** 最小高度，避免布局跳动 */
  minHeight?: number | string;
}

/**
 * 统一的异步三态边界组件（Loading / Empty / Error）。
 * 用法：任何需要拉取数据的页面，用 status 驱动渲染，避免各页面散落 Spin/Empty/Alert。
 */
const AsyncState: React.FC<AsyncStateProps> = ({
  status, error, emptyText = "暂无数据", emptyAction, onRetry, children, loadingText = "加载中...", minHeight = 240,
}) => {
  if (status === "loading") {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight }}>
        <Spin size="large" tip={loadingText} />
      </div>
    );
  }
  if (status === "error") {
    return (
      <Alert
        type="error"
        showIcon
        message="加载失败"
        description={error || "请求异常，请稍后重试"}
        action={onRetry ? <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>重试</Button> : undefined}
        style={{ margin: "24px 0" }}
      />
    );
  }
  if (status === "empty") {
    return (
      <div style={{ padding: "40px 0" }}>
        <Empty description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE}>
          {emptyAction}
          {onRetry && (
            <Button icon={<ReloadOutlined />} onClick={onRetry} style={{ marginTop: 12 }}>
              重新加载
            </Button>
          )}
        </Empty>
      </div>
    );
  }
  return <>{children}</>;
};

export default AsyncState;
