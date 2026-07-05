# D2: Opportunity Agent V1 — Handoff

**日期:** 2026-06-27
**Branch:** master
**HEAD:** (pre-commit, working tree has D2 changes)
**Tag:** (to be created as `d2-opportunity-agent-v1`)

---

## 1. 本阶段目标

实现第二个正式动态子 Agent：Opportunity Agent。

基于当前 RoundSnapshot、未解决线索、ActiveMemory、人物关系张力、
玩家目标、场景压力和已确认历史事实，识别"本回合可以被 Director 选择性采用的戏剧机会"。

**Opportunity ≠ Event。**
Opportunity Agent 只能提出可选叙事入口，不能生成事件、修改状态或推进时间线。

---

## 2. 已实现合同 (7 files)

| 文件 | schemaId | 用途 |
|------|----------|------|
| `contracts/opportunity_request.py` | `awp.rp.opportunity-request.v1` | 机会分析请求 |
| `contracts/opportunity_candidate.py` | `awp.rp.opportunity-candidate.v1` | 单个机会候选 |
| `contracts/opportunity_evidence.py` | `awp.rp.opportunity-evidence.v1` | 证据引用 |
| `contracts/opportunity_result.py` | `awp.rp.opportunity-result.v1` | 分析结果 |
| `contracts/opportunity_risk.py` | `awp.rp.opportunity-risk.v1` | 风险评估 |
| `contracts/opportunity_suggestion.py` | `awp.rp.opportunity-suggestion.v1` | 结构化建议 |
| `contracts/opportunity_trigger_diagnostics.py` | `awp.rp.opportunity-trigger-diagnostics.v1` | 触发诊断 |

### 修改合同 (3 files)

| 文件 | 变更 |
|------|------|
| `contracts/agent_suggestion.py` | 新增 11 个 SuggestionKind (PROMISE_PRESSURE 等) |
| `contracts/final_turn_brief.py` | 新增 4 个机会字段 (accepted_opportunities 等) |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增 11 个机会建议权重 |

---

## 3. 已实现 Runtime (8 files)

| 文件 | 用途 |
|------|------|
| `runtime/opportunity_trigger_policy.py` | 确定性触发规则 |
| `runtime/opportunity_runtime.py` | 主运行时 (快照 → 证据 → 候选 → 验证 → 排序 → 结果) |
| `runtime/opportunity_query_planner.py` | 查询计划生成 (domain → tool 映射) |
| `runtime/opportunity_candidate_generator.py` | 候选生成 (Fake Adapter) |
| `runtime/opportunity_validator.py` | 候选验证 (拒绝无证据/事件断言/代理权侵犯) |
| `runtime/opportunity_ranker.py` | 确定性排序 + 去重 |
| `runtime/opportunity_adapter.py` | Result → AgentSuggestion 转换 |
| `runtime/opportunity_tool_profile.py` | 工具白名单与角色规格 |

### 修改 Runtime (2 files)

| 文件 | 变更 |
|------|------|
| `runtime/agent_runtime_registry.py` | 注册 `opportunity` 角色 |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增机会权重 |

---

## 4. ComfyUI 节点 (7 nodes)

| 节点 ID | 显示名称 | 函数 |
|---------|----------|------|
| `AWPV2OpportunityTrigger` | AWP V2 戏剧机会触发 | evaluate |
| `AWPV2OpportunityRequest` | AWP V2 戏剧机会请求 | build |
| `AWPV2OpportunityAgent` | AWP V2 戏剧机会Agent | run |
| `AWPV2OpportunityValidator` | AWP V2 戏剧机会验证 | validate |
| `AWPV2OpportunityRanker` | AWP V2 戏剧机会排序 | rank |
| `AWPV2OpportunityResult` | AWP V2 戏剧机会结果 | output |
| `AWPV2OpportunityDiagnostics` | AWP V2 戏剧机会诊断 | diagnose |

### 官方工作流

`workflows/official_opportunity_agent_v2.json`

节点图:
```
Memory Recall → RoundSnapshot → DirectorPlan
→ OpportunityTrigger → OpportunityAgent → OpportunityValidator → OpportunityRanker
                                    ↓
                              SuggestionMerge → FinalTurnBrief → Writer → Quality / Commit
```

no-op 路径:
```
shouldTrigger = false → 空 OpportunityResult(NO_TRIGGER) → SuggestionMerge 正常完成 → Writer 正常继续
```

---

## 5. 权限边界

### OpportunityRoleSpec

