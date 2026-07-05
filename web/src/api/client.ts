const BASE = "";

interface ApiEnvelope<T> {
  data?: T;
}

export interface Session {
  session_id: string;
  card_id: string;
  card_name: string;
  greeting_id: string;
  turn_count: number;
  last_turn_time: string;
  created_at: string;
  status: string;
}

export interface Turn {
  turn_id: string;
  turn_index: number;
  mode: string;
  player_input: string;
  writer_output: string;
  base_card_state_revision: number;
  result_card_state_revision: number;
  accepted_at: string;
  created_at: string;
}

export interface Card {
  card_id: string;
  version: number;
  name: string;
  status: string;
  greeting_count: number;
  worldbook_count: number;
  created_at: string;
}

export interface Opening {
  opening_record_id: string;
  greeting_id: string;
  content: string;
  created_at: string;
}

export type ExecutionMode = "hybrid" | "python" | "";

export interface ExecutionOptions {
  mode?: string;
  workflow?: string;
}

export interface TurnCommandResult {
  success: boolean;
  turn_id?: string;
  turn_index?: number;
  quality?: string;
  writer_output?: string;
}

export interface StepPayload {
  [key: string]: unknown;
}

export type StreamEvent =
  | { type: "started"; turn_id: string; steps: string[] }
  | { type: "step"; step: string; payload: StepPayload; duration_ms: number }
  | { type: "writer_text"; turn_id: string; writer_output: string }
  | {
      type: "done";
      success: boolean;
      turn_id?: string;
      turn_index?: number;
      writer_output?: string;
      error?: string;
      failure_code?: string;
    };

export interface ImportCardResult {
  success: boolean;
  session_id: string;
  card_id: string;
  diagnostics?: Record<string, unknown>;
}

export interface GreetingInfo {
  greeting_id: string;
  label: string;
  is_default: boolean;
  preview: string;
}

export interface CreateSessionResult {
  session_id: string;
  card_id: string;
  greeting_id: string;
  diagnostics?: Record<string, unknown>;
}

export interface WorkflowInfo {
  name: string;
  node_count: number;
  class_types: string[];
}

export interface WriterPresetInfo {
  name: string;
  content: string;
  path: string;
}

export interface ConsoleCommandResult {
  ok: boolean;
  command: string;
  output: string;
  data: Record<string, unknown>;
}

function errorMessage(body: ApiEnvelope<{ error?: string }> | undefined, status: number): string {
  return body?.data?.error || `HTTP ${status}`;
}

