# D1: History / Recall Dynamic Sub-Agent V1 — Handoff

**日期:** 2026-06-27
**Branch:** master
**HEAD:** (pre-commit, working tree has D1 changes)
**Tag:** (to be created as `d1-history-recall-v1`)

---

## 1. 本阶段目标

实现第一个正式动态子 Agent：History / Recall Agent。

在存在历史指代、连续性风险、关系记忆风险、未兑现承诺等情况下，
对当前 RoundSnapshot 内允许访问的记忆与工具结果进行受控回查，
返回带证据的结构化历史建议。

---

## 2. 已实现合同 (7 files)

| 文件 | schemaId | 用途 |
|------|----------|------|
| `contracts/recall_focus.py` | `awp.rp.recall-focus.v1` | 回查焦点实体与类型 |
| `contracts/recall_evidence.py` | `awp.rp.recall-evidence.v1` | 单条回查证据 |
| `contracts/continuity_risk.py` | `awp.rp.continuity-risk.v1` | 连续性风险 |
| `contracts/history_recall_request.py` | `awp.rp.history-recall-request.v1` | 回查请求 |
| `contracts/history_recall_result.py` | `awp.rp.history-recall-result.v1` | 回查结果 |
| `contracts/history_recall_suggestion.py` | `awp.rp.history-recall-suggestion.v1` | 结构化建议 |
| `contracts/history_recall_diagnostics.py` | `awp.rp.history-recall-diagnostics.v1` | 诊断信息 |

### 修改合同 (2 files)

| 文件 | 变更 |
|------|------|
| `contracts/agent_suggestion.py` | 新增 5 个 SuggestionKind (HISTORICAL_CONFLICT 等) |
| `contracts/final_turn_brief.py` | 新增 4 个历史字段 (accepted_history_findings 等) |

---

## 3. 已实现 Runtime (7 files)

| 文件 | 用途 |
|------|------|
| `runtime/history_recall_trigger_policy.py` | 确定性触发规则 (正则匹配) |
| `runtime/history_recall_runtime.py` | 主运行时 (快照数据 → 证据 → 结果) |
| `runtime/history_recall_query_planner.py` | 查询计划生成 (RecallKind → Tool) |
| `runtime/recall_evidence_ranker.py` | 证据排序 (CardState > Turn > AM > RAG > WB) |
| `runtime/history_recall_validator.py` | 结果验证 (拒绝无证据结论/最终正文) |
| `runtime/history_recall_adapter.py` | 结果 → AgentSuggestion 转换 |
| `runtime/history_recall_tool_profile.py` | 工具白名单与角色规格 |

### 修改 Runtime (3 files)

| 文件 | 变更 |
|------|------|
| `runtime/agent_runtime_registry.py` | 注册 `history-recall` 角色 |
| `runtime/tool_registry.py` | 注册 `accepted_turn_lookup`, `active_memory_lookup` |
| `runtime/tool_gateway.py` | FakeToolRunner 新增 2 个工具默认结果 |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增 5 个历史建议权重 |

---

## 4. ComfyUI 节点 (6 nodes)

| 节点 ID | 显示名称 | 函数 |
|---------|----------|------|
| `AWPV2HistoryRecallTrigger` | AWP V2 历史回查触发 | evaluate |
| `AWPV2HistoryRecallRequest` | AWP V2 历史回查请求 | build |
| `AWPV2HistoryRecallAgent` | AWP V2 历史回查Agent | run |
| `AWPV2RecallEvidenceRanker` | AWP V2 回查证据排序 | rank |
| `AWPV2HistoryRecallResult` | AWP V2 历史回查结果 | output |
| `AWPV2HistoryRecallDiagnostics` | AWP V2 历史回查诊断 | diagnose |

### 官方工作流

`workflows/official_history_recall_agent_v2.json`

节点图:
```
CardStateInit → RoundSnapshot → DirectorPlan
→ HistoryRecallTrigger → HistoryRecallRequest → HistoryRecallAgent
→ RecallEvidenceRanker → HistoryRecallResult → HistoryRecallDiagnostics
                                    ↓
                              SuggestionMerge → FinalTurnBrief → Writer
```

