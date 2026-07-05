# D5: Continuity Agent V1 — Handoff

**日期:** 2026-06-27
**Branch:** d5-continuity-agent-v1
**HEAD:** (pre-commit)
**Tag:** (to be created as `d5-continuity-agent-v1`)

---

## 1. 本阶段目标

实现第五个正式动态子 Agent：Continuity Agent。

基于当前 RoundSnapshot、CardState、accepted TurnRecord、ActiveMemory、RAG、世界书和已验证建议，
检查"这些事实、建议和叙事前提之间，哪些不能互相打架"。

**Continuity Agent ≠ Quality Gate。**
Continuity Agent 是写作前连续性约束层；Quality Gate 是写作后最终输出验证层。

---

## 2. 已实现合同 (7 files)

| 文件 | schemaId | 用途 |
|------|----------|------|
| `contracts/continuity_request.py` | `awp.rp.continuity-request.v1` | 连续性分析请求 |
| `contracts/continuity_issue.py` | `awp.rp.continuity-issue.v1` | 单个连续性问题 |
| `contracts/continuity_evidence.py` | `awp.rp.continuity-evidence.v1` | 证据引用 |
| `contracts/continuity_conflict.py` | `awp.rp.continuity-conflict.v1` | 证据冲突 |
| `contracts/continuity_result.py` | `awp.rp.continuity-result.v1` | 分析结果 |
| `contracts/continuity_suggestion.py` | `awp.rp.continuity-suggestion.v1` | 结构化建议 |
| `contracts/continuity_trigger_diagnostics.py` | `awp.rp.continuity-trigger-diagnostics.v1` | 触发诊断 |

### 修改合同 (3 files)

| 文件 | 变更 |
|------|------|
| `contracts/agent_suggestion.py` | 新增 9 个 ContinuityKind |
| `contracts/final_turn_brief.py` | 新增 4 个连续性字段 |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增 9 个连续性权重 |

---

## 3. 已实现 Runtime (8 files)

| 文件 | 用途 |
|------|------|
| `runtime/continuity_trigger_policy.py` | 确定性触发规则 |
| `runtime/continuity_runtime.py` | 主运行时 (快照 → 证据 → issue → 验证 → 排序 → 结果) |
| `runtime/continuity_query_planner.py` | 查询计划生成 (domain → tool 映射) |
| `runtime/continuity_evidence_ranker.py` | 证据优先级排序 (CardState > Turn > AM > RAG > WB) |
| `runtime/continuity_issue_detector.py` | issue 检测 (Fake Adapter) |
| `runtime/continuity_validator.py` | issue 验证 (拒绝无证据blocking/状态修改/事件创建) |
| `runtime/continuity_ranker.py` | 确定性排序 (max 3 blocking + 3 warning) |
| `runtime/continuity_adapter.py` | Result → AgentSuggestion 转换 |
| `runtime/continuity_tool_profile.py` | 工具白名单与角色规格 |

### 修改 Runtime (3 files)

| 文件 | 变更 |
|------|------|
| `runtime/agent_runtime_registry.py` | 注册 `continuity` 角色 |
| `runtime/tool_registry.py` | 所有工具新增 `continuity` 到 allowed_roles |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增连续性权重 |

---

## 4. ComfyUI 节点 (7 nodes)

| 节点 ID | 显示名称 | 函数 |
|---------|----------|------|
| `AWPV2ContinuityTrigger` | AWP V2 连续性触发 | evaluate |
| `AWPV2ContinuityRequest` | AWP V2 连续性请求 | build |
| `AWPV2ContinuityAgent` | AWP V2 连续性Agent | run |
| `AWPV2ContinuityValidator` | AWP V2 连续性验证 | validate |
| `AWPV2ContinuityRanker` | AWP V2 连续性排序 | rank |
| `AWPV2ContinuityResult` | AWP V2 连续性结果 | output |
| `AWPV2ContinuityDiagnostics` | AWP V2 连续性诊断 | diagnose |

### 官方工作流

`workflows/official_continuity_agent_v2.json`

节点图:
```
Memory Recall → RoundSnapshot → DirectorPlan
→ ContinuityTrigger → ContinuityAgent → ContinuityValidator → ContinuityRanker
                                    ↓
                              SuggestionMerge → FinalTurnBrief → Writer → Quality / Commit
```

no-op 路径:
```
shouldTrigger = false → 空 ContinuityResult(NO_TRIGGER) → SuggestionMerge 正常完成 → Writer 正常继续
```

---

## 5. 权限边界

### ContinuityRoleSpec

```
can_delegate = False
can_write_state = False
can_write_memory = False
can_generate_final_text = False
can_create_event = False
can_advance_timeline = False
can_modify_relationships = False
can_modify_scene = False
```

### 工具白名单 (10 tools, all read-only)

