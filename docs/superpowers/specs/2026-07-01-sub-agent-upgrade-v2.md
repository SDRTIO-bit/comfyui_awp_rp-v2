# 子 Agent 升级 V2 — 从上下文拼接器到真 Agent

**日期：** 2026-07-01
**范围：** Director（一号主 Agent）+ D1-D5 子 Agent
**不动：** Writer（二号主 Agent）、存储层、节点层

---

## 1. 背景与动机

### 1.1 原始设计（架构文档 v0.1）

子 Agent 的定位是"创意变量"：

> 子 Agent 的价值不仅是找错，更是提供主 Writer 原本没有想到的角度。它们让叙事从"模型按当前输入线性续写"变成"世界会回忆、会联想、会暗自酝酿"。

每个子 Agent 有明确职责：

| 子 Agent | 核心问题 | 典型产出 |
|----------|---------|---------|
| History/Recall | 有没有被遗忘但值得呼应的旧剧情？ | 旧承诺、旧物件、旧对话的回收建议 |
| Opportunity | 当前局面有什么意外但合理的推进？ | 1–3 张剧情机会卡 |
| World-Life | 世界在主角视线之外可能发生什么？ | 不强制发生的环境变化候选 |
| Emotion/Relationship | 人物是否太理性、太平、缺少暗流？ | 动作、停顿、误会、克制等建议 |
| Continuity | 人物位置、知识边界、时间线是否冲突？ | 可证据化的问题列表 |

### 1.2 升级前的问题

**问题 1：子 Agent 是上下文拼接器，不是 Agent**

引擎预拼所有数据塞进 prompt，子 Agent 做纯文本生成，没有工具调用能力。

**问题 2：Director 给子 Agent 的指令是硬编码的通用文本**

```python
purpose="Check recent history for consistency and unresolved threads"
purpose="Find dramatic opportunities grounded in established facts"
```

没有包含 Director 的具体计划（turn_goal、scene_focus、risk_flags）。

**问题 3：子 Agent 输出是自由分析文本，不是结构化建议**

```
[opportunity] The player's turn shows a guarded, self-deprecating deflection
of care, which creates subtle emotional tension with 语晴's earnest desire
to nurture him...
```

Writer 看到的是一段分析报告，不是具体可操作的建议。

**问题 4：token 消耗过高**

全量世界书（40 条，108KB）塞给每个子 Agent，每轮 flash 缓存未命中 ~500K tokens。

---

## 2. 改动清单

### 2.1 子 Agent 升级为真 Agent（`runtime/sub_agent_llm_runner.py`）

**改动前：**
```python
def run_sub_agent_llm(role, snapshot, adapter, ...):
    prompt = _build_prompt(role, snapshot)  # 预拼所有数据
    text, receipt = adapter.generate_text(prompt, ...)  # 单次 LLM 调用
    return text
```

**改动后：**
```python
def run_sub_agent_llm(role, snapshot, adapter, ..., allowlist=None):
    # 1. 预塞最相关数据（精简版）
    pre_results = _pre_populate_tools(role, snapshot)

    # 2. 给 LLM 工具定义，让它自己决定查什么
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content + pre_results}]

    # 3. Agent 循环：调工具 → 拿结果 → 写建议（最多 2 轮）
    for round_idx in range(_MAX_TOOL_ROUNDS):
        message, usage = adapter.call_with_tools(messages, tools, ...)
        if message.tool_calls:
            # 执行工具，追加结果，继续
        else:
            # 没有工具调用，产出最终建议
            break
    return final_text
```

**新增工具：**

| 工具 | 作用 | 参数 |
|------|------|------|
| `accepted_turn_lookup` | 读最近回合 | `limit` |
| `active_memory_lookup` | 读活跃记忆 | 无 |
| `memory_rag_lookup` | 关键词搜索记忆 | `query` |
| `worldbook_lookup` | 读世界书条目 | `keyword`（可选） |
| `scene_context_lookup` | 读场景上下文 | 无 |
| `character_profile_lookup` | 读角色资料 | 无 |
| `relationship_context_lookup` | 读关系线索 | 无 |

**每个角色有默认工具集：**

