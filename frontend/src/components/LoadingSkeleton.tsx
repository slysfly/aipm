import React from "react";
import { Skeleton, Card, Space, Row, Col, Divider } from "antd";

interface LoadingSkeletonProps {
  /** 骨架屏类型 */
  type?: "card" | "table" | "list" | "form" | "detail" | "chart";
  /** 卡片/行数 */
  rows?: number;
  /** 每行列数（仅 card 类型有效） */
  columns?: number;
  /** 是否带标题栏 */
  header?: boolean;
}

/** 卡片骨架 — 模拟卡片网格 */
const CardSkeleton: React.FC<{ rows: number; columns: number }> = ({ rows, columns }) => (
  <>
    {Array.from({ length: rows }).map((_, ri) => (
      <Row key={ri} gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {Array.from({ length: columns }).map((_, ci) => (
          <Col key={ci} span={Math.floor(24 / columns)}>
            <Card>
              <Space direction="vertical" style={{ width: "100%" }}>
                <Skeleton.Input active size="small" style={{ width: "40%" }} />
                <Skeleton.Input active size="small" style={{ width: "100%" }} />
                <Skeleton.Input active size="small" style={{ width: "70%" }} />
                <Skeleton paragraph={{ rows: 1 }} active />
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
    ))}
  </>
);

/** 表格骨架 — 模拟表格行和列 */
const TableSkeleton: React.FC<{ rows: number }> = ({ rows }) => (
  <Card>
    <Skeleton.Input active style={{ width: 120, height: 22, marginBottom: 16 }} />
    <Skeleton active paragraph={{ rows: 1 }} style={{ marginBottom: 8 }} />
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} style={{ display: "flex", gap: 16, marginBottom: 12, alignItems: "center" }}>
        <Skeleton.Input active size="small" style={{ width: "18%", height: 22 }} />
        <Skeleton.Input active size="small" style={{ width: "25%", height: 22 }} />
        <Skeleton.Input active size="small" style={{ width: "15%", height: 22 }} />
        <Skeleton.Input active size="small" style={{ width: "12%", height: 22 }} />
        <Skeleton.Input active size="small" style={{ width: "10%", height: 22 }} />
        <Skeleton.Input active size="small" style={{ width: "10%", height: 22 }} />
      </div>
    ))}
  </Card>
);

/** 列表骨架 — 模拟带头像的列表项 */
const ListSkeleton: React.FC<{ rows: number }> = ({ rows }) => (
  <Card>
    {Array.from({ length: rows }).map((_, i) => (
      <div
        key={i}
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 16,
          paddingBottom: 16,
          borderBottom: i < rows - 1 ? "1px solid #F0F0F0" : "none",
        }}
      >
        <Skeleton.Avatar active size={40} />
        <div style={{ flex: 1 }}>
          <Skeleton.Input active size="small" style={{ width: "50%", marginBottom: 8 }} />
          <Skeleton.Input active size="small" style={{ width: "80%" }} />
        </div>
      </div>
    ))}
  </Card>
);

/** 表单骨架 — 模拟表单字段 */
const FormSkeleton: React.FC = () => (
  <Card>
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Skeleton.Input active size="small" style={{ width: 80, height: 22 }} />
          <Skeleton.Input
            active
            size="small"
            style={{ width: i === 2 ? "100%" : "60%", height: 32 }}
          />
        </div>
      ))}
      <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
        <Skeleton.Button active size="default" style={{ width: 80 }} />
        <Skeleton.Button active size="default" style={{ width: 80 }} />
      </div>
    </Space>
  </Card>
);

/** 详情页骨架 — 模拟左侧描述 + 右侧统计的面板布局 */
const DetailSkeleton: React.FC = () => (
  <div>
    {/* 标题区 */}
    <Skeleton.Input active size="large" style={{ width: 240, height: 28, marginBottom: 8 }} />
    <Skeleton.Input active size="small" style={{ width: 360, height: 16, marginBottom: 24 }} />
    <Divider style={{ margin: "0 0 24px" }} />

    {/* 统计卡片行 */}
    <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
      {[1, 2, 3, 4].map((_, i) => (
        <Col key={i} span={6}>
          <Card size="small">
            <Skeleton.Input active size="small" style={{ width: "50%", height: 14, marginBottom: 8 }} />
            <Skeleton.Input active size="large" style={{ width: "30%", height: 32 }} />
          </Card>
        </Col>
      ))}
    </Row>

    {/* 主要内容区 — 两栏布局 */}
    <Row gutter={[24, 24]}>
      <Col span={16}>
        <Card title={<Skeleton.Input active size="small" style={{ width: 100 }} />}>
          <Skeleton active paragraph={{ rows: 4 }} />
        </Card>
      </Col>
      <Col span={8}>
        <Card title={<Skeleton.Input active size="small" style={{ width: 80 }} />}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Skeleton.Input active size="small" style={{ width: "100%", height: 32 }} />
            <Skeleton.Input active size="small" style={{ width: "100%", height: 32 }} />
            <Skeleton.Input active size="small" style={{ width: "100%", height: 32 }} />
          </Space>
        </Card>
      </Col>
    </Row>
  </div>
);

/** 图表骨架 — 模拟统计图表区域 */
const ChartSkeleton: React.FC<{ rows: number }> = ({ rows }) => (
  <Row gutter={[16, 16]}>
    {Array.from({ length: rows }).map((_, i) => (
      <Col key={i} span={i === 0 ? 24 : 12}>
        <Card title={<Skeleton.Input active size="small" style={{ width: 120 }} />}>
          <div style={{ padding: "16px 0" }}>
            {/* 模拟柱状图/折线图 */}
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", height: 160, padding: "0 8px" }}>
              {Array.from({ length: 8 }).map((__, j) => (
                <Skeleton.Input
                  key={j}
                  active
                  size="small"
                  style={{
                    flex: 1,
                    height: `${30 + Math.random() * 120}px`,
                    borderRadius: "4px 4px 0 0",
                  }}
                />
              ))}
            </div>
            {/* X 轴标签 */}
            <div style={{ display: "flex", gap: 8, marginTop: 8, padding: "0 8px" }}>
              {Array.from({ length: 8 }).map((__, j) => (
                <Skeleton.Input key={j} active size="small" style={{ flex: 1, height: 12 }} />
              ))}
            </div>
          </div>
        </Card>
      </Col>
    ))}
  </Row>
);

/**
 * 通用页面加载骨架屏
 * 支持多种类型：
 * - card: 卡片网格
 * - table: 表格行
 * - list: 列表项
 * - form: 表单字段
 * - detail: 详情页布局（标题 + 统计卡片 + 双栏内容）
 * - chart: 图表区域
 * 用于页面级数据加载时的占位显示，替代全局 Spin，视觉更平滑。
 */
const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  type = "card",
  rows = 3,
  columns = 2,
  header = true,
}) => {
  return (
    <div style={{ padding: 24 }}>
      {header && type !== "detail" && (
        <div style={{ marginBottom: 24 }}>
          <Skeleton.Input active size="large" style={{ width: 200, height: 28, marginBottom: 8 }} />
          <Skeleton.Input active size="small" style={{ width: 320, height: 16 }} />
        </div>
      )}

      {type === "card" && <CardSkeleton rows={rows} columns={columns} />}
      {type === "table" && <TableSkeleton rows={rows} />}
      {type === "list" && <ListSkeleton rows={rows} />}
      {type === "form" && <FormSkeleton />}
      {type === "detail" && <DetailSkeleton />}
      {type === "chart" && <ChartSkeleton rows={rows} />}
    </div>
  );
};

export default LoadingSkeleton;
