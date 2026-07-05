# P1 Real RP Evolution Loop — 交接文档

日期: 2026-06-28
分支: feat/comfy-multisession-long-context-acceptance-v1
测试: 71 pass (test_p1_real_evolution + test_linear_debug + test_persistent_session + test_p0_canonical)

---

## 一、已完成的工作

### 1.1 新文件

| 文件 | 用途 |
|------|------|
| `contracts/turn_evolution_proposal.py` | TurnEvolutionProposal + StateUpdateProposalV2 + MemoryCandidate |
| `contracts/curator_request.py` | CuratorRequest 输入合约 |
| `runtime/turn_evolution_curator.py` | TurnEvolutionCurator — LLM 驱动的状态+记忆策展器 |
| `runtime/condition_evaluator.py` | 安全条件求值器 (equals/gt/gte/and/or/not 等) |
| `nodes/continue_turn_execution_node.py` | AWPV2ContinueTurn — 正式 Continue 回合 |
| `testing/linear_persistent_rp_debug.py` | 线性调试工具 (绕过 ComfyUI 直接调用节点) |
| `tests/test_p1_real_evolution.py` | 23 个 P1 测试 |
| `tests/test_linear_debug.py` | 5 个调试工具 smoke test |

### 1.2 修改的文件

| 文件 | 改动 |
|------|------|
| `runtime/persistent_turn_engine.py` | 空 patch + 假 D6 → TurnEvolutionCurator |
| `runtime/version_locked_worldbook_resolver.py` | 条件世界书 + position 字段支持 + deferred 求值 + constant 预算提高 |
| `runtime/session_runtime_load.py` | 传递 CardState 给世界书条件求值 |
| `runtime/quality_pipeline_runtime.py` | JSON 检测改为只匹配真正 JSON 模式 |
| `adapters/llm/real_director_adapter.py` | 生成 0-2 个委派任务 |
| `contracts/turn_result_projection.py` | 新增 state_effects / memory_effects / delegation_effects |
| `nodes/__init__.py` | 注册 AWPV2ContinueTurnP1 |

---

## 二、已验证可工作的部分

### 2.1 真实酒馆卡加载 (测试酒馆卡, 263KB, 40 worldbook)

- Bootstrap 正确加载 40 条 worldbook (26 constant + 14 selective)
- 6 greetings 正确解析 (g0-g6)
- Session binding / opening record / worldbook binding 全部写入 SQLite

### 2.2 世界书激活

- Constant 条目: 每回合激活 8 条 (预算 max_constant_entries=8)
- Selective 条目: 关键词匹配正常 (输入含"周语晴" → wb_3 激活, 含"刘屠户" → 对应条目激活)
- 修复了 `position` 字段误判为 unsupported 的 bug
- 修复了 `deferred` 条目被跳过的 bug
- 修复了 constant+selective 条目被要求有关键词的 bug

### 2.3 双 Agent (Director + Writer)

- Director: deepseek-v4-pro, success=True
- Writer: deepseek-v4-flash, success=True, 产出 1100-1500 字中文 RP 正文
- 每回合 2 次 LLM 调用 (Director + Writer)

### 2.4 子 Agent 触发

- Turn 1: 3 个触发 (d2_opportunity, d3_world_life, d5_continuity)
- 触发策略是确定性的 (基于关键词/快照内容)
- 触发后产生的 AgentSuggestion 通过 SuggestionMerge 合并到 Writer guidance

### 2.5 状态演化 (真实 LLM)

- Turn 1 (问候): no_state_change (正确)
- Turn 2 (揭露秘密): `variables.trust = 1` + `event_flags.secret_revealed` → revision 0→1
- Turn 3 (安慰): `variables.trust` +1 → revision 1→2
- Turn 4 (刘屠户出场): scene 全面变化 (loc/time/weather/NPC) + 新 event_flag → revision 2→3

### 2.6 调试工具

- `testing/linear_persistent_rp_debug.py` 完整跑通 bootstrap → first_turn → accepted_text → probe → continuation → accepted_text → probe
- `--replay-first-turn` 幂等重放验证通过
- `--restart-runtime-before-continuation` SQLite 恢复验证通过

