import React, { useEffect, useState } from "react";
import {
  Card, Button, Select, App, Spin, Input, Typography, Space, Divider, Row, Col, Tag,
} from "antd";
import { DownloadOutlined, FilePdfOutlined, SendOutlined, RobotOutlined } from "@ant-design/icons";
import { reportApi, projectApi } from "../api";

const { Title, Paragraph, Text } = Typography;

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  window.URL.revokeObjectURL(url);
}

const REPORT_TYPES = [
  { value: "project-progress", label: "项目进度" },
  { value: "burndown", label: "燃尽图" },
  { value: "velocity", label: "速度图" },
  { value: "cumulative-flow", label: "累积流" },
  { value: "evm", label: "EVM挣值" },
  { value: "resource-utilization", label: "资源利用率" },
  { value: "risk-trend", label: "风险趋势" },
];

const Reports: React.FC = () => {
  const { message } = App.useApp();
  const [projects, setProjects] = useState<any[]>([]);
  const [exportType, setExportType] = useState("project-progress");
  const [exportFormat, setExportFormat] = useState("csv");
  const [exportProject, setExportProject] = useState<string>("");
  const [pdfProject, setPdfProject] = useState<string>("");
  const [daily, setDaily] = useState<any>(null);
  const [weekly, setWeekly] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    projectApi.list({ page_size: 100 }).then((r) => {
      const items = r?.items || [];
      setProjects(items);
      if (items[0]) {
        setExportProject(items[0].id);
        setPdfProject(items[0].id);
      }
    }).catch(() => {});
  }, []);

  const exportReport = async () => {
    if (!exportProject) return message.warning("请选择项目");
    try {
      const blob = await reportApi.exportReport({
        project_id: exportProject,
        report_type: exportType,
        format_type: exportFormat,
      });
      triggerDownload(blob, `${exportType}_${exportProject}.${exportFormat}`);
      message.success("报表已导出");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "导出失败");
    }
  };

  const exportPdf = async () => {
    if (!pdfProject) return message.warning("请选择项目");
    try {
      const blob = await reportApi.exportProjectPdf(pdfProject);
      triggerDownload(blob, `report_${pdfProject}.pdf`);
      message.success("PDF 已导出");
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "PDF 导出失败（需安装 reportlab）");
    }
  };

  const genDaily = async () => {
    setLoading(true);
    try {
      setDaily(await reportApi.daily());
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const genWeekly = async () => {
    setLoading(true);
    try {
      setWeekly(await reportApi.weekly());
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "生成失败");
    } finally {
      setLoading(false);
    }
  };

  const sendDaily = async () => {
    try {
      const res = await reportApi.sendDaily({ project_id: exportProject || null, send_type: "email" });
      message.success("日报已生成并发送");
      console.log(res);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "发送失败");
    }
  };

  return (
    <div>
      <Title level={3}>报表中心</Title>

      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card title="数据报表导出">
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select style={{ width: "100%" }} placeholder="选择项目" value={exportProject || undefined}
                options={projects.map((p: any) => ({ value: p.id, label: p.name }))} onChange={setExportProject} />
              <Select style={{ width: "100%" }} value={exportType} options={REPORT_TYPES} onChange={setExportType} data-tour="reports-type" />
              <Select style={{ width: "100%" }} value={exportFormat}
                options={[{ value: "csv", label: "CSV" }, { value: "json", label: "JSON" }]} onChange={setExportFormat} />
              <Button type="primary" icon={<DownloadOutlined />} onClick={exportReport} data-tour="reports-export">导出报表</Button>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="项目报告 PDF">
            <Space direction="vertical" style={{ width: "100%" }}>
              <Select style={{ width: "100%" }} placeholder="选择项目" value={pdfProject || undefined}
                options={projects.map((p: any) => ({ value: p.id, label: p.name }))} onChange={setPdfProject} />
              <Button icon={<FilePdfOutlined />} onClick={exportPdf}>导出 PDF 报告</Button>
              <Divider />
              <Button icon={<SendOutlined />} onClick={sendDaily}>生成并发送每日日报（邮件+站内通知）</Button>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card title="AI 智能报告" style={{ marginTop: 16 }}>
        <Space>
          <Button icon={<RobotOutlined />} loading={loading} onClick={genDaily}>生成 AI 日报</Button>
          <Button icon={<RobotOutlined />} loading={loading} onClick={genWeekly}>生成 AI 周报</Button>
        </Space>
        {daily && (
          <div style={{ marginTop: 16 }}>
            <Text strong>日报：</Text>
            <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6, maxHeight: 300, overflow: "auto" }}>
              {JSON.stringify(daily, null, 2)}
            </pre>
          </div>
        )}
        {weekly && (
          <div style={{ marginTop: 16 }}>
            <Text strong>周报：</Text>
            <pre style={{ background: "#f5f5f5", padding: 12, borderRadius: 6, maxHeight: 300, overflow: "auto" }}>
              {JSON.stringify(weekly, null, 2)}
            </pre>
          </div>
        )}
      </Card>
    </div>
  );
};

export default Reports;
