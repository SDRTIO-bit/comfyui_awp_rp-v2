import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Empty, List, Popconfirm, Space, Spin, Tag, Typography, message } from "antd";
import { DeleteOutlined, MessageOutlined, PlusOutlined } from "@ant-design/icons";
import { deleteSession, listSessions, Session } from "../api/client";
import NewSessionModal from "../components/NewSessionModal";

const { Text } = Typography;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function Sessions() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  const loadSessions = () => {
    setLoading(true);
    listSessions()
      .then(setSessions)
      .catch((error) => message.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSessions();
  }, []);

  const handleDelete = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      message.success("会话已删除");
      loadSessions();
    } catch (error) {
      message.error(getErrorMessage(error));
    }
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
          gap: 12,
        }}
      >
        <Text strong style={{ fontSize: 18 }}>
          会话
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          新建会话
        </Button>
      </div>

      {loading ? (
        <Spin size="large" style={{ display: "block", margin: "100px auto" }} />
      ) : sessions.length ? (
        <List
          dataSource={sessions}
          renderItem={(session) => (
            <List.Item
              onClick={() => navigate(`/sessions/${session.session_id}`)}
              style={{ cursor: "pointer", padding: "12px 16px" }}
              extra={
                <Space onClick={(event) => event.stopPropagation()}>
                  <Tag>{session.turn_count} 回合</Tag>
                  <Popconfirm
                    title="删除这个会话？"
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => handleDelete(session.session_id)}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              }
            >
              <List.Item.Meta
                avatar={<MessageOutlined style={{ fontSize: 24, color: "#1677ff" }} />}
                title={session.card_name}
                description={
                  <>
                    <Text type="secondary">ID: {session.session_id.slice(0, 16)}...</Text>
                    <br />
                    <Text type="secondary">开场白：{session.greeting_id}</Text>
                    <br />
                    <Text type="secondary">
                      {new Date(session.last_turn_time || session.created_at).toLocaleString("zh-CN")}
                    </Text>
                  </>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty description="暂无会话" />
      )}

      <NewSessionModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={loadSessions}
      />
    </div>
  );
}
