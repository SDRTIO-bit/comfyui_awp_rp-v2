import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu } from "antd";
import { MessageOutlined, AppstoreOutlined, BookOutlined } from "@ant-design/icons";

const { Sider, Content } = Layout;

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = location.pathname.startsWith("/cards")
    ? "/cards"
    : location.pathname.startsWith("/novels")
      ? "/novels"
      : "/sessions";

  return (
    <Layout style={{ height: "100vh", minHeight: 0, overflow: "hidden" }}>
      <Sider width={200} theme="light" style={{ height: "100vh", overflow: "auto" }}>
        <div style={{ padding: "16px", fontWeight: "bold", fontSize: 16, textAlign: "center" }}>
          AWP RP
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={[
            { key: "/sessions", icon: <MessageOutlined />, label: "会话" },
            { key: "/novels", icon: <BookOutlined />, label: "小说" },
            { key: "/cards", icon: <AppstoreOutlined />, label: "角色卡" },
          ]}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout style={{ minHeight: 0 }}>
        <Content
          style={{
            padding: 24,
            background: "#f5f5f5",
            height: "100vh",
            minHeight: 0,
            overflow: "hidden",
            boxSizing: "border-box",
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