---

## 5. 权限边界

### HistoryRecallRoleSpec

```
can_delegate = False
can_write_state = False
can_write_memory = False
can_generate_final_text = False
```

### 工具白名单 (7 tools, all read-only)

| toolId | 副作用 | 写状态 | 写内存 | 委派 |
|--------|--------|--------|--------|------|
| `rag_memory_lookup` | 无 | ❌ | ❌ | ❌ |
| `entity_alias_lookup` | 无 | ❌ | ❌ | ❌ |
| `timeline_lookup` | 无 | ❌ | ❌ | ❌ |
| `relationship_context_lookup` | 无 | ❌ | ❌ | ❌ |
| `worldbook_lookup` | 无 | ❌ | ❌ | ❌ |
| `accepted_turn_lookup` | 无 | ❌ | ❌ | ❌ |
| `active_memory_lookup` | 无 | ❌ | ❌ | ❌ |

---

## 6. Trigger Policy 触发条件

| 规则 | 匹配方式 | 风险等级 |
|------|----------|----------|
| 历史指代词 (之前/上次/当年/那件事/答应过/还记得) | 正则 | MEDIUM |
| 承诺/约定关键词 (答应/承诺/保证/约定) | 正则 | MEDIUM |
| 秘密/冲突关键词 (秘密/隐瞒/冲突/债务/误会) | 正则 | HIGH |
| 关系变化关键词 (关系/信任/怀疑/敌意) | 正则 | MEDIUM |
| 模糊指代 (他之前/她之前/那个人) | 正则 | LOW |
| Director 风险标记 | 字段检查 | HIGH |
| 未解决伏笔 | 字段检查 | MEDIUM |
| RAG 冲突 | 字段检查 | HIGH |
| 多 RAG 候选 (≥3) | 计数 | LOW |

---

## 7. Evidence 排序优先级

```
CardState (100) > accepted_turn (90) > ActiveMemory (80)
> RagMemory (70) > worldbook (60) > tool_result (50)
```

同类型内: confidence ↓ → recency ↓ → relevance_score ↓

冲突证据保留但标记 conflict_status = "conflicted" | "stale"

---

## 8. 与 SuggestionMerge / FinalTurnBrief / Writer 的接入

### HistoryRecallResult → AgentSuggestion

- `continuity_fact` → `SuggestionKind.CONTINUITY_ISSUE`
- `relationship_context` → `SuggestionKind.RELATIONSHIP_SHIFT`
- `historical_conflict` → `SuggestionKind.HISTORICAL_CONFLICT`
- `identity_clarification` → `SuggestionKind.IDENTITY_CLARIFICATION`
- `timeline_warning` → `SuggestionKind.TIMELINE_WARNING`
- `writer_constraint` → `SuggestionKind.WRITER_CONSTRAINT`
- `director_followup` → `SuggestionKind.DIRECTOR_FOLLOWUP`

### FinalTurnBrief 新增字段

```python
accepted_history_findings: list[str]
rejected_history_findings: list[dict]
history_continuity_warnings: list[str]
history_evidence_refs: list[str]
```

### Writer 只能读取 FinalTurnBrief 中已采纳的内容

- Writer 通过 WriterInputBundle 读取 FinalTurnBrief
- Writer 无法读取原始 HistoryRecallResult
- Writer 无法访问 ToolGateway 或 Store

---

## 9. no-op / 降级 / 失败行为

| 场景 | 行为 |
|------|------|
| shouldTrigger = false | 返回 NO_TRIGGER，空 suggestion，SuggestionMerge 正常完成 |
| 无证据 | confirmed_facts = []，status = SUCCESS |
| 冲突证据 | status = DEGRADED，degraded_reasons 记录原因 |
| 无 source_ref 证据 | validator 拒绝其为 confirmedFact |
| 最终正文泄漏 | validator 拒绝，status = DEGRADED |
| Tool timeout | Gateway 返回 degraded，主链继续 |
| required tool failure | 记录 failed，Writer 不假设结果存在 |