async function parseJson<T>(res: Response): Promise<ApiEnvelope<T>> {
  return (await res.json()) as ApiEnvelope<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/awp/api/v1${path}`);
  const body = await parseJson<T>(res);
  if (!res.ok) throw new Error(errorMessage(body as ApiEnvelope<{ error?: string }>, res.status));
  return body.data as T;
}

async function post<T>(path: string, payload?: unknown): Promise<T> {
  const res = await fetch(`${BASE}/awp/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const body = await parseJson<T>(res);
  if (!res.ok) throw new Error(errorMessage(body as ApiEnvelope<{ error?: string }>, res.status));
  return body.data as T;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/awp/api/v1${path}`, { method: "DELETE" });
  const body = await parseJson<T>(res);
  if (!res.ok) throw new Error(errorMessage(body as ApiEnvelope<{ error?: string }>, res.status));
  return body.data as T;
}

function withExecutionQuery(path: string, opts?: ExecutionOptions): string {
  const params = new URLSearchParams();
  if (opts?.mode) params.set("mode", opts.mode);
  if (opts?.workflow) params.set("workflow", opts.workflow);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export async function listSessions(): Promise<Session[]> {
  return get<Session[]>("/sessions");
}

export async function getSession(id: string): Promise<Session & { opening_content: string }> {
  return get(`/sessions/${encodeURIComponent(id)}`);
}

export async function listTurns(sessionId: string): Promise<Turn[]> {
  return get<Turn[]>(`/sessions/${encodeURIComponent(sessionId)}/turns`);
}

export async function getOpening(sessionId: string): Promise<Opening> {
  return get<Opening>(`/sessions/${encodeURIComponent(sessionId)}/opening`);
}

export async function listCards(): Promise<Card[]> {
  return get<Card[]>("/cards");
}

export async function continueSession(sessionId: string): Promise<{ success: boolean; turn_id: string; turn_index: number; quality: string; writer_output: string }> {
  return continueSessionV2(sessionId) as Promise<{ success: boolean; turn_id: string; turn_index: number; quality: string; writer_output: string }>;
}

export async function sendTurn(
  sessionId: string,
  playerInput: string,
  opts?: ExecutionOptions,
): Promise<TurnCommandResult> {
  return post<TurnCommandResult>(
    withExecutionQuery(`/sessions/${encodeURIComponent(sessionId)}/turn`, opts),
    { player_input: playerInput },
  );
}

export function parseSSEBlock(block: string): StreamEvent | null {
  let type = "";
  const dataLines: string[] = [];
  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) {
      type = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (!type || dataLines.length === 0) return null;
  const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
  return { type, ...data } as StreamEvent;
}

export async function sendTurnStream(
  sessionId: string,
  playerInput: string,
  onEvent: (event: StreamEvent) => void,
  opts?: ExecutionOptions,
  signal?: AbortSignal,
): Promise<void> {
  // SSE 实时流式接收；8s 内若连一个事件都没收到，回落为轮询 /turns 兜底。
  // 注意：python 模式会逐步推 step 事件，gotEvent 会很快置 true；hybrid/工作流模式
  // 后端会立即推 started 事件（即使后续要等 ComfyUI 跑完才有 done），所以正常
  // 情况下 8s 内一定会收到事件，这个兜底只在 SSE 真的没动静时才触发。
  const res = await fetch(
    `${BASE}/awp/api/v1${withExecutionQuery(
      `/sessions/${encodeURIComponent(sessionId)}/turn/stream`,
      opts,
    )}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_input: playerInput }),
      signal,
    },
  );
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      message = errorMessage(await parseJson<{ error?: string }>(res), res.status);
    } catch {
      // Keep the HTTP status if the server did not return JSON.
    }
    throw new Error(message);
  }
  if (!res.body) throw new Error("流式响应正文不可用");

  let gotEvent = false;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Start a polling fallback timer: if no SSE event arrives within 8s,
  // poll the turns endpoint for the result.
  const knownTurnCount = await _getTurnCount(sessionId, signal);
  const pollTimer = setTimeout(async () => {
    if (gotEvent || signal?.aborted) return;
    // 8s 内一个 SSE 事件都没收到（连接异常或后端迟迟没推），改轮询 /turns 兜底拿结果。
    const result = await _pollForNewTurn(sessionId, knownTurnCount, signal);
    if (result && !signal?.aborted) {
      onEvent({ type: "started", turn_id: result.turn_id, steps: [] });
      onEvent({
        type: "writer_text",
        turn_id: result.turn_id,
        writer_output: result.writer_output,
      });
      onEvent({
        type: "done",
        success: true,
        turn_id: result.turn_id,
        turn_index: result.turn_index,
        writer_output: result.writer_output,
      });
    }
  }, 8000);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      gotEvent = true;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop() || "";
      for (const part of parts) {
        const event = parseSSEBlock(part);
        if (event) onEvent(event);
      }
    }
    buffer += decoder.decode();
    const trailing = buffer.trim();
    if (trailing) {
      const event = parseSSEBlock(trailing);
      if (event) onEvent(event);
    }
  } finally {
    clearTimeout(pollTimer);
  }
}

async function _getTurnCount(sessionId: string, signal?: AbortSignal): Promise<number> {
  try {
    const res = await fetch(
      `${BASE}/awp/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`,
      { signal },
    );
    if (!res.ok) return 0;
    const body = await res.json();
    return (body?.data as unknown[])?.length ?? 0;
  } catch {
    return 0;
  }
}

