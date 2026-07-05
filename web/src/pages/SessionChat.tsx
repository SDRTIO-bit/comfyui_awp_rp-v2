import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Empty, Input, Spin, Tag, Typography, message } from "antd";
import { ArrowLeftOutlined, DashboardOutlined, PlayCircleOutlined, SendOutlined } from "@ant-design/icons";
import {
  continueSessionV2,
  getSession,
  listTurns,
  Session,
  Turn,
} from "../api/client";
import PipelineStreamDrawer from "../components/PipelineStreamDrawer";
import PresetViewer from "../components/PresetViewer";
import WorkflowSelector from "../components/WorkflowSelector";
import "./SessionChat.css";

const { Text } = Typography;

type SessionDetails = Session & { opening_content?: string };

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function SessionChat() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [session, setSession] = useState<SessionDetails | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(true);
  const [continuing, setContinuing] = useState(false);
  const [inputText, setInputText] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerInput, setDrawerInput] = useState("");
  const [streamRunId, setStreamRunId] = useState(0);
  const [streaming, setStreaming] = useState(false);
  const [turnMode, setTurnMode] = useState("python");
  const [turnWorkflow, setTurnWorkflow] = useState("");
  const [continueMode, setContinueMode] = useState("python");
  const [continueWorkflow, setContinueWorkflow] = useState("");

  const load = useCallback((showSpinner = true) => {
    if (!id) return;
    if (showSpinner) setLoading(true);
    Promise.all([getSession(id), listTurns(id)])
      .then(([sessionDetails, turnList]) => {
        setSession(sessionDetails);
        setTurns(turnList);
      })
      .catch((error) => message.error(getErrorMessage(error)))
      .finally(() => {
        if (showSpinner) setLoading(false);
      });
  }, [id]);

  // 必须保持稳定引用：PipelineStreamDrawer 的 SSE effect 把 onComplete 放进了依赖数组，
  // 若每次 render 都新建函数，会在 effect 启动后立刻触发 cleanup → abort 进行中的 SSE 流，
  // 表现为“步骤不更新、刷新页面才出数据”。
  const handleStreamComplete = useCallback(() => {
    load(false);
  }, [load]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const turnExecutionOptions = useMemo(() => ({
    mode: turnMode,
    workflow: turnWorkflow || undefined,
  }), [turnMode, turnWorkflow]);

  const continueExecutionOptions = useMemo(() => ({
    mode: continueMode,
    workflow: continueWorkflow || undefined,
  }), [continueMode, continueWorkflow]);

  const handleContinue = async () => {
    if (!id) return;
    setContinuing(true);
    try {
      const result = await continueSessionV2(id, continueExecutionOptions);
      if (result.success) {
        message.success(`继续完成：第 ${result.turn_index ?? ""} 回合`.trim());
        load();
      } else {
        message.error("继续失败");
      }
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setContinuing(false);
    }
  };

  const handleSend = async () => {
    if (!id || !inputText.trim()) return;
    setDrawerInput(inputText.trim());
    setInputText("");
    setStreamRunId((value) => value + 1);
    setDrawerOpen(true);
  };

  if (loading) {
    return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  }

  if (!session) {
    return <Empty description="未找到会话" />;
  }

  return (
    <div className="session-chat-shell">
      <section className="session-chat-main">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/sessions")} />
          <Text strong style={{ fontSize: 18, flex: 1 }}>
            {session.card_name}
          </Text>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={continuing}
            onClick={handleContinue}
          >
            继续
          </Button>
          <Button
            icon={<DashboardOutlined />}
            onClick={() => setDrawerOpen(true)}
          >
            流程
          </Button>
        </div>

        <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
          ID: {session.session_id} | 开场白：{session.greeting_id} | {session.turn_count} 回合
        </Text>

        <div className="session-chat-scroll">
          {session.opening_content && (
            <div
              style={{
                background: "#e6f4ff",
                border: "1px solid #91caff",
                borderRadius: 8,
                padding: "12px 16px",
                marginBottom: 16,
                whiteSpace: "pre-wrap",
              }}
            >
              <Text type="secondary" style={{ fontSize: 12 }}>
                开场白（{session.greeting_id}）
              </Text>
              <div style={{ marginTop: 4 }}>{session.opening_content}</div>
            </div>
          )}

          {turns.map((turn) => (
            <div key={turn.turn_id} style={{ marginBottom: 20 }}>
              <div style={{ textAlign: "center", marginBottom: 8, fontSize: 12, color: "#999" }}>
                第 {turn.turn_index} 回合 |{" "}
                {new Date(turn.accepted_at || turn.created_at).toLocaleString("zh-CN")}
              </div>

              {turn.player_input && (
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                  <div
                    style={{
                      background: "#f0f0f0",
                      borderRadius: "12px 12px 4px 12px",
                      padding: "10px 14px",
                      maxWidth: "72%",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    <div style={{ fontSize: 12, color: "#999", marginBottom: 2 }}>玩家</div>
                    {turn.player_input}
                  </div>
                </div>
              )}

              {turn.writer_output && (
                <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 8 }}>
                  <div
                    style={{
                      background: "#e6f4ff",
                      borderRadius: "12px 12px 12px 4px",
                      padding: "10px 14px",
                      maxWidth: "72%",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    <div style={{ fontSize: 12, color: "#1677ff", marginBottom: 2 }}>写手</div>
                    {turn.writer_output}
                  </div>
                </div>
              )}

              <div style={{ textAlign: "center" }}>
                {turn.mode === "continue" && <Tag color="purple">续写</Tag>}
                {turn.writer_output && turn.writer_output.length < 1000 && (
                  <Tag color="orange">输出偏短</Tag>
                )}
              </div>
            </div>
          ))}

          <div ref={bottomRef} />
        </div>

        <div className="session-chat-composer">
          <Input.TextArea
            autoSize={{ minRows: 1, maxRows: 4 }}
            placeholder="输入玩家消息"
            value={inputText}
            onChange={(event) => setInputText(event.target.value)}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault();
                handleSend();
              }
            }}
          />
          <Button type="primary" icon={<SendOutlined />} disabled={streaming} onClick={handleSend}>
            发送
          </Button>
        </div>
      </section>

      <aside className="session-chat-sidebar">
        <WorkflowSelector
          action="turn"
          mode={turnMode}
          workflow={turnWorkflow}
          onModeChange={setTurnMode}
          onWorkflowChange={setTurnWorkflow}
        />
        <WorkflowSelector
          action="continue"
          mode={continueMode}
          workflow={continueWorkflow}
          onModeChange={setContinueMode}
          onWorkflowChange={setContinueWorkflow}
        />
        <PresetViewer />
      </aside>

      {id && (
        <PipelineStreamDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          sessionId={id}
          playerInput={drawerInput}
          streamRunId={streamRunId}
          onComplete={handleStreamComplete}
          onRunningChange={setStreaming}
          executionOptions={turnExecutionOptions}
        />
      )}
    </div>
  );
}
