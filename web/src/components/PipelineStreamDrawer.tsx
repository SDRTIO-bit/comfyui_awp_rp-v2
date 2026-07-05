import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import { Button, Card, Collapse, Drawer, Input, Space, Tag, Typography, message } from "antd";
import {
  ExecutionOptions,
  runConsoleCommand,
  sendTurnStream,
  StepPayload,
  StreamEvent,
} from "../api/client";
import "./PipelineStreamDrawer.css";

const { Paragraph, Text } = Typography;

const STEP_LABELS: Record<string, string> = {
  round_snapshot: "回合快照",
  director: "总控规划",
  director_delegation: "总控委派",
  sub_agents: "子代理分析",
  writer: "写作",
  quality_gate: "质量门",
  turn_evolution_curator: "演进策展",
  state_commit: "状态提交",
  memory_curator: "记忆治理",
};

type StepStatus = "pending" | "done" | "failed";

interface StepState {
  name: string;
  label: string;
  status: StepStatus;
  payload?: StepPayload;
  duration_ms?: number;
  writerOutput?: string;
}

interface ConsoleEntry {
  id: number;
  time: string;
  level: "info" | "error";
  title: string;
  data: unknown;
}

interface PipelineStreamDrawerProps {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  playerInput: string;
  streamRunId: number;
  onComplete: () => void;
  onRunningChange?: (running: boolean) => void;
  executionOptions?: ExecutionOptions;
}

function initialSteps(names: string[]): StepState[] {
  return names.map((name) => ({
    name,
    label: STEP_LABELS[name] || name,
    status: "pending",
  }));
}

function valueText(value: unknown): string {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function statusIcon(status: StepStatus) {
  if (status === "done") return <CheckCircleOutlined className="pipeline-step-icon done" />;
  if (status === "failed") return <CloseCircleOutlined className="pipeline-step-icon failed" />;
  return <ClockCircleOutlined className="pipeline-step-icon pending" />;
}

function verdictText(verdict: unknown): string {
  if (verdict === "pass") return "通过";
  if (verdict === "fail") return "拒绝";
  return valueText(verdict);
}

function finalizeFailedSteps(steps: StepState[]): StepState[] {
  if (steps.some((step) => step.status === "failed")) return steps;

  const next = [...steps];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].status === "done") {
      next[i] = { ...next[i], status: "failed" };
      return next;
    }
  }
  if (next.length > 0) next[0] = { ...next[0], status: "failed" };
  return next;
}

function formatStreamError(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error || "");
  if (text.includes("No tool_call or valid JSON in response")) {
    return "模型没有返回可用的工具调用或 JSON";
  }
  if (text.includes("EMPTY_RESPONSE")) {
    return "模型返回了空响应";
  }
  if (text.includes("Streaming response body unavailable")) {
    return "流式响应正文不可用";
  }
  return text || "发送失败";
}