```
can_delegate = False
can_write_state = False
can_write_memory = False
can_generate_final_text = False
can_create_event = False
can_advance_timeline = False
can_modify_relationships = False
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

### 应触发场景

| 规则 | 匹配方式 | 风险等级 |
|------|----------|----------|
| 玩家犹豫/试探/回避/追问 | 关键词正则 | low |
| Director 标记未解决线索 | 字段检查 | medium |
| Director 标记关系张力 | 字段检查 | medium |
| Director 标记场景压力 | 字段检查 | medium |
| Director 标记叙事机会 | 字段检查 | low |
| 历史回查发现连续性风险 | 字段检查 | medium |
| 活跃记忆含 promise/secret/misunderstanding/future_hook | kind 检查 | low |
| RAG 含 unresolved_thread/foreshadowing | kind 检查 | low |
| 连续多回合缺少叙事变化 | 输出模式检查 | low |

### 不应触发场景

1. 玩家明确要求纯信息问答
2. 玩家输入无任何机会信号
3. 当前无未解决线索、无关系张力、无记忆信号

---

## 7. OpportunityKind 种类

| kind | 说明 | 优先级权重 |
|------|------|-----------|
| `promise_pressure` | 未兑现承诺 | 0.95 |
| `secret_pressure` | 旧秘密压力 | 0.90 |
| `relationship_tension` | 关系张力 | 0.85 |
| `misunderstanding_pressure` | 误会压力 | 0.82 |
| `goal_reactivation` | 目标重激活 | 0.78 |
| `scene_pressure` | 场景压力 | 0.72 |
| `emotional_shift` | 情绪转变 | 0.70 |
| `choice_opening` | 选择空间 | 0.65 |
| `foreshadowing_echo` | 伏笔回声 | 0.60 |
| `pace_variation` | 节奏变化 | 0.55 |
| `thread_recall` | 线索回忆 | 0.50 |

---

## 8. NarrativeFunction 种类

| function | 说明 |
|----------|------|
| `increase_tension` | 增加张力 |
| `create_choice_space` | 创建选择空间 |
| `deepen_characterization` | 深化角色塑造 |
| `surface_unresolved_thread` | 浮现未解决线索 |
| `soften_transition` | 柔化过渡 |
| `create_emotional_subtext` | 创建情感潜文本 |
| `prepare_future_hook` | 准备未来钩子 |
| `avoid_repetition` | 避免重复 |

---

## 9. 候选验证规则

OpportunityValidator 拒绝以下候选:

| 规则 | 错误类型 |
|------|----------|
| 无 evidence_refs | missing_evidence |
| 无 foundation_facts | missing_foundation |
| mustNotAssertAsFact ≠ True | assertion_violation |
| 包含"已经发生/突然闯入"等事件断言 | event_assertion |
| 包含"修改状态/推进时间"等状态修改请求 | state_modification |
| 包含"玩家接受/代替玩家"等代理权侵犯 | player_agency |
| player_agency_risk > 0.5 | high_agency_risk |
| 包含 memory_commit / rag_commit 指令 | memory_commit |

---

## 10. 排序规则

OpportunityRanker 确定性排序:

```
score = kind_weight * 0.30
      + relevance_score * 0.25
      + confidence * 0.20
      + novelty_score * 0.10
      + (1.0 - player_agency_risk) * 0.10
      + (1.0 - continuity_risk) * 0.05
