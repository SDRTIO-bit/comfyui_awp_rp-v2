# 管线流式观察窗（Pipeline Stream Drawer）设计

> **交付对象**：codex 照此实现。本 spec 已锁定方案 A（引擎进度回调 + SSE 流式 + 前端 Drawer）。
> 配套实现计划将由 writing-plans 生成。

## 1. 目标

让玩家在管理面板发送回合后，**生成过程中**实时看到 AI 管线各步骤的中间产物逐块出现，既作监控也作等待时的消遣读物。不是事后回放，是真·生成中实时。

## 2. 范围与约束

- **仅 python 轨**：管理面板聊天只走 `ExecutionDispatcher` 的 python 直调路径。hybrid 轨（ComfyUI 队列）不实现流式，仅保留给"在 ComfyUI 画布里手动跑工作流"的调试场景。本特性不触碰 hybrid 轨。
- **数据粒度**：按管线步骤分块，9 步 9 块，每块显示该步骤的可观察摘要。
- **触发**：玩家点发送后，左侧弹窗自动弹出，各块随生成进度逐块出现。
- **不破坏现有契约**：`PersistentTurnEngine.execute` 的同步返回值（851+ 测试依赖）保持不变；流式能力通过新增的可选参数注入，不改变默认行为。

## 3. 管线步骤清单

引擎 `PersistentTurnEngine.execute` 的 9 个步骤，顺序固定：

| 序 | step_name | 中文 | 现有 `_record_step`/`steps_completed` 名 |
|---|---|---|---|
| 1 | `round_snapshot` | 回合快照 | `round_snapshot` |
| 2 | `director` | 总控规划 | `director` |
| 3 | `director_delegation` | 总控委派 | `director_delegation` |
| 4 | `sub_agents` | 子代理分析 | `agents:<names>`（流式统一用 `sub_agents`） |
| 5 | `writer` | 写作 | `writer` |
| 6 | `quality_gate` | 质量门 | `quality_gate` |
| 7 | `turn_evolution_curator` | 演进策展 | `turn_evolution_curator` |
| 8 | `state_commit` | 状态提交 | `state_commit` |
| 9 | `memory_curator` | 记忆治理 | `memory_curator` |

> 注：`director_tools` 是 director 段内的可选子步骤，流式不单独成块（并入 director 块的 payload）。

## 4. 引擎进度回调接口

### 4.1 新增参数

`PersistentTurnEngine.execute` 签名新增可选参数（位置：所有现有参数之后，`turn_kind` 之前或之后均可，实现时放最末尾以兼容现有调用）：

```python
on_step: Callable[[str, dict[str, Any]], None] | None = None
```

`on_step(step_name: str, payload: dict)` 在每个步骤完成时被调用，`step_name` 取 §3 第 1 列的统一流式名，`payload` 见 §4.2。回调内抛异常不影响引擎主流程（引擎侧 try/except 包裹，失败则跳过该次回调）。

### 4.2 各步骤 payload

payload 只给摘要和 ID，**不给原始大文本**（writer 正文除外，见 §4.3），与项目"diagnostics 只存 ID 不存 raw content"的安全约定一致。各字段从引擎现有局部变量/diag 对象读取（实现时在对应 `_record_step` 调用点旁边构造 payload 并触发回调）。

每个 payload **统一带一个 `duration_ms` 字段**，值 = `diag.step_timings_ms[step_name]`（由 `_record_step` 刚写入）。`round_snapshot`/`director_delegation`/`sub_agents` 这几步若不在 `step_timings_ms` 里（见 §3 注），`duration_ms` 取 0 或就近的上一步值——实现时若无对应 key 则填 0。

**1. round_snapshot**
```json
{"l1_turn_ids_recalled_count": 3, "l2_memory_ids_recalled_count": 2,
 "l3_memory_ids_recalled_count": 0, "worldbook_activated_count": 5,
 "snapshot_id": "s001"}
```

**2. director**
```json
{"provider_type": "fake|deepseek", "model": "...", "plan_ref": "...",
 "call_success": true, "failure_code": ""}
```
失败时 `call_success=false` 且 `failure_code` 非空，引擎随后会提前 return（见 §7）。

**3. director_delegation**
```json
{"source": "director_request|trigger_policy_fallback", "requested_agents": ["d1_history_recall","d2_opportunity"]}
```

**4. sub_agents**
```json
{"agent_dispositions": {"d1_history_recall":"召回上轮情绪线索", "d2_opportunity":"发现推进机会"},
 "trigger_diagnostics": [{"agent":"d1_history_recall","should_trigger":true}],
 "parallelism": 0}
```
无触发时 `agent_dispositions = {"_none_triggered":"no sub-agents fired this turn"}`（复用引擎已有的回填逻辑）。

