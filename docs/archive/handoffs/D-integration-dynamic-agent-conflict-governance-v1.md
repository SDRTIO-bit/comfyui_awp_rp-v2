# D-Integration: Dynamic Agent Integration & Conflict Governance V1

**Date**: 2026-06-27
**Branch**: main
**HEAD**: 2665f43
**Tag**: d-integration-dynamic-agent-conflict-governance-v1
**Tests**: 566 passed (497 existing + 69 new)

---

## 1. 启动核验结果

| 检查项 | 结果 |
|---|---|
| 分支基于包含 D6 的最新 origin/main | ✅ main @ 9fb0efa |
| D1～D6 tags 全部存在 | ✅ d1-history-recall-v1 … d6-memory-curator-agent-v1 |
| docs/reference/ 存在 | ❌ 不存在（文档缺口，如实记录） |
| 工作树干净 | ✅ (post-commit, clean) |
| 全部测试通过 | ✅ 566 passed in 2.44s |

---

## 2. D1～D6 的正式执行位置

| Agent | Role ID | Wave | 触发位置 | 执行位置 |
|---|---|---|---|---|
| D1 History/Recall | history-recall | Wave A | DynamicAgentScheduler | DynamicSubAgentPool |
| D2 Opportunity | opportunity | Wave A | DynamicAgentScheduler | DynamicSubAgentPool |
| D3 World-Life | world-life | Wave A | DynamicAgentScheduler | DynamicSubAgentPool |
| D4 Emotion/Relationship | emotion-relationship | Wave A | DynamicAgentScheduler | DynamicSubAgentPool |
| D5 Continuity | continuity | Wave B | DynamicAgentScheduler | DynamicSubAgentPool (after Wave A barrier) |
| D6 Memory Curator | memory-curator | Post-Commit | MemoryCurationTriggerPolicy | MemoryCurationRuntime |

**关键修正**: `world-life` role 原先未注册到 BUILTIN_ROLES，D-Integration 已修正。

---

## 3. Wave A 与 Continuity Barrier 拓扑

```
Wave A (并发):
  D1 History / Recall
  D2 Opportunity
  D3 World-Life
  D4 Emotion / Relationship
        ↓
  Normalized Candidate Suggestion Set
        ↓
  Continuity Barrier (ContinuityBarrierRuntime)
        ↓
  Wave B:
  D5 Continuity Agent
        ↓
  Conflict Governance (SuggestionConflictGovernor)
        ↓
  Director Suggestion Resolution (DirectorSuggestionResolutionRuntime)
        ↓
  FinalTurnBrief → Writer
```

Continuity Barrier 只传递：
- suggestion_id, role, kind, priority, confidence
- summary, recommendations (最多3条)
- evidence_refs, risk_flags
- proposed_state_changes (最多3条)

不传递：
- 原始模型思维链
- 完整工具原始输出
- 系统 Prompt

---

## 4. D6 的 post-accept 位置

```
QualityGate(ACCEPT) → CardStateCommit(SUCCESS) → TurnRecordCommit(SUCCESS)
    → MemoryCurationTriggerPolicy → MemoryCurationRuntime
    → MemoryPlanCompiler → ActiveMemoryCommit + RagMemoryCommit
```

D6 永远不进入 Writer 前 DynamicSubAgentPool。
D6 永远不参与 SuggestionMerge。
D6 永远不影响当前回合已经写出的正文。
D6 只读取 accepted turn。

---

## 5. 预算与并发策略

| 参数 | Simple | Normal | Complex |
|---|---|---|---|
| max_agents_per_turn | 0 | 1 | 4 |
| max_parallel_agents | 0 | 1 | 3 |
| wave_a_max_agents | 0 | 1 | 3 |
| wave_b_max_agents | 0 | 0 | 1 |
| max_tool_calls_per_turn | 0 | 5 | 20 |
| agent_timeout_ms | - | 30000 | 30000 |
| turn_deadline_ms | - | 120000 | 120000 |

默认策略:
- Simple turn: 0 agents (SIMPLE_TURN_POLICY)
- Normal turn: 1 Wave A, no Wave B (NORMAL_TURN_POLICY)
- Complex turn: 3 Wave A + 1 Wave B (COMPLEX_TURN_POLICY)

---

## 6. Agent 选择与跳过规则

当候选 Agent 数超过预算时，确定性排序：

```
history-recall (1.0)
> continuity (0.95)
> emotion-relationship (0.7)
> opportunity (0.6)
> world-life (0.5)
```

跳过原因记录在 `ScheduledWave.skipped_tasks` 中。

---

## 7. 工具预算和超时规则