async function _pollForNewTurn(
  sessionId: string,
  previousCount: number,
  signal?: AbortSignal,
): Promise<{ turn_id: string; turn_index: number; writer_output: string } | null> {
  // Poll every 2s for up to 120s
  for (let i = 0; i < 60; i++) {
    if (signal?.aborted) return null;
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const res = await fetch(
        `${BASE}/awp/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`,
        { signal },
      );
      if (!res.ok) continue;
      const body = await res.json();
      const turns = (body?.data as Array<Record<string, unknown>>) ?? [];
      if (turns.length > previousCount) {
        const latest = turns[turns.length - 1];
        return {
          turn_id: String(latest.turn_id ?? ""),
          turn_index: Number(latest.turn_index ?? 0),
          writer_output: String(latest.writer_output ?? ""),
        };
      }
    } catch {
      // ignore and retry
    }
  }
  return null;
}

export async function firstTurn(
  sessionId: string,
  playerInput: string,
  opts?: ExecutionOptions,
): Promise<TurnCommandResult> {
  return post<TurnCommandResult>(
    withExecutionQuery(`/sessions/${encodeURIComponent(sessionId)}/first-turn`, opts),
    { player_input: playerInput },
  );
}

export async function continueSessionV2(
  sessionId: string,
  opts?: ExecutionOptions,
): Promise<TurnCommandResult> {
  return post<TurnCommandResult>(
    withExecutionQuery(`/sessions/${encodeURIComponent(sessionId)}/continue`, opts),
  );
}

export async function importCard(sourcePath: string, greetingId?: string): Promise<ImportCardResult> {
  return post<ImportCardResult>("/cards/import", {
    source_path: sourcePath,
    ...(greetingId ? { greeting_id: greetingId } : {}),
  });
}

export async function uploadCard(file: File, greetingId?: string): Promise<ImportCardResult> {
  const formData = new FormData();
  formData.append("file", file);
  const params = greetingId ? `?greeting_id=${encodeURIComponent(greetingId)}` : "";
  const res = await fetch(`${BASE}/awp/api/v1/cards/upload${params}`, {
    method: "POST",
    body: formData,
  });
  const body = await parseJson<ImportCardResult>(res);
  if (!res.ok) throw new Error(errorMessage(body as ApiEnvelope<{ error?: string }>, res.status));
  return body.data as ImportCardResult;
}

