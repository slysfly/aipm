import React, { ErrorInfo } from "react";
import { Button, Collapse, Result, Space, Typography } from "antd";

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
  showDetails: boolean;
}

interface Props {
  children: React.ReactNode;
  /** 外部 key 变化时自动重置错误状态（配合路由 location.pathname 使用） */
  resetKey?: string;
}

/**
 * 错误边界组件
 * - 捕获子组件渲染错误
 * - 显示友好的错误页面，支持展开错误详情
 * - 提供"重试"和"返回首页"按钮
 * - 开发模式下打印完整错误堆栈到控制台
 * - 支持外部 resetKey 变化时自动重置
 */
class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, showDetails: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ errorInfo: info });
    // 开发模式下打印完整错误堆栈
    if (import.meta.env.DEV) {
      console.group("🚨 [ErrorBoundary] 页面渲染错误");
      console.error("错误信息:", error);
      console.error("错误名称:", error.name);
      console.error("错误消息:", error.message);
      if (error.stack) {
        console.error("错误堆栈:\n", error.stack);
      }
      if (info?.componentStack) {
        console.error("组件堆栈:\n", info.componentStack);
      }
      console.groupEnd();
    } else {
      console.error("[ErrorBoundary]", error?.message);
      if (info?.componentStack) {
        console.warn("[ErrorBoundary] Component stack available in dev mode");
      }
    }
  }

  /** resetKey 变化时自动重置错误状态（路由切换场景） */
  componentDidUpdate(prevProps: Props) {
    if (this.state.hasError && this.props.resetKey && this.props.resetKey !== prevProps.resetKey) {
      this.setState({ hasError: false, error: undefined, errorInfo: undefined, showDetails: false });
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined, showDetails: false });
  };

  handleHome = () => {
    window.location.href = "/";
  };

  render() {
    if (this.state.hasError) {
      const { error, errorInfo } = this.state;
      const isDev = import.meta.env.DEV;

      // 构建错误详情面板
      const errorDetails = [
        { label: "错误类型", value: error?.name || "UnknownError" },
        { label: "错误消息", value: error?.message || "未知错误" },
      ];
      if (isDev && error?.stack) {
        errorDetails.push({ label: "错误堆栈", value: error.stack });
      }
      if (isDev && errorInfo?.componentStack) {
        errorDetails.push({ label: "组件堆栈", value: errorInfo.componentStack });
      }

      return (
        <Result
          status="error"
          title="页面出现错误"
          subTitle={
            <Typography.Paragraph
              type="secondary"
              ellipsis={isDev ? false : { rows: 2, expandable: true, symbol: "展开详情" }}
              style={{ maxWidth: 560, margin: "0 auto", marginBottom: 16 }}
            >
              {error?.message || "发生未知错误，请尝试刷新页面或联系管理员"}
            </Typography.Paragraph>
          }
          extra={
            <Space direction="vertical" style={{ width: "100%", maxWidth: 560 }}>
              <Space>
                <Button type="primary" onClick={this.handleRetry}>
                  重试
                </Button>
                <Button onClick={this.handleHome}>
                  返回首页
                </Button>
              </Space>

              {/* 错误详情折叠面板 — 开发模式下默认展开 */}
              <Collapse
                ghost
                size="small"
                defaultActiveKey={isDev ? ["error-detail"] : undefined}
                items={[
                  {
                    key: "error-detail",
                    label: <Typography.Text type="secondary" style={{ fontSize: 13 }}>查看错误详情</Typography.Text>,
                    children: (
                      <div style={{ textAlign: "left", fontSize: 12 }}>
                        {errorDetails.map((item, i) => (
                          <div key={i} style={{ marginBottom: 8 }}>
                            <Typography.Text strong style={{ fontSize: 12 }}>{item.label}：</Typography.Text>
                            <Typography.Paragraph
                              code
                              style={{
                                fontSize: 11,
                                marginBottom: 0,
                                padding: 8,
                                background: "#F5F5F5",
                                borderRadius: 4,
                                maxHeight: i >= 2 ? 200 : undefined,
                                overflow: "auto",
                                whiteSpace: "pre-wrap",
                                wordBreak: "break-all",
                              }}
                            >
                              {item.value}
                            </Typography.Paragraph>
                          </div>
                        ))}
                        {!isDev && (
                          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                            切换到开发模式可查看完整堆栈信息
                          </Typography.Text>
                        )}
                      </div>
                    ),
                  },
                ]}
              />
            </Space>
          }
          style={{
            padding: 48,
            minHeight: "60vh",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
          }}
        />
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