| toolId | 副作用 | 写状态 | 写内存 | 委派 |
|--------|--------|--------|--------|------|
| `accepted_turn_lookup` | 无 | ❌ | ❌ | ❌ |
| `active_memory_lookup` | 无 | ❌ | ❌ | ❌ |
| `rag_memory_lookup` | 无 | ❌ | ❌ | ❌ |
| `timeline_lookup` | 无 | ❌ | ❌ | ❌ |
| `relationship_context_lookup` | 无 | ❌ | ❌ | ❌ |
| `worldbook_lookup` | 无 | ❌ | ❌ | ❌ |
| `entity_alias_lookup` | 无 | ❌ | ❌ | ❌ |
| `event_stage_lookup` | 无 | ❌ | ❌ | ❌ |
| `scene_context_lookup` | 无 | ❌ | ❌ | ❌ |
| `npc_context_lookup` | 无 | ❌ | ❌ | ❌ |

---

## 6. Trigger Policy 触发条件

### 应触发场景

| 规则 | 匹配方式 | 风险等级 |
|------|----------|----------|
| 连续性指代词 (之前/已经/还没/回来/离开/答应/知道/秘密) | 关键词正则 | medium |
| 角色出入场信号 | 关键词正则 | medium |
| 时间变化信号 | 关键词正则 | low |
| 地点变化信号 | 关键词正则 | low |
| 知识边界/秘密/身份信号 | 关键词正则 | high |
| 承诺/约定信号 | 关键词正则 | high |
| 事件阶段变化信号 | 关键词正则 | medium |
| DirectorPlan 标记连续性风险 | 字段检查 | high |
| 活跃记忆中承诺与冲突并存 | kind 检查 | high |
| RAG 召回 ≥3 条 | 计数 | low |
| 最近回合涉及角色出入场 | 输出模式检查 | low |
| DirectorPlan 推动叙事变化 | 字段检查 | medium |

### 不应触发场景

1. 纯即时、单一动作，CardState 与最近 Turn 已足够覆盖
2. 玩家仅询问孤立的事实信息
3. 当前处于 retry、错误恢复、状态修复
4. 无角色、地点、时间线、关系、事件或知识状态风险
5. 仅为了增加 Agent 调用次数

---

## 7. ContinuityIssueKind 种类

| kind | 说明 | 严重等级 |
|------|------|----------|
| `identity_conflict` | 身份冲突 | blocking |
| `location_conflict` | 地点冲突 | blocking |
| `timeline_conflict` | 时间线冲突 | warning |
| `event_stage_conflict` | 事件阶段冲突 | warning |
| `state_conflict` | 状态冲突 | blocking |
| `relationship_conflict` | 关系冲突 | warning |
| `knowledge_boundary_conflict` | 知识边界冲突 | blocking |
| `secret_exposure_risk` | 秘密泄露风险 | blocking |
| `promise_resolution_risk` | 承诺兑现风险 | warning |
| `character_availability_conflict` | 角色可用性冲突 | warning |
| `causality_gap` | 因果关系缺失 | warning |
| `memory_conflict` | 记忆冲突 | warning |
| `suggestion_conflict` | 建议冲突 | warning |
| `worldbook_conflict` | 世界书冲突 | info |
| `player_agency_risk` | 玩家代理权风险 | blocking |

---

## 8. 证据优先级与冲突裁决

### 固定证据优先级

```
CardState (100) > accepted_turn (90) > ActiveMemory (80)
> high-confidence RagMemory (70) > worldbook (60)
> DirectorPlan (50) > AgentSuggestion (40) > tool_result (30)
```

### 冲突裁决规则

- CardState 是硬事实，RAG 只能提醒，不能推翻 CardState
- AgentSuggestion 永远不能推翻 CardState 或 accepted Turn
- 低优先级记忆若与高优先级事实冲突，必须标记 stale / conflicted
- blocking issue 必须有至少一个高优先级 evidenceRef
- 无 evidence 的 blocking issue 必须被 Validator 拒绝

---

## 9. 与 Quality Gate、History/Recall、其他 Agent 的职责差异

| 维度 | Continuity Agent | Quality Gate | History/Recall |
|------|-----------------|--------------|----------------|
| 时机 | 写作前 | 写作后 | 写作前 |
| 作用 | 连续性约束层 | 最终输出验证层 | 历史事实找回 |
| 输出 | 事实边界、冲突裁决、Writer 约束 | accept/revise | 带证据的历史建议 |
| 能否创造新事实 | 否 | 否 | 否 |
| 能否修改状态 | 否 | 否 | 否 |

---

## 10. 与 SuggestionMerge / FinalTurnBrief / Writer 的接入

### ContinuityResult → AgentSuggestion

- `blocking` issue → 高优先级 CONTINUITY_BLOCKING_RISK / CONTINUITY_FACT_CONSTRAINT
- `warning` issue → 中优先级 CONTINUITY_WRITER_CONSTRAINT
- `info` issue → 低优先级 CONTINUITY_DIRECTOR_FOLLOWUP

### FinalTurnBrief 新增字段

```python
accepted_continuity_constraints: list[str]      # 已采纳连续性约束
rejected_continuity_findings: list[dict]         # 被拒绝连续性发现
continuity_warnings: list[str]                   # 警告信息
continuity_evidence_refs: list[str]              # 证据引用
```