function renderStepBody(step: StepState) {
  const payload = step.payload || {};
  if (step.status === "pending" && !step.payload) {
    return <Text type="secondary">等待执行</Text>;
  }

  switch (step.name) {
    case "round_snapshot":
      return (
        <Text>
          召回 L1:{valueText(payload.l1_turn_ids_recalled_count)} L2:
          {valueText(payload.l2_memory_ids_recalled_count)} L3:
          {valueText(payload.l3_memory_ids_recalled_count)} | 世界书：
          {valueText(payload.worldbook_activated_count)}
        </Text>
      );
    case "director": {
      const hasPlan = Boolean(payload.turn_goal || payload.scene_focus);
      return (
        <Space direction="vertical" size={2}>
          <Text>
            {valueText(payload.provider_type)} / {valueText(payload.model)}
          </Text>
          {payload.call_success === false && <Tag color="red">{valueText(payload.failure_code)}</Tag>}
          {hasPlan && (
            <Collapse size="small" ghost items={[{
              key: "plan",
              label: <Text type="secondary">计划 {valueText(payload.plan_ref).slice(0, 24)}…</Text>,
              children: (
                <Space direction="vertical" size={2} style={{ fontSize: 12 }}>
                  {Boolean(payload.turn_goal) && <div><Text strong>目标：</Text>{String(payload.turn_goal)}</div>}
                  {Boolean(payload.scene_focus) && <div><Text strong>焦点：</Text>{String(payload.scene_focus)}</div>}
                  {Array.isArray(payload.must_preserve_facts) && payload.must_preserve_facts.length > 0 && (
                    <div><Text strong>必须保留：</Text>{(payload.must_preserve_facts as string[]).join("；")}</div>
                  )}
                  {Array.isArray(payload.must_not_do) && payload.must_not_do.length > 0 && (
                    <div><Text strong>禁止：</Text>{(payload.must_not_do as string[]).join("；")}</div>
                  )}
                  {Array.isArray(payload.narrative_opportunities) && payload.narrative_opportunities.length > 0 && (
                    <div><Text strong>机会：</Text>{(payload.narrative_opportunities as string[]).join("；")}</div>
                  )}
                  {Array.isArray(payload.writer_constraints) && payload.writer_constraints.length > 0 && (
                    <div><Text strong>约束：</Text>{(payload.writer_constraints as string[]).join("；")}</div>
                  )}
                  {Array.isArray(payload.active_character_refs) && payload.active_character_refs.length > 0 && (
                    <div><Text strong>角色：</Text>{(payload.active_character_refs as string[]).join("；")}</div>
                  )}
                </Space>
              ),
            }]} />
          )}
        </Space>
      );
    }
    case "director_delegation":
      return (
        <Space direction="vertical" size={4}>
          <Text type="secondary">{valueText(payload.source)}</Text>
          <Space wrap>
            {Array.isArray(payload.requested_agents) && payload.requested_agents.length > 0
              ? payload.requested_agents.map((agent) => <Tag key={String(agent)}>{String(agent)}</Tag>)
              : <Tag>无</Tag>}
          </Space>
        </Space>
      );
    case "sub_agents": {
      const dispositions = (payload.agent_dispositions || {}) as Record<string, unknown>;
      const items = Object.entries(dispositions).map(([role, summary]) => ({
        key: role,
        label: role,
        children: <Paragraph style={{ marginBottom: 0 }}>{valueText(summary)}</Paragraph>,
      }));
      return items.length > 0 ? (
        <Collapse size="small" ghost items={items} />
      ) : (
        <Text type="secondary">没有子代理</Text>
      );
    }
    case "writer":
      return step.writerOutput ? (
        <Paragraph style={{ maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap", marginBottom: 0 }}>
          {step.writerOutput}
        </Paragraph>
      ) : (
        <Text type="secondary">正在写作...（{valueText(payload.text_length)} 字）</Text>
      );
    case "quality_gate":
      return (
        <Space direction="vertical" size={4}>
          <Space>
            <Tag color={payload.verdict === "pass" ? "green" : "red"}>
              {verdictText(payload.verdict)}
            </Tag>
            <Text>评分 {valueText(payload.overall_score)}</Text>
          </Space>
          {Array.isArray(payload.blocking_reasons) && payload.blocking_reasons.length > 0 && (
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {payload.blocking_reasons.join("; ")}
            </Paragraph>
          )}
        </Space>
      );
    case "turn_evolution_curator":
      return (
        <Text>
          状态 {valueText(payload.proposed_state_changes_count)} | 活跃{" "}
          {valueText(payload.memory_candidates_active_count)} | RAG{" "}
          {valueText(payload.memory_candidates_rag_count)} | 置信度{" "}
          {valueText(payload.curator_confidence)}
        </Text>
      );
    case "state_commit":
      return (
        <Text>
          {valueText(payload.commit_status)} | 修订 {valueText(payload.revision_before)}
          {" -> "}
          {valueText(payload.revision_after)}
        </Text>
      );
    case "memory_curator":
      return (
        <Space direction="vertical" size={2}>
          <Text>{valueText(payload.curation_status)}</Text>
          <Text type="secondary">{valueText(payload.curation_reason)}</Text>
          <Text type="secondary">
            提交 {valueText(payload.commit_ids_count)} | 活跃{" "}
            {valueText(payload.active_committed_count)} | RAG{" "}
            {valueText(payload.rag_committed_count)}
          </Text>
        </Space>
      );
    default:
      return <Paragraph style={{ marginBottom: 0 }}>{JSON.stringify(payload)}</Paragraph>;
  }
}

function consoleEntryText(entry: ConsoleEntry): string {
  let body = "";
  try {
    body = JSON.stringify(entry.data, null, 2);
  } catch {
    body = String(entry.data);
  }
  return `[${entry.time}] ${entry.level.toUpperCase()} ${entry.title}\n${body}`;
}

export default function PipelineStreamDrawer({
  open,
  onClose,
  sessionId,
  playerInput,
  streamRunId,
  onComplete,
  onRunningChange,
  executionOptions,
}: PipelineStreamDrawerProps) {
  const defaultStepNames = useMemo(() => Object.keys(STEP_LABELS), []);
  const [steps, setSteps] = useState<StepState[]>(() => initialSteps(defaultStepNames));
  const [running, setRunning] = useState(false);
  const [consoleEntries, setConsoleEntries] = useState<ConsoleEntry[]>([]);
  const [consoleCommand, setConsoleCommand] = useState("");
  const [commandRunning, setCommandRunning] = useState(false);
  const startedRunRef = useRef<number | null>(null);
  const consoleSeqRef = useRef(0);

  const pushConsole = (entry: Omit<ConsoleEntry, "id" | "time">) => {
    const id = consoleSeqRef.current + 1;
    consoleSeqRef.current = id;
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    setConsoleEntries((current) => [
      ...current.slice(-79),
      {
        id,
        time,
        ...entry,
      },
    ]);
  };

  const submitConsoleCommand = async () => {
    const command = consoleCommand.trim();
    if (!command) return;
    setConsoleCommand("");
    if (command.toLowerCase() === "clear") {
      setConsoleEntries([]);
      consoleSeqRef.current = 0;
      return;
    }
    pushConsole({
      level: "info",
      title: `$ ${command}`,
      data: { command, sessionId },
    });
    setCommandRunning(true);
    try {
      const result = await runConsoleCommand(command, sessionId);
      pushConsole({
        level: result.ok ? "info" : "error",
        title: `result: ${command}`,
        data: result,
      });
    } catch (error) {
      pushConsole({
        level: "error",
        title: `command_error: ${command}`,
        data: {
          message: error instanceof Error ? error.message : String(error || ""),
        },
      });
    } finally {
      setCommandRunning(false);
    }
  };

  useEffect(() => {
    if (!open || !sessionId || !playerInput || startedRunRef.current === streamRunId) return;
    startedRunRef.current = streamRunId;
    setSteps(initialSteps(defaultStepNames));
    setConsoleEntries([]);
    consoleSeqRef.current = 0;
    setRunning(true);
    onRunningChange?.(true);
    const controller = new AbortController();
    pushConsole({
      level: "info",
      title: "request",
      data: { sessionId, playerInput, executionOptions },
    });

    const handleEvent = (event: StreamEvent) => {
      pushConsole({
        level: event.type === "done" && !event.success ? "error" : "info",
        title: event.type,
        data: event,
      });
      if (event.type === "started") {
        setSteps(initialSteps(event.steps));
        return;
      }
      if (event.type === "step") {
        setSteps((current) =>
          current.map((step) =>
            step.name === event.step
              ? {
                  ...step,
                  status: event.payload.call_success === false ? "failed" : "done",
                  payload: event.payload,
                  duration_ms: event.duration_ms,
                }
              : step,
          ),
        );
        return;
      }
      if (event.type === "writer_text") {
        setSteps((current) =>
          current.map((step) =>
            step.name === "writer" ? { ...step, writerOutput: event.writer_output } : step,
          ),
        );
        return;
      }
      if (event.type === "done") {
        setRunning(false);
        onRunningChange?.(false);
        if (event.success) {
          onComplete();
        } else {
          setSteps(finalizeFailedSteps);
          message.error(formatStreamError(event.error));
        }
      }
    };

    sendTurnStream(sessionId, playerInput, handleEvent, executionOptions, controller.signal).catch((error) => {
      if (controller.signal.aborted) return;
      setRunning(false);
      onRunningChange?.(false);
      setSteps(finalizeFailedSteps);
      pushConsole({
        level: "error",
        title: "stream_error",
        data: {
          message: formatStreamError(error),
          raw: error instanceof Error ? error.message : String(error || ""),
        },
      });
      message.error(formatStreamError(error));
    });

    return () => {
      controller.abort();
      onRunningChange?.(false);
    };
  }, [defaultStepNames, executionOptions, onComplete, onRunningChange, open, playerInput, sessionId, streamRunId]);

  return (
    <Drawer
      title="流程"
      placement="left"
      width="min(420px, 100vw)"
      open={open}
      onClose={onClose}
      mask={false}
      className="pipeline-stream-drawer"
      extra={running ? <Tag color="processing">运行中</Tag> : <Tag>空闲</Tag>}
    >
      <Space className="pipeline-step-list" direction="vertical" size={10}>
        <Card size="small" title="运行控制台">
          <Space.Compact style={{ width: "100%", marginBottom: 8 }}>
            <Input
              value={consoleCommand}
              onChange={(event) => setConsoleCommand(event.target.value)}
              onPressEnter={submitConsoleCommand}
              placeholder="help / context / session / turns 5 / state / workflows / presets / clear"
              disabled={commandRunning}
            />
            <Button type="primary" loading={commandRunning} onClick={submitConsoleCommand}>
              Run
            </Button>
          </Space.Compact>
          {consoleEntries.length === 0 ? (
            <Text type="secondary">等待事件</Text>
          ) : (
            <Collapse
              size="small"
              ghost
              items={consoleEntries.map((entry) => ({
                key: String(entry.id),
                label: (
                  <Space>
                    <Tag color={entry.level === "error" ? "red" : "blue"}>{entry.level}</Tag>
                    <Text>{entry.title}</Text>
                    <Text type="secondary">{entry.time}</Text>
                  </Space>
                ),
                children: (
                  <pre className="pipeline-console-entry">
                    {consoleEntryText(entry)}
                  </pre>
                ),
              }))}
            />
          )}
        </Card>
        {steps.map((step, index) => (
          <Card
            key={step.name}
            size="small"
            className={`pipeline-step-card ${step.status}`}
            style={{ animationDelay: `${index * 38}ms` }}
            title={
              <Space>
                {statusIcon(step.status)}
                <Text strong>{step.label}</Text>
              </Space>
            }
            extra={
              step.duration_ms !== undefined ? (
                <Text type="secondary">{step.duration_ms}ms</Text>
              ) : null
            }
            styles={{ body: { fontSize: 13 } }}
          >
            {renderStepBody(step)}
          </Card>
        ))}
      </Space>
    </Drawer>
  );
}