**5. writer**
```json
{"provider_type": "...", "model": "...", "call_success": true,
 "text_length": 1234, "text_hash": "sha256前16位", "failure_code": ""}
```
**不包含 `writer_output` 正文**——正文通过单独的 `writer_text` SSE 事件在 quality 通过后回填（§4.3）。

**6. quality_gate**
```json
{"verdict": "pass|block", "blocking_reasons": [], "overall_score": 0.85}
```

**7. turn_evolution_curator**
```json
{"proposed_state_changes_count": 2, "memory_candidates_active_count": 1,
 "memory_candidates_rag_count": 1, "curator_confidence": 0.7}
```

**8. state_commit**
```json
{"commit_status": "committed", "revision_before": 3, "revision_after": 4}
```

**9. memory_curator**
```json
{"curation_status": "curated_rag", "curation_reason": "rag_committed:1",
 "commit_ids_count": 1, "active_committed_count": 0, "rag_committed_count": 1}
```

### 4.3 writer 正文的延迟回填

writer 块在步骤 5 完成时只显示"正在写作…" + text_length 占位。当步骤 6 quality_gate verdict=pass 后，引擎继续走修订/提交流程，最终正文（可能是 Reviser 修订稿）通过 **单独的 `writer_text` SSE 事件** 推送，前端回填到 writer 块。

- quality 通过：引擎在确定最终正文后（state_commit 之前或 turn_commit 时）触发一次 `writer_text` 事件，携带最终 `writer_output`。
- quality 拒绝（Reviser 修订后仍不通过）：**不触发 `writer_text`**，writer 块保持"初稿被拒"状态，最终 `done(success=false)`。

> 实现提示：最终正文 = `turn_record.writer_output`。引擎在 `turn_commit` 步骤后、return 前，若 `diag.outcome == "success"`，触发 `writer_text` 事件。

## 5. 执行调度层

### 5.1 ExecutionDispatcher 新增方法

`runtime/execution_dispatcher.py` 的 `ExecutionDispatcher` 新增：

```python
def execute_turn_streaming(
    self, session_id: str, player_input: str,
    on_started: Callable[[list[str]], None] | None,
    on_step: Callable[[str, dict], None] | None,
    on_writer_text: Callable[[str], None] | None,
    on_done: Callable[[dict], None] | None,
) -> dict:
    """流式玩家回合。调用顺序：on_started → (on_step ×N) → on_writer_text? → on_done。"""
```

内部：
1. 若 `on_started`：调 `on_started(STEP_NAMES)`（§3 的 9 个名字列表）
2. 调 `AWPV2PersistentContinuationTurn().execute(..., on_step=on_step, on_writer_text=on_writer_text)`，节点透传给 `PersistentTurnEngine.execute`
3. 引擎返回后从 result 提取 success/turn_id/turn_index/error，调 `on_done({...})`，并返回结果 dict

> **关键**：`AWPV2PersistentContinuationTurn` 节点也要透传 `on_step`/`on_writer_text` 参数到 `PersistentTurnEngine.execute`（节点 execute 签名加同名可选参数）。dispatcher 不直接调引擎，而是调节点——保持与现有 `_python_turn` 一致的调用层级。

### 5.2 writer_text 触发点（引擎侧）

引擎 `execute` 签名因此新增两个可选参数：

```python
on_step: Callable[[str, dict[str, Any]], None] | None = None,
on_writer_text: Callable[[str], None] | None = None,
```

在引擎 `execute` 的**成功 return 之前**（即 `turn_commit` 之后、return tuple 之前），插入：

```python
if on_writer_text is not None and diag.outcome == "success":
    try:
        on_writer_text(turn_record.writer_output)
    except Exception:
        pass
```

> `turn_record.writer_output` 是经 quality 通过（含 Reviser 修订）后的最终正文。失败/拒绝路径不触发。dispatcher 把 `on_writer_text` 透传给节点透传给引擎。

## 6. SSE 端点

### 6.1 端点定义

`runtime/management_api.py` 新增：

```
POST /awp/api/v1/sessions/{session_id}/turn/stream
Content-Type: application/json  (请求体: {"player_input": "..."})
响应: text/event-stream
```

原有的同步 `POST /awp/api/v1/sessions/{session_id}/turn` **保留不动**（测试和非流式场景仍用）。

### 6.2 SSE 事件协议

每条事件格式：`event: <type>\ndata: <json>\n\n`。事件类型按顺序：

| event | data | 时机 |
|---|---|---|
| `started` | `{"turn_id":"...","steps":[9个名字]}` | 引擎开始前 |
| `step` | `{"step":"director","payload":{...},"duration_ms":12}` | 每个步骤完成 |
| `writer_text` | `{"turn_id":"...","writer_output":"最终正文"}` | quality 通过后（见 §4.3） |
| `done` | `{"success":true,"turn_id":"...","turn_index":2}` 或 `{"success":false,"error":"...","failure_code":"..."}` | 引擎结束 |