---

## 三、已确认未工作的部分

### 3.1 记忆系统 (L2 ActiveMemory / L3 RAG)

**现象**: `memory_curation_status = "noop"`, `active_added = 0`, `rag_added = 0`

**根因链**:

1. TurnEvolutionCurator 调用 LLM (`generate_text`)
2. LLM 返回 JSON，但 `memory_candidates_active` 和 `memory_candidates_rag` 为空数组或缺失
3. Curator 解析后得到 0 个 memory candidates
4. PersistentTurnEngine._run_memory_commit 收到空 candidates → 返回 "noop"

**需要验证的问题**:
- curator prompt 是否足够明确地要求 LLM 返回 memory candidates?
- LLM 实际返回的 JSON 是什么? (在 `generate_text` 的 raw response 中)
- `_parse_llm_response` 是否正确解析了 `memory_candidates_active` 字段?

**不要直接修**。先用以下方式验证:
```python
# 在 curator._curate_with_llm 中 print(text) 看 LLM 原始返回
# 确认 LLM 是否返回了 memory_candidates_active
# 确认 _parse_llm_response 是否正确提取了它们
```

### 3.2 子 Agent Turn 2 未触发

**现象**: Turn 2 的 `delegation.requested = []`, `delegation.executed = []`

**可能原因**: 触发策略的关键词/条件在 Turn 2 的快照中未满足

**需要验证**:
- Turn 2 的 RoundSnapshot 内容是什么?
- 各触发策略的 `evaluate()` 返回了什么?
- 这是设计行为还是 bug?

### 3.3 Curator Prompt 返回格式不稳定

**现象**: 之前测试中 LLM 有时返回 `type` 而非 `op`, `key` 而非 `path`

**当前处理**: `_parse_llm_response` 有容错 (`op_map`, 路径前缀推断)

**需要验证**: 在真实运行中 LLM 是否稳定返回正确格式

---

## 四、关键文件位置

| 组件 | 文件 |
|------|------|
| 主引擎 | `runtime/persistent_turn_engine.py` |
| Curator | `runtime/turn_evolution_curator.py` |
| 条件求值器 | `runtime/condition_evaluator.py` |
| 世界书 Resolver | `runtime/version_locked_worldbook_resolver.py` |
| Continue 节点 | `nodes/continue_turn_execution_node.py` |
| 调试工具 | `testing/linear_persistent_rp_debug.py` |
| Patch 验证 | `contracts/card_state_patch.py` |
| CardState 提交 | `runtime/card_state_commit_runtime.py` |
| 质量门 | `runtime/quality_pipeline_runtime.py` |
| Director 适配器 | `adapters/llm/real_director_adapter.py` |
| Writer 适配器 | `adapters/llm/real_writer_adapter.py` |
| DeepSeek 适配器 | `adapters/llm/deepseek_adapter.py` |
| Memory commit | `runtime/active_memory_commit_runtime.py` + `runtime/rag_memory_commit_runtime.py` |
| Memory plan | `runtime/memory_plan_compiler.py` |

---

## 五、工作原则

1. **先验证再改代码** — 不要假设问题是什么，先用 print/日志确认实际行为
2. **不要改测试来通过** — 测试反映的是预期行为，代码才是要改的
3. **不要改合约来修 bug** — `PatchOpType.INCREMENT` 的 `may_create` 不应该随意改
4. **最小改动** — 每次只改一个文件的一个点，验证通过再改下一个
5. **不要引入新路径** — 所有改动必须在现有 canonical persistent path 内

---

## 六、环境

- 测试卡: 任意酒馆卡 JSON (263KB+, 40+ worldbook, 6+ greetings)
- 预设: `kedai_heavy_v1` (已包含在 `presets/writer/`)
- API Key: `DEEPSEEK_API_KEY` 已设置
- Profile: `deepseek-v4-pro-director`, `deepseek-v4-flash-writer`
- 测试命令: `python -m awp_rp_runtime_v2.testing.linear_persistent_rp_debug --card "<your-card-path>.json" --greeting-id g1 --verbose`