```python
_ROLE_DEFAULT_TOOLS = {
    "history_recall": ["accepted_turn_lookup", "active_memory_lookup", "memory_rag_lookup", "scene_context_lookup"],
    "opportunity": ["accepted_turn_lookup", "active_memory_lookup", "memory_rag_lookup", "worldbook_lookup", "scene_context_lookup"],
    "world_life": ["worldbook_lookup", "scene_context_lookup"],
    "emotion_relationship": ["accepted_turn_lookup", "active_memory_lookup", "scene_context_lookup", "relationship_context_lookup"],
    "continuity": ["accepted_turn_lookup", "active_memory_lookup", "memory_rag_lookup", "worldbook_lookup", "scene_context_lookup"],
}
```

**预查数据（`_pre_populate_tools`）：**

每个角色预塞 1-2 个最相关工具的精简结果，减少 LLM 调用次数：

```python
_ROLE_PRELOAD = {
    "history_recall": [("accepted_turn_lookup", {"limit": 3}), ("active_memory_lookup", {})],
    "opportunity": [("scene_context_lookup", {}), ("active_memory_lookup", {})],
    "world_life": [("scene_context_lookup", {}), ("worldbook_lookup", {})],
    "emotion_relationship": [("active_memory_lookup", {}), ("accepted_turn_lookup", {"limit": 2})],
    "continuity": [("accepted_turn_lookup", {"limit": 3})],
}
```

预查数据使用精简版（`_execute_tool_compact`）：writer_output 截断 150 字，worldbook 条目截断 200 字。

**世界书 RAG 检索（`_worldbook_rag`）：**

从玩家输入提取关键词，按关键词重叠度对世界书条目打分，返回 top 5：

```python
def _worldbook_rag(player_input, snapshot, top_k=5):
    keywords = _extract_keywords(player_input)
    # 为每条世界书计算关键词重叠分数
    scored = [(score, entry) for entry in worldbook if score > 0]
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]
```

### 2.2 Director 给子 Agent 下具体指令（`adapters/llm/real_director_adapter.py`）

**改动前：**
```python
purpose="Check recent history for consistency and unresolved threads"
```

**改动后：**
```python
purpose=(
    f"Check recent history for this turn. "
    f"Director's goal: {plan.turn_goal}. "
    f"Risks to verify: {'; '.join(plan.risk_flags[:3]) if plan.risk_flags else 'none'}. "
    f"Look for contradictions with established facts, unresolved threads, and callbacks."
)
```

每个角色的 purpose 都包含 Director 的具体计划：
- `turn_goal`：这轮要达到什么目的
- `scene_focus`：聚焦什么场景元素
- `narrative_opportunities`：具体的机会点
- `risk_flags`：具体的风险
- `relationship_tensions`：关系张力

### 2.3 子 Agent 输出格式改造（`runtime/sub_agent_llm_runner.py`）

**改动前（自由分析文本）：**
```
[opportunity] **Summary:** The player's turn shows a guarded deflection...
**Key Evidence:** 1) In Turn 1, 语晴 offered to buy 蛤蜊油...
**Confidence:** high
```

**改动后（结构化建议）：**
```
[SUGGESTION_1]
kind: callback
suggestion: Have 周语晴 mention the 蛤蜊油 she promised to buy, showing she remembers.
evidence: Turn 1: she offered to buy it for his chapped hands.
[/SUGGESTION_1]

[SUGGESTION_2]
kind: emotion
suggestion: When she hears the word 检查, her hand drifts to her belly unconsciously.
evidence: memory: she bought a pregnancy test last month, was disappointed.
[/SUGGESTION_2]
```

**kind 类型：**

| kind | 对应 SuggestionKind | 优先级权重 |
|------|-------------------|-----------|
| `callback` | HISTORICAL_CONFLICT | 0.98 |
| `opportunity` | NARRATIVE_OPPORTUNITY | 0.6 |
| `world_event` | WORLD_DETAIL | 0.65 |
| `emotion` | EMOTION_CUE | 0.55 |
| `continuity_issue` | CONTINUITY_ISSUE | 1.0 |

**解析器（`parse_sub_agent_output`）：**

```python
def parse_sub_agent_output(text: str) -> list[dict[str, str]]:
    # 1. 尝试解析 [SUGGESTION_N]...[/SUGGESTION_N] 结构
    # 2. 尝试行内解析（无闭合标签）
    # 3. Fallback：整段文本作为单条建议，自动猜测 kind
```

Fallback 逻辑：
- 包含 "contradiction/conflict/mismatch" → `continuity_issue`
- 包含 "callback/recall/promise" → `callback`
- 包含 "emotion/feel/tension" → `emotion`
- 包含 "world/environment/npc" → `world_event`
- 其他 → `opportunity`