```

- 默认最多返回 2 个可采纳候选
- 去重: 同 kind + 同 focus_entities 的候选只保留最高分的一个
- 超出 max_accepted 的候选标记为 "outranked"，不是 policy violation

---

## 11. 与 SuggestionMerge / FinalTurnBrief / Writer 的接入

### OpportunityResult → AgentSuggestion

每个采纳的 OpportunityCandidate 转换为一个 AgentSuggestion。
每个被拒绝的候选（policy violation）生成一个 OPPORTUNITY_WARNING 警告。

### FinalTurnBrief 新增字段

```python
accepted_opportunities: list[dict]      # 已采纳机会
rejected_opportunities: list[dict]      # 被拒绝机会
opportunity_warnings: list[str]         # 警告信息
opportunity_evidence_refs: list[str]    # 证据引用
```

### Writer 规则

- Writer 只读取 FinalTurnBrief 中已采纳的机会
- Writer 必须将机会视为"可自然使用的叙事入口"
- Writer 不得将机会视为"必须发生的剧情事件"
- Writer 无法读取原始 OpportunityResult

---

## 12. no-op / 降级 / 失败行为

| 场景 | 行为 |
|------|------|
| shouldTrigger = false | status = NO_TRIGGER，空候选，SuggestionMerge 正常完成 |
| 无有效候选 | status = DEGRADED，degraded_reasons 记录原因 |
| 所有候选被验证拒绝 | status = DEGRADED，rejected_candidates 记录每个拒绝原因 |
| 候试被 outranked | 正常淘汰，不标记为 policy violation |
| Tool timeout | Gateway 返回 degraded，主链继续 |
| Runtime 失败 | 不阻断主链，Writer 不假设获得机会建议 |

---

## 13. 测试命令与真实结果

```bash
python -m pytest tests/ -v
```

```
============================= 318 passed in 1.83s ==============================
```

| 测试集 | 数量 | 状态 |
|--------|------|------|
| P1 tests | 55 | ✅ 全部通过 |
| P2 tests | 51 | ✅ 全部通过 |
| M1 tests | 10+ | ✅ 全部通过 |
| C1 tests | 34 | ✅ 全部通过 |
| D1 tests | 40 | ✅ 全部通过 |
| **D2 tests** | **40** | **✅ 全部通过** |
| **总计** | **318** | **✅ 全部通过** |

### D2 测试明细

| 测试类 | 数量 | 覆盖内容 |
|--------|------|----------|
| TestTriggerPolicy | 6 | 无风险/承诺触发/秘密触发/future_hook/强计划/禁止凑数 |
| TestOpportunityValidator | 6 | 无证据/冲突/代理权/事件伪装/自动推进 |
| TestOpportunityPermissions | 7 | Store/跨cardId/未授权工具/不可委派/不可写状态/不可写内存/不可生成正文 |
| TestOpportunityRanker | 3 | 最多2个/高证据优先/去重 |
| TestSuggestionMergeOpportunity | 3 | 软Guidance/仅采纳/Writer不可读原始Result |
| TestNoOpPath | 1 | no-op路径完成 |
| TestToolFailureBehavior | 1 | timeout降级 |
| TestD2WorkflowValidation | 1 | 官方workflow JSON校验 |
| TestD2NodeRegistration | 2 | 节点注册/中文显示名 |
| TestD2ContractSerialization | 7 | 所有D2合同序列化/反序列化 |
| TestOpportunityAdapter | 1 | Result→AgentSuggestion 转换 |
| TestD2E2ENormalPath | 1 | 完整机会采纳路径 |
| TestD2E2EViolationDegradation | 1 | 违规候选与降级路径 |

---

## 14. 机会与事件的区别

| 维度 | Opportunity (允许) | Event (禁止) |
|------|-------------------|-------------|
| 本质 | 已有事实基础上的叙事入口 | 已经发生、修改世界的事实 |
| 状态影响 | 无 | 修改 CardState/关系/时间线 |
| 玩家代理 | 不代替玩家选择 | 代替玩家做决定 |
| 表述方式 | "可以/或许/可能" | "已经/将会/自动" |
| 证据要求 | 必须回溯到已有数据 | - |
| Writer 使用 | 可选的叙事入口 | 必须执行的剧情 |

---

## 15. 已知限制

1. CandidateGenerator 使用 Fake Adapter（确定性生成），未使用真实 LLM
2. Query Planner 生成查询但未实际通过 ToolGateway 执行（Snapshot 模式直接收集证据）
3. Trigger Policy 使用简单正则，不支持同义词扩展
4. 排序算法基于固定权重，不支持动态调整
5. 去重仅基于 kind + focus_entities，不支持语义去重
6. Validator 使用正则模式匹配事件断言，可能遗漏变体表述

---

## 16. 下一阶段推荐接入点

### D3: World-Life Agent

- 可复用 DynamicSubAgentPool + AgentRuntimeRegistry 模式
- 可复用 ToolGateway + ToolPermissionPolicy
- 可复用 SuggestionMerge + FinalTurnBrief 接入方式
- 需要新增 `world-life` 角色和对应的 SuggestionKind

### 推荐接入步骤

1. 注册 `world-life` 角色到 AgentRuntimeRegistry
2. 实现 WorldLifeTriggerPolicy
3. 实现 WorldLifeRuntime
4. 新增合同 (WorldLifeRequest, WorldLifeResult)
5. 转换为 AgentSuggestion → SuggestionMerge → FinalTurnBrief

---

## 17. 禁止回归的架构约束

1. **OpportunityAgent 不得写 CardState / TurnRecord / ActiveMemory / RAG**
2. **OpportunityAgent 不得委派子 Agent**
3. **OpportunityAgent 不得生成最终玩家正文**
4. **OpportunityAgent 不得创建事件或推进时间线**
5. **所有工具调用必须经过 ToolGateway**
6. **未注册工具一律拒绝**
7. **无 evidence 的候选不得被采纳**
8. **机会不得伪装成已发生事件**
9. **机会不得代替玩家做选择**
10. **Writer 只能读取 WriterInputBundle 中已采纳的机会**
11. **QualityGate reject 时零副作用**
12. **no-op 路径必须能完成正式回合**