### Writer 规则

- Writer 只读取 FinalTurnBrief 中已采纳的连续性约束
- Writer 不得读取原始 ContinuityResult
- blocking 约束必须进入 FinalTurnBrief 硬约束
- warning 只作为软 Guidance

---

## 11. no-op / 降级 / 失败行为

| 场景 | 行为 |
|------|------|
| shouldTrigger = false | status = NO_TRIGGER，空 issue，SuggestionMerge 正常完成 |
| 无有效 issue | status = DEGRADED，degraded_reasons 记录原因 |
| 所有 issue 被验证拒绝 | status = DEGRADED，记录每个拒绝原因 |
| issue 被 outranked | 正常淘汰，不标记为 policy violation |
| Tool timeout | Gateway 返回 degraded，主链继续 |
| Runtime 失败 | 不阻断主链，Writer 不假设获得连续性约束 |

---

## 12. 测试命令与真实结果

```bash
python -m pytest tests/ -v
```

```
============================= 451 passed in 2.01s ==============================
```

| 测试集 | 数量 | 状态 |
|--------|------|------|
| P1 tests | 55 | ✅ 全部通过 |
| P2 tests | 51 | ✅ 全部通过 |
| M1 tests | 10+ | ✅ 全部通过 |
| C1 tests | 34 | ✅ 全部通过 |
| D1 tests | 40 | ✅ 全部通过 |
| D2 tests | 40 | ✅ 全部通过 |
| D3 tests | 41 | ✅ 全部通过 |
| D4 tests | 42 | ✅ 全部通过 |
| **D5 tests** | **50** | **✅ 全部通过** |
| **总计** | **451** | **✅ 全部通过** |

### D5 测试明细

| 测试类 | 数量 | 覆盖内容 |
|--------|------|----------|
| TestTriggerPolicy | 6 | 无风险/地点冲突/知识边界/承诺/连续性指代/禁止凑数 |
| TestContinuityValidator | 5 | 无证据blocking/RAG覆盖CardState/状态修改/事件创建/MemoryCommit |
| TestContinuityPermissions | 7 | Store/跨cardId/未授权工具/不可委派/不可写状态/不可写内存/不可生成正文 |
| TestContinuityRanker | 3 | 最多3+3/CardState证据优先/去重 |
| TestSuggestionMergeContinuity | 3 | blocking硬约束/warning软Guidance/Writer不可读原始Result |
| TestNoOpPath | 1 | no-op路径完成 |
| TestToolFailureBehavior | 1 | timeout降级 |
| TestD5WorkflowValidation | 1 | 官方workflow JSON校验 |
| TestD5NodeRegistration | 2 | 节点注册/中文显示名 |
| TestD5ContractSerialization | 7 | 所有D5合同序列化/反序列化 |
| TestContinuityAdapter | 1 | Result→AgentSuggestion 转换 |
| TestEvidencePriority | 4 | CardState>Turn>AM>RAG 优先级/stale标记 |
| TestD5E2ENormalPath | 1 | 完整连续性约束路径 |
| TestD5E2EViolationDegradation | 1 | 违规issue与降级路径 |
| TestContinuityAdditionalPermissions | 7 | 额外权限测试 |

---

## 13. 已知限制

1. IssueDetector 使用 Fake Adapter（确定性检测），未使用真实 LLM
2. Query Planner 生成查询但未实际通过 ToolGateway 执行（Snapshot 模式直接收集证据）
3. Trigger Policy 使用简单正则，不支持同义词扩展
4. 证据冲突检测使用简单关键词启发式，不支持语义冲突检测
5. 排序算法基于固定权重，不支持动态调整
6. Validator 使用正则模式匹配状态修改，可能遗漏变体表述

---

## 14. 下一阶段推荐接入点

### D-Integration 或 D6 Memory Curator Agent

- 可复用 DynamicSubAgentPool + AgentRuntimeRegistry 模式
- 可复用 ToolGateway + ToolPermissionPolicy
- 可复用 SuggestionMerge + FinalTurnBrief 接入方式

---

## 15. 禁止回归的架构约束

1. **ContinuityAgent 不得写 CardState / TurnRecord / ActiveMemory / RAG**
2. **ContinuityAgent 不得委派子 Agent**
3. **ContinuityAgent 不得生成最终玩家正文**
4. **ContinuityAgent 不得创建事件或推进时间线**
5. **ContinuityAgent 不得修改关系或场景**
6. **所有工具调用必须经过 ToolGateway**
7. **未注册工具一律拒绝**
8. **无 evidence 的 blocking issue 不得被采纳**
9. **低优先级 RAG 不得产生高优先级硬约束**
10. **ContinuityAgent 不得创造新事实**
11. **Writer 只能读取 FinalTurnBrief 中已采纳的连续性约束**
12. **QualityGate reject 时零副作用**
13. **no-op 路径必须能完成正式回合**