---

## 10. 测试命令与真实结果

```bash
python -m pytest tests/ -v
```

```
============================= 278 passed in 2.18s ==============================
```

| 测试集 | 数量 | 状态 |
|--------|------|------|
| P1 tests | 55 | ✅ 全部通过 |
| P2 tests | 51 | ✅ 全部通过 |
| M1 tests | 10+ | ✅ 全部通过 |
| C1 tests | 34 | ✅ 全部通过 |
| 其他 | 88 | ✅ 全部通过 |
| **D1 tests** | **40** | **✅ 全部通过** |
| **总计** | **278** | **✅ 全部通过** |

### D1 测试明细

| 测试类 | 数量 | 覆盖内容 |
|--------|------|----------|
| TestTriggerPolicy | 7 | 无风险/历史指代/承诺冲突/CardState冲突/风险标记/伏笔/别名 |
| TestEvidenceRanker | 3 | CardState>Turn>AM>RAG 优先级 |
| TestHistoryRecallValidator | 3 | 无sourceRef/无证据结论/最终正文拒绝 |
| TestHistoryRecallPermissions | 7 | 字段限制/无Store/跨cardId/未授权工具/不可委派/不可写状态/不可写内存 |
| TestToolFailureBehavior | 3 | timeout降级/optional失败/required失败策略 |
| TestHistoryRecallAdapter | 1 | Result→AgentSuggestion 转换 |
| TestSuggestionMergeHistory | 3 | 冲突拒绝/FinalTurnBrief字段/Writer不可读原始Result |
| TestNoOpPath | 1 | no-op路径完成 |
| TestContractSerialization | 7 | 所有D1合同序列化/反序列化 |
| TestD1E2ENormalPath | 1 | 完整历史回查路径 |
| TestD1E2EConflictDegradation | 1 | 冲突与降级路径 |
| TestD1NodeRegistration | 2 | 节点注册/中文显示名 |
| TestD1WorkflowValidation | 1 | 官方workflow JSON校验 |

---

## 11. 已知限制

1. 当前 HistoryRecallRuntime 使用快照数据直接收集证据，未通过 ToolGateway 执行工具调用（Fake 模式）
2. Query Planner 生成查询但未实际执行（需要 LLM Adapter 集成后才能使用真实工具）
3. 证据排序是确定性的，但不包含语义相似度计算
4. Trigger Policy 使用简单正则，不支持同义词扩展
5. 未实现 LLM 驱动的查询规划（仅关键词/实体查询）

---

## 12. 下一阶段推荐接入点

### D2: Opportunity Agent

- 可复用 DynamicSubAgentPool + AgentRuntimeRegistry 模式
- 可复用 ToolGateway + ToolPermissionPolicy
- 可复用 SuggestionMerge + FinalTurnBrief 接入方式
- 需要新增 `opportunity` 角色和对应的 SuggestionKind

### 推荐接入步骤

1. 注册 `opportunity` 角色到 AgentRuntimeRegistry
2. 实现 OpportunityTriggerPolicy
3. 实现 OpportunityRuntime
4. 新增合同 (OpportunityRequest, OpportunityResult)
5. 转换为 AgentSuggestion → SuggestionMerge → FinalTurnBrief

---

## 13. 禁止回归的架构约束

1. **HistoryRecallAgent 不得写 CardState / TurnRecord / ActiveMemory / RAG**
2. **HistoryRecallAgent 不得委派子 Agent**
3. **HistoryRecallAgent 不得生成最终玩家正文**
4. **所有工具调用必须经过 ToolGateway**
5. **未注册工具一律拒绝**
6. **证据无 sourceRef 不得成为 confirmedFact**
7. **冲突证据不得作为确定事实**
8. **Writer 只能读取 WriterInputBundle**
9. **QualityGate reject 时零副作用**
10. **no-op 路径必须能完成正式回合**