### 2.4 引擎解析层（`runtime/persistent_turn_engine.py`）

**新增方法 `_apply_sub_agent_output`：**

```python
def _apply_sub_agent_output(self, sug, role, llm_text):
    parsed = parse_sub_agent_output(llm_text)
    if not parsed:
        sug.summary = f"[{role}] {llm_text[:300]}"
        return

    first = parsed[0]
    sug.summary = f"[{role}] {first['suggestion']}"
    sug.kind = SuggestionKind[mapped_kind]  # 按 kind 映射
    sug.recommendations = [p['suggestion'] for p in parsed]
    sug.evidence = [p['evidence'] for p in parsed if p['evidence']]
```

**调用位置：**

```python
# persistent_turn_engine.py, _run_one 回调中
for future in as_completed(futures):
    sug, role, llm_text = future.result()
    if llm_text:
        self._apply_sub_agent_output(sug, role, llm_text)
```

### 2.5 DeepSeekAdapter 新增 `call_with_tools` 方法（`adapters/llm/deepseek_adapter.py`）

```python
def call_with_tools(self, messages, tools, model="", max_tokens=500,
                    temperature=0.3, extra_body=None):
    """Single tool-calling turn. Returns the raw message object.
    The caller is responsible for the agentic loop."""
    resp = self._client.chat.completions.create(
        model=model, messages=messages, tools=tools,
        tool_choice="auto", max_tokens=max_tokens, temperature=temperature,
    )
    message = resp.choices[0].message
    usage = ...
    return message, usage
```

### 2.6 allowlist 过滤（`runtime/sub_agent_llm_runner.py` + `runtime/persistent_turn_engine.py`）

**子 Agent runner：** `_build_tool_result_block` 支持 `allowlist` 参数，只塞 Director 指定的工具结果。

**引擎：** `_run_one` 从 delegation_plan 的 tasks 中查找对应 role 的 `input_field_allowlist`，传给 `run_sub_agent_llm`。

**allowlist 调整：**

| 子 Agent | 旧 allowlist | 新 allowlist |
|----------|-------------|-------------|
| history_recall | 含 `active_worldbook_entries` | **去掉**——靠 RAG 查记忆 |
| emotion_relationship | 含 `active_worldbook_entries` | **去掉**——靠记忆和近忆 |
| opportunity | 含 `active_worldbook_entries` | 保留 |
| world_life | 含 `active_worldbook_entries` | 保留 |
| continuity | 含 `active_worldbook_entries` | 保留 |

---

## 3. 数据流对比

### 升级前

```
玩家输入
  ↓
RoundSnapshot（全量世界书 + 近 5 回合 + 记忆）
  ↓
Director（读全部）→ 硬编码 purpose → 子 Agent
  ↓
子 Agent：预拼全量数据 → 单次 LLM → 自由文本
  ↓
引擎：sug.summary = "[role] text"
  ↓
SuggestionMerger：kind/evidence 全是默认值，过滤无效
  ↓
Writer：看到分析报告
```

### 升级后

```
玩家输入
  ↓
RoundSnapshot（全量世界书 + 近 5 回合 + 记忆）
  ↓
Director（读全部）→ 具体 purpose（含 turn_goal/risk_flags）
  ↓
子 Agent：预塞精简数据 + 工具定义 → Agent 循环（调工具 → 写建议）
  ↓
引擎：parse → sug.kind + recommendations + evidence
  ↓
SuggestionMerger：按 kind 优先级排序，过滤高风险无证据
  ↓
Writer：看到具体建议（recommendations[:2]）
```

---

## 4. token 消耗对比

| | 升级前 | 升级后 |
|---|--------|--------|
| 子 Agent 调用方式 | 单次 LLM（拼接器） | 1-2 次 LLM（真 Agent） |
| 每个子 Agent 输入 | ~25K tokens（全量数据） | ~8K tokens（精简预查 + 工具定义） |
| 子 Agent 总调用/轮 | 3 次 | 3-6 次（多了一轮工具调用） |
| 子 Agent 总 tokens/轮 | ~75K | ~40K |
| Director | ~29K | ~29K（不变） |
| **每轮合计** | **~104K** | **~69K** |

子 Agent 调用次数增加，但每次输入大幅减少，总 token 降低 ~35%。

---

## 5. 不改的部分