export async function deleteCard(cardId: string): Promise<void> {
  await del<{ success: boolean }>(`/cards/${encodeURIComponent(cardId)}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await del<{ success: boolean }>(`/sessions/${encodeURIComponent(sessionId)}`);
}

export async function listGreetings(cardId: string): Promise<GreetingInfo[]> {
  return get<GreetingInfo[]>(`/cards/${encodeURIComponent(cardId)}/greetings`);
}

export async function createSession(cardId: string, greetingId: string): Promise<CreateSessionResult> {
  return post<CreateSessionResult>("/sessions", {
    card_id: cardId,
    greeting_id: greetingId,
  });
}

export async function listWorkflows(): Promise<WorkflowInfo[]> {
  return get<WorkflowInfo[]>("/workflows");
}

export async function runConsoleCommand(
  command: string,
  sessionId?: string,
): Promise<ConsoleCommandResult> {
  return post<ConsoleCommandResult>("/console/command", {
    command,
    session_id: sessionId || "",
  });
}

export async function listWriterPresets(): Promise<string[]> {
  return get<string[]>("/presets/writer");
}

export async function getWriterPreset(name: string): Promise<WriterPresetInfo> {
  return get<WriterPresetInfo>(`/presets/writer/${encodeURIComponent(name)}`);
}

// ── Novel Mode ──────────────────────────────────────────────────────────

export interface NovelProject {
  project_id: string;
  title: string;
  genre: string;
  target_platform: string;
  target_reader: string;
  core_emotion: string;
  one_sentence_pitch: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface NovelCharacter {
  character_id: string;
  project_id: string;
  name: string;
  role: string;
  personality: string;
  core_motivation: string;
  current_state: Record<string, unknown>;
}

export interface NovelChapterPlan {
  chapter_id: string;
  chapter_index: number;
  title: string;
  target_chars: number;
  target_emotion: string;
  scene_beats: Array<{
    beat_id: string;
    description: string;
    function_tag: string;
    density: string;
    budget_chars: number;
  }>;
  ending_design: {
    hook_type: string;
    hook_detail: string;
    hook_strength: string;
  };
}

export interface NovelDraft {
  draft_id: string;
  chapter_id: string;
  revision: number;
  text: string;
  char_count: number;
  status: string;
}

export interface NovelLedgerItem {
  item_id: string;
  section: string;
  entity: string;
  content: string;
  status: string;
  source_chapter: number;
}

export interface NovelPlanResult {
  title: string;
  genre: string;
  one_sentence_pitch: string;
  core_outline: { surface: string; inner: string; one_sentence: string };
  world_setting: Record<string, unknown>;
  characters: Array<{ name: string; role: string; core_trait: string; motivation: string }>;
  volumes: Array<{ volume_index: number; title: string; objective: string; key_results: string[] }>;
  first_volume_chapters: Array<{ chapter_index: number; objective: string; key_results: string[]; hook_type: string }>;
  tags: string[];
}

export async function listNovelProjects(): Promise<NovelProject[]> {
  return get<NovelProject[]>("/novels");
}

export async function getNovelProject(projectId: string): Promise<NovelProject> {
  return get<NovelProject>(`/novels/${encodeURIComponent(projectId)}`);
}

export async function deleteNovelProject(projectId: string): Promise<void> {
  await del<{ success: boolean }>(`/novels/${encodeURIComponent(projectId)}`);
}

export async function planNovelFromConcept(params: {
  concept: string;
  title?: string;
  genre?: string;
  target_platform?: string;
  additional_requirements?: string;
}): Promise<NovelPlanResult> {
  return post<NovelPlanResult>("/novels/plan", params);
}

export async function listNovelCharacters(projectId: string): Promise<NovelCharacter[]> {
  return get<NovelCharacter[]>(`/novels/${encodeURIComponent(projectId)}/characters`);
}

export async function listNovelChapterPlans(projectId: string): Promise<NovelChapterPlan[]> {
  return get<NovelChapterPlan[]>(`/novels/${encodeURIComponent(projectId)}/chapters`);
}

export async function planNovelChapter(projectId: string, chapterIndex: number, taskDescription?: string): Promise<NovelChapterPlan> {
  return post<NovelChapterPlan>(`/novels/${encodeURIComponent(projectId)}/chapters/plan`, {
    chapter_index: chapterIndex,
    task_description: taskDescription || "",
  });
}

export async function writeNovelChapter(projectId: string, chapterIndex: number): Promise<NovelDraft> {
  return post<NovelDraft>(`/novels/${encodeURIComponent(projectId)}/chapters/${chapterIndex}/write`);
}

export async function getNovelDrafts(projectId: string, chapterIndex: number): Promise<NovelDraft[]> {
  return get<NovelDraft[]>(`/novels/${encodeURIComponent(projectId)}/chapters/${chapterIndex}/drafts`);
}

export async function batchWriteNovel(projectId: string, chapterStart: number, chapterEnd: number): Promise<{ status: string }> {
  return post<{ status: string }>(`/novels/${encodeURIComponent(projectId)}/batch-write`, {
    chapter_start: chapterStart,
    chapter_end: chapterEnd,
  });
}

export async function listNovelLedger(projectId: string): Promise<NovelLedgerItem[]> {
  return get<NovelLedgerItem[]>(`/novels/${encodeURIComponent(projectId)}/ledger`);
}