- `step` 事件的 `duration_ms` 从 `diag.step_timings_ms[step]` 取（复用 §4 已有数据）。
- 失败时（director/writer 失败或 quality 拒绝）：先推已完成的 `step` 事件，再推 `done(success=false)`，不推后续步骤也不推 `writer_text`。

### 6.3 执行模型（线程化 + asyncio.Queue）

端点 handler（async）流程：

1. 解析 `player_input`，校验非空
2. 创建 `queue: asyncio.Queue`、获取当前 `loop = asyncio.get_running_loop()`
3. 定义线程侧回调：
   ```python
   def _on_started(steps): loop.call_soon_threadsafe(queue.put_nowait, ("started", {"turn_id":..., "steps":steps}))
   def _on_step(name, payload): loop.call_soon_threadsafe(queue.put_nowait, ("step", {"step":name, "payload":payload, "duration_ms":payload.get("duration_ms", 0)}))
   def _on_writer_text(text): loop.call_soon_threadsafe(queue.put_nowait, ("writer_text", {"turn_id":..., "writer_output":text}))
   def _on_done(result): loop.call_soon_threadsafe(queue.put_nowait, ("done", result))
   ```
4. `loop.run_in_executor(None, functools.partial(dispatcher.execute_turn_streaming, session_id, player_input, _on_started, _on_step, _on_writer_text, _on_done))` 提交到线程池
5. `async for item in queue:` 取事件，按类型格式化为 SSE 文本 `yield`；收到 `done` 事件后 break
6. 超时保护：`asyncio.wait_for(queue.get(), timeout=180)` 循环，超时则 yield `done(success=false, error="timeout")` 并 break

> 注：`run_in_executor` 的参数传递限制——`execute_turn_streaming` 有多个回调参数，用 `functools.partial(dispatcher.execute_turn_streaming, session_id, player_input, on_step=..., on_writer_text=..., on_done=..., on_started=...)` 包装后提交。

aiohttp 的 SSE 响应用 `web.StreamResponse(content_type="text/event-stream")`，每条 `await response.write(f"event: {type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8"))`。

## 7. 失败与边界处理

- **director 失败**：引擎在 director 步骤失败时提前 return。流式端点已推送 `step(director, success=false)`，随后推 `done(success=false, error="DIRECTOR_...")`。前端 director 块标红，后续块保持 pending（灰色）。
- **writer 失败**：同上，writer 块标红，无 `writer_text`。
- **quality 拒绝**：`step(quality_gate, verdict=block)` 后引擎走 Reviser 修订重试；若仍拒绝，`done(success=false)`。前端 quality 块显示拒绝理由。仍无 `writer_text`。
- **超时**：180s 总超时，推 `done(success=false, error="timeout")`。注意 `run_in_executor` 的线程无法真正取消（Python 线程不可强制终止），引擎会在后台继续跑完但结果丢弃——可接受。
- **客户端断连**：aiohttp 检测到连接关闭时 handler 退出 `async for`，线程继续跑完丢弃结果。
- **player_input 为空**：直接返回 400（不发 SSE）。

## 8. 前端

### 8.1 API client

`web/src/api/client.ts` 新增：

```typescript
export interface StepPayload { [key: string]: any }
export interface StreamEvent {
  type: "started" | "step" | "writer_text" | "done";
  // started: { turn_id, steps }
  // step: { step, payload, duration_ms }
  // writer_text: { turn_id, writer_output }
  // done: { success, turn_id?, turn_index?, error?, failure_code? }
}

export async function sendTurnStream(
  sessionId: string,
  playerInput: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/awp/api/v1/sessions/${encodeURIComponent(sessionId)}/turn/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player_input: playerInput }),
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  // 用 ReadableStream 解析 text/event-stream
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // 按双换行分割事件块
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const event = parseSSEBlock(part);
      if (event) onEvent(event);
    }
  }
}
```

`parseSSEBlock` 解析 `event:` 和 `data:` 两行。具体实现见计划。

### 8.2 PipelineStreamDrawer 组件

新建 `web/src/components/PipelineStreamDrawer.tsx`：

- Props: `{ open: boolean, onClose: () => void, sessionId: string, playerInput: string, onComplete: () => void }`
- 内部 state: `steps: Array<{name, label, status: "pending"|"done"|"failed", payload?, duration_ms?, writerOutput?}>`
- `useEffect` 监听 `open`：为 true 时调 `sendTurnStream`，`onEvent` 按 type 更新 state
- `started` → 初始化 9 个 pending 块（label 用 §3 中文）
- `step` → 找到对应 name 的块，置 done + 填 payload + duration_ms
- `writer_text` → 找到 writer 块填 writerOutput
- `done` → success=false 时把最后处理的块标 failed；success=true 时调 `onComplete()`（父组件刷新回合列表）