| 组件 | 说明 |
|------|------|
| Writer（二号主 Agent） | 不动。仍然读 WriterInputBundle，仍然生成正文。 |
| AgentSuggestion 合约 | 已有 `kind`、`recommendations`、`evidence` 字段，只是之前没填。 |
| SuggestionMerger | 已有 kind 优先级、mustNotDo 检查、高风险过滤，现在能真正生效。 |
| WriterInputBundleV2Builder | 已有 `recommendations[:2]` 提取，现在能提取到内容。 |
| PromptAssembler | 已有 `accepted_guidance` 格式化，不需要改。 |
| RoundSnapshot | rag_recall 和 active_memories 已在 snapshot 里，子 Agent 通过工具读取。 |
| 存储层 | 不动。 |
| 节点层 | 不动。 |
| 世界书 resolver | 不动。constant/selective/condition 三种激活方式不变。 |

---

## 6. 测试

### 6.1 单元测试

**`tests/runtime/test_sub_agent_llm_runner.py`**（6 个测试）：
- `test_character_profile_lookup_returns_profile`
- `test_accepted_turn_lookup_returns_chronological_history`
- `test_accepted_turn_lookup_respects_limit`
- `test_scene_context_lookup_returns_scene`
- `test_worldbook_lookup_filters_by_keyword`
- `test_active_memory_lookup_returns_memories`

**`tests/test_p1_real_evolution.py`**（适配改动）：
- `test_22c_sub_agent_tools_return_expected_data`（原 `test_22c` 改为测试工具执行）
- `test_22c1_sub_agent_prompt_preserves_latest_five_full_context`（改为测试工具返回完整上下文）
- `test_22d_sub_agent_llm_disables_thinking_mode`（适配 MockAdapter）

### 6.2 全量测试

1063 passed, 1 skipped。

---

## 7. 验收要点

### 7.1 功能验收

- [ ] 子 Agent 能调用工具（看 SSE 中 `sub_agents` 事件的 `agent_dispositions`）
- [ ] 子 Agent 输出包含结构化建议（`kind`/`suggestion`/`evidence`）
- [ ] Director 给子 Agent 的 purpose 包含具体计划（`turn_goal`/`risk_flags`）
- [ ] Writer 看到的 `accepted_guidance` 是具体建议，不是分析报告
- [ ] `memory_rag_lookup` 工具能搜索记忆
- [ ] `worldbook_lookup` 的 RAG 检索返回相关条目

### 7.2 性能验收

- [ ] 每轮 flash 调用次数 ≤ 8（1 director + 3-6 子 Agent）
- [ ] 每轮 flash 缓存未命中 < 200K tokens

### 7.3 质量验收

- [ ] history_recall 产出 `callback` 类型建议（回收旧线索）
- [ ] opportunity 产出 `opportunity` 类型建议（剧情机会卡）
- [ ] world_life 产出 `world_event` 类型建议（世界在动）
- [ ] emotion_rel 产出 `emotion` 类型建议（微动作/潜台词）
- [ ] continuity 产出 `continuity_issue` 类型建议（矛盾报告）
- [ ] 建议是具体的、可操作的，不是泛泛的分析

---

## 8. 已知限制

1. **world_life 的 scene_context 经常为空**——CardState 的 `scene_state` 在 bootstrap 时没有被初始化。需要后续在 Writer 输出后更新 scene_state。

2. **continuity 经常没产出**——因为当前场景矛盾较少，它找不到问题。这是正常的。

3. **解析器 fallback**——如果 LLM 不按格式输出，会降级为单条建议。长期来看需要优化 prompt 让 LLM 更稳定地输出结构化格式。

4. **worldbook RAG 是关键词匹配**——不是向量检索。`_extract_keywords` 对中文分词较简单（按标点分割），可能漏掉语义相关的条目。

---

## 9. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `runtime/sub_agent_llm_runner.py` | 重写 | 真 Agent 循环、工具定义、RAG 工具、输出解析器 |
| `runtime/persistent_turn_engine.py` | 小改 | 新增 `_apply_sub_agent_output`，`_run_one` 传 allowlist |
| `adapters/llm/real_director_adapter.py` | 小改 | purpose 包含 Director 计划，allowlist 调整 |
| `adapters/llm/deepseek_adapter.py` | 小改 | 新增 `call_with_tools` 方法 |
| `tests/runtime/test_sub_agent_llm_runner.py` | 重写 | 适配新工具接口 |
| `tests/test_p1_real_evolution.py` | 小改 | 适配 MockAdapter 和新工具 |
