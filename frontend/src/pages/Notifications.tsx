import React, { useEffect, useState } from "react";
import { List, Button, App, Spin, Tag, Empty, Typography, Popconfirm } from "antd";
import { CheckOutlined, ClearOutlined, DeleteOutlined } from "@ant-design/icons";
import { notificationApi } from "../api";

const { Text } = Typography;

const TYPE_COLOR: any = {
  mention: "blue",
  assign: "green",
  status_change: "orange",
  due_soon: "red",
  risk_alert: "volcano",
  daily_report: "purple",
};

const Notifications: React.FC = () => {
  const { message } = App.useApp();
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await notificationApi.list({ page_size: 50 });
      setData(res?.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const read = async (id: string) => {
    try {
      await notificationApi.read(id);
      load();
    } catch (e: any) {
      message.error("操作失败");
    }
  };

  const readAll = async () => {
    try {
      await notificationApi.readAll();
      message.success("全部已读");
      load();
    } catch (e: any) {
      message.error("操作失败");
    }
  };

  const remove = async (id: string) => {
    try {
      await notificationApi.remove(id);
      load();
    } catch (e: any) {
      message.error("删除失败");
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>通知中心</h2>
        <Button icon={<CheckOutlined />} onClick={readAll} data-tour="noti-read">全部已读</Button>
      </div>
      {loading ? <Spin /> : data.length === 0 ? <Empty description="暂无通知" /> : (
        <List
          dataSource={data}
          data-tour="noti-list"
          renderItem={(n: any) => (
            <List.Item
              actions={[
                !n.is_read && <Button key="r" size="small" icon={<CheckOutlined />} onClick={() => read(n.id)}>标记已读</Button>,
                <Popconfirm key="d" title="删除该通知？" onConfirm={() => remove(n.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={<span><Tag color={TYPE_COLOR[n.type] || "default"}>{n.type}</Tag> {n.title}</span>}
                description={n.content || ""}
              />
              {!n.is_read && <Tag color="blue">未读</Tag>}
            </List.Item>
          )}
        />
      )}
    </div>
  );
};

export default Notifications;