- 每回合总 Tool Call 上限: max_tool_calls_per_turn (默认20)
- 单 Agent Tool Call 上限: max_tool_calls_per_agent (默认5)
- Agent 超时: agent_timeout_ms (默认30000ms)
- 回合截止: turn_deadline_ms (默认120000ms)
- 超限行为: deterministic skip / degrade，不阻断主链

---

## 8. 冲突优先级与 resolution 规则

优先级层次：
```
CardState (100)
> accepted TurnRecord (90)
> ActiveMemory (80)
> 高置信 RagMemory (70)
> 当前激活世界书 (60)
> DirectorPlan
> AgentSuggestion
> 无证据推测
```

冲突类型 (ConflictKind):
- fact_contradiction
- state_path_collision
- player_agency_violation
- evidence_priority_override
- temporal_contradiction
- relationship_boundary
- world_life_fact_leak
- opportunity_fact_leak
- emotion_fact_leak
- continuity_hard_block

Resolution 类型:
- accepted
- partially_accepted
- rejected
- downgraded_to_soft_guidance
- deferred
- blocked_by_player_agency
- blocked_by_hard_fact

---

## 9. Director Suggestion Resolution 的职责

`DirectorSuggestionResolutionRuntime` 结构化输出：
- accepted_suggestion_ids
- partially_accepted_suggestion_ids
- rejected_suggestion_ids
- rejection_reasons
- hard_constraints
- soft_guidance
- writer_priorities
- player_agency_guards
- evidence_refs

Director 不直接输出玩家可见正文，不写 CardState/TurnRecord/Memory。

---

## 10. Writer 输入边界与 FinalTurnBrief 裁剪

Writer 只能读取：
- RoundSnapshot 中允许的裁剪事实
- FinalTurnBrief
- 已采纳 hardConstraints
- 已采纳 softGuidance
- 玩家输入
- 必要格式与风格约束

Writer 不得读取：
- 原始 AgentSuggestion
- 原始 AgentExecutionResult
- 原始 ToolResult
- 执行 Trace
- 被拒绝建议

裁剪顺序：先低优先级说明 → 重复软 Guidance → 低价值世界活性 → 低价值机会 → 必要上下文

不得裁剪：CardState 硬事实、accepted Turn 窗口、blocking Continuity Constraint、玩家代理权、Turn Goal

---

## 11. retry / resume / idempotency 行为

- Writer 前 Agent 全部只读，可在相同 snapshot 下安全重跑
- D6 MemoryCommit 保持幂等（idempotency_key = turn_id:memory_commit_id）
- retry 不得重复创建 ActiveMemory / RagMemory
- 已 accepted 的 TurnRecord 不得重复提交
- CardState patch 不得重复提交

---

## 12. Trace、诊断与失败降级方式

每个 Agent 的 Trace 包含：
- triggered / skip_reason
- outcome (success/no_trigger/skipped_budget/skipped_priority/timeout/degraded/failed)
- suggestion_count / adopted_count / rejected_count
- duration_ms / tool_calls_made / tokens_used
- wave (wave_a/wave_b)
- priority_score

`IntegratedTurnTrace` 聚合：
- agent_reports (每 Agent)
- budget_report (回合级)
- conflicts (冲突记录)
- resolution (Director 决议)
- dropped_suggestion_ids / truncated_sections / budget_reason

---

## 13. 官方 ComfyUI 整合工作流

文件: `workflows/official_dynamic_agent_integration_v1.json`

完整流程节点：
1. AWPV2CardStateInit
2. AWPV2RoundSnapshot
3. AWPV2DirectorPlan
4. AWPV2DynamicAgentScheduler (新增)
5. AWPV2DynamicAgentWaveExecutor (新增)
6. D1-D5 Trigger 节点 (观察模式)
7. AWPV2SuggestionMerge
8. AWPV2ContinuityBarrier (新增)
9. AWPV2SuggestionConflictGovernor (新增)
10. AWPV2DirectorSuggestionResolution (新增)
11. AWPV2FinalTurnBrief
12. AWPV2WriterInputBundleV2
13. AWPV2QualityPipeline
14. AWPV2CardStateCommit
15. AWPV2TurnRecordCommit
16. AWPV2MemoryCurationTrigger
17. AWPV2MemoryCurationCommitPlan
18. AWPV2ActiveMemoryCommit
19. AWPV2RagMemoryCommit
20. AWPV2AgentIntegrationDiagnostics (新增，观察模式)

D6 明确在 Commit 后，Writer 前与 Writer 后链明显分层。

---

## 14. 测试命令与真实结果

```
python -m pytest tests/ -q
```

结果: **566 passed in 2.44s**