### 8.3 各块渲染（按 step name 分发）

Drawer 内每个块用 Antd `Card`（size=small），顶部：中文 label + 状态图标（⏳ pending / ✓ done / ✗ failed）+ duration_ms。body 按 name 分发：

| name | 渲染 |
|---|---|
| round_snapshot | `召回 L1:3 L2:2 L3:0 | worldbook:5` |
| director | 模型名 + plan_ref（截断）+ 成功徽标 |
| director_delegation | source + requested_agents 标签列表 |
| sub_agents | `agent_dispositions` 用 `Collapse` 列每个 role→summary |
| writer | 无 writerOutput 时"正在写作…（{text_length} 字）"；有则显示正文（限高 200px 滚动）|
| quality_gate | verdict 徽标（pass 绿/block 红）+ overall_score + blocking_reasons |
| turn_evolution_curator | 各 count + confidence |
| state_commit | commit_status + revision before→after |
| memory_curator | curation_status + curation_reason + 各 committed count |

### 8.4 SessionChat 改造

`web/src/pages/SessionChat.tsx`：
- 新增 state: `drawerOpen`, `drawerInput`
- `handleSend` 改为：set `drawerInput = inputText`、`drawerOpen = true`、`inputText = ""`（不在 handleSend 里直接调 API，由 Drawer 内部驱动流式）
- Drawer `onComplete` → `load()` 刷新回合列表
- Drawer `onClose` → `drawerOpen = false`
- JSX 末尾加 `<PipelineStreamDrawer open={drawerOpen} ... />`

## 9. 测试要求

- **引擎回调**：`tests/test_pipeline_stream_engine.py`——mock 引擎跑一次，断言 `on_step` 被 9 步依次调用、payload 字段齐全；quality 拒绝路径断言无 `on_writer_text`；director 失败路径断言提前停止。
- **dispatcher 流式**：`tests/test_execution_dispatcher_streaming.py`——断言 `execute_turn_streaming` 按序调 on_started/on_step/on_writer_text/on_done。
- **SSE 端点**：`tests/test_turn_stream_endpoint.py`——用 aiohttp test client 或直接调 handler，断言事件序列正确、失败路径事件齐全、player_input 空返回 400。
- **前端**：类型检查 `npx tsc --noEmit` + `npm run build` 通过。
- **全量回归**：`python -m pytest tests/ -q` 无新增失败（关键：851+ 引擎测试不受 on_step 可选参数影响）。

## 10. 文件清单

### 新建
- `web/src/components/PipelineStreamDrawer.tsx`
- `tests/test_pipeline_stream_engine.py`
- `tests/test_execution_dispatcher_streaming.py`
- `tests/test_turn_stream_endpoint.py`

### 修改
- `runtime/persistent_turn_engine.py` — `execute` 加 `on_step`/`on_writer_text` 参数 + 9 处回调触发 + 末尾 writer_text 触发
- `nodes/persistent_continuation_turn_node.py` — `execute` 透传 `on_step`/`on_writer_text`
- `runtime/execution_dispatcher.py` — 加 `execute_turn_streaming`
- `runtime/management_api.py` — 加 `/turn/stream` SSE 端点
- `web/src/api/client.ts` — 加 `sendTurnStream` + 类型
- `web/src/pages/SessionChat.tsx` — 接入 Drawer

## 11. 不在本期范围

- hybrid 轨流式（ComfyUI 队列不支持中间产物推送，本期不做）
- 历史回合的管线数据回看（本特性只覆盖"当前正在生成的回合"；历史回合的 diag 已落库，未来可加"查看历史回合管线"端点）
- 流式首回合（`/first-turn/stream`）和流式续写（`/continue/stream`）——本期只做玩家回合 `turn/stream`，结构相同可后续复制

## 12. 实现前必读的代码确认点

codex 实现时需先读代码确认（非占位符）：
1. `PersistentTurnEngine.execute` 的完整签名和 return tuple 结构（`runtime/persistent_turn_engine.py:374`）
2. `AWPV2PersistentContinuationTurn.execute` 的签名和它如何调引擎（`nodes/persistent_continuation_turn_node.py`）
3. `management_api.py` 现有路由的 `_json`/`_factory` 辅助和 aiohttp StreamResponse 用法
4. 各步骤 payload 字段在引擎局部变量/diag 里的实际变量名（§4.2 的字段是从哪里读的）
5. writer 最终正文在 return 前的变量名（`turn_record.writer_output`）