D-Integration 新增测试: 69 个
- Test 1: D1-D6 全部可被 registry 发现 ✅
- Test 2-3: D1-D5 可进入 Writer 前调度；D6 不得进入 ✅
- Test 4: D6 位于 CardStateCommit 与 TurnRecordCommit 之后 ✅
- Test 5-7: 简单/普通/复杂回合默认策略 ✅
- Test 8: 超预算按确定性优先级跳过 ✅
- Test 9: max_parallel_agents 被真实强制 ✅
- Test 10: 每回合总 Tool Call 上限被真实强制 ✅
- Test 11-13: 单 Agent/Tool 超时不阻断主链 ✅
- Test 14: Continuity timeout → Writer 仅使用确定性约束 ✅
- Test 15: History 高优先级事实可否决低优先级建议 ✅
- Test 16-17: CardState > RAG, accepted Turn > 低优先级 ✅
- Test 18-20: Opportunity/World-Life/Emotion 不能变成事实 ✅
- Test 21: Continuity blocking 无高优先级证据时降级 ✅
- Test 22: 玩家代理权不能被覆盖 ✅
- Test 23: 相同建议去重 ✅
- Test 24: 冲突建议有明确 resolution ✅
- Test 25: 被拒绝建议不进入 FinalTurnBrief ✅
- Test 26-27: Writer 无法读取原始 AgentResult/ToolResult ✅
- Test 28-29: 硬约束、玩家代理权不被裁剪 ✅
- Test 30-32: Quality Gate reject → D6 不触发 ✅
- Test 33: D6 failure 不撤销 accepted output ✅
- Test 34-37: retry 不重复提交 ✅
- Test 38: 每个 Agent 的 Trace 包含完整字段 ✅
- Test 39: 工作流 JSON 结构校验通过 ✅
- Test 40: 所有既有 D1-D6 测试持续通过 ✅
- E2E A: 零 Agent 普通回合 ✅
- E2E B: 单 Agent 历史回合 ✅
- E2E C: 多 Agent 复杂回合 ✅
- E2E D: 冲突、超时、降级与重试回合 ✅

---

## 15. 新增 / 修改文件

### 新增文件 (12)
| 文件 | 职责 |
|---|---|
| contracts/suggestion_conflict.py | 统一冲突记录 |
| contracts/agent_execution_report.py | 每 Agent 执行报告 |
| contracts/turn_agent_budget_report.py | 每回合预算报告 |
| contracts/integrated_turn_trace.py | 集成追踪聚合 |
| runtime/turn_agent_budget_policy.py | 预算策略 |
| runtime/dynamic_agent_scheduler.py | Wave A/B 调度 |
| runtime/dynamic_agent_wave_executor.py | Wave 执行器 |
| runtime/continuity_barrier_runtime.py | 连续性屏障 |
| runtime/suggestion_conflict_governor.py | 冲突治理 |
| runtime/director_suggestion_resolution_runtime.py | Director 决议 |
| runtime/agent_integration_trace.py | 集成追踪构建 |
| tests/test_d_integration.py | 69 个集成测试 |
| workflows/official_dynamic_agent_integration_v1.json | 官方工作流 |

### 修改文件 (4)
| 文件 | 修改内容 |
|---|---|
| runtime/agent_runtime_registry.py | 新增 world-life role 到 BUILTIN_ROLES |
| runtime/turn_orchestrator.py | 新增 wave-based 执行路径（可选组件） |
| runtime/__init__.py | 导出新 runtime 模块 |
| contracts/__init__.py | 导出新 contract 模块 |

---

## 16. 已知限制

1. docs/reference/ 架构文档不存在（文档缺口）
2. 当前 Wave A 执行仍是顺序的（DynamicSubAgentPool.execute 顺序遍历），真正的并发需要异步/线程池支持
3. FinalTurnBrief 裁剪逻辑尚未实现自动截断（当前由 DirectorResolution 输出裁剪元数据，Writer 端自行处理）
4. TurnOrchestrator 的 wave 路径需要显式注入 scheduler/wave_executor/budget_policy 才会激活

---

## 17. 下一阶段

**Public Alpha Release Hygiene & Repository Documentation V1**

---

## 18. 禁止回归的架构约束

1. CardState 只能通过 CardStateCommitRuntime 写入
2. TurnRecord 只能通过 TurnRecordCommitRuntime 写入
3. ActiveMemory / RagMemory 只能通过各自的 CommitRuntime 写入
4. D6 永远不在 Writer 前 DynamicSubAgentPool 中
5. Writer 只能读取 WriterInputBundle，不能读取原始 Agent 输出
6. QualityGate reject = zero side effects
7. 所有 Agent 只读、不可委托、不可写状态/记忆
8. 每个 Agent 有 no-op 路径
