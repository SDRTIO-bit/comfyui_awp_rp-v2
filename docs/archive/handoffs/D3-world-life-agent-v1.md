# D3: World-Life Agent V1 — Handoff

**日期:** 2026-06-27
**Branch:** master
**HEAD:** ba947f6 (pre-commit, working tree has D3 changes)
**Tag:** (to be created as `d3-world-life-agent-v1`)

---

## 1. 本阶段目标

实现第三个正式动态子 Agent：World-Life Agent。

基于当前 RoundSnapshot、场景环境、活跃 NPC、事件阶段、世界书和已确认记忆，
识别"世界在主角视线之外可能发生什么"的环境变化、NPC 侧动向和事件压力候选。

**World-Life Candidate ≠ World Event。**
World-Life Agent 只能提出不强制发生的环境变化候选，不能生成事件、修改状态或推进时间线。

---

## 2. 已实现合同 (7 files)

| 文件 | schemaId | 用途 |
|------|----------|------|
| `contracts/world_life_request.py` | `awp.rp.world-life-request.v1` | 世界活性分析请求 |
| `contracts/world_life_candidate.py` | `awp.rp.world-life-candidate.v1` | 单个世界活性候选 |
| `contracts/world_life_evidence.py` | `awp.rp.world-life-evidence.v1` | 证据引用 |
| `contracts/world_life_result.py` | `awp.rp.world-life-result.v1` | 分析结果 |
| `contracts/world_life_risk.py` | `awp.rp.world-life-risk.v1` | 风险评估 |
| `contracts/world_life_suggestion.py` | `awp.rp.world-life-suggestion.v1` | 结构化建议 |
| `contracts/world_life_trigger_diagnostics.py` | `awp.rp.world-life-trigger-diagnostics.v1` | 触发诊断 |

### 修改合同 (3 files)

| 文件 | 变更 |
|------|------|
| `contracts/agent_suggestion.py` | 新增 10 个 SuggestionKind (ENVIRONMENTAL_PRESSURE 等) |
| `contracts/final_turn_brief.py` | 新增 4 个世界活性字段 (accepted_world_life_candidates 等) |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增 10 个世界活性建议权重 |

---

## 3. 已实现 Runtime (8 files)

| 文件 | 用途 |
|------|------|
| `runtime/world_life_trigger_policy.py` | 确定性触发规则 |
| `runtime/world_life_runtime.py` | 主运行时 (快照 → 证据 → 候选 → 验证 → 排序 → 结果) |
| `runtime/world_life_query_planner.py` | 查询计划生成 (domain → tool 映射) |
| `runtime/world_life_candidate_generator.py` | 候选生成 (Fake Adapter) |
| `runtime/world_life_validator.py` | 候选验证 (拒绝无证据/事件断言/代理权侵犯/自动推进) |
| `runtime/world_life_ranker.py` | 确定性排序 + 去重 |
| `runtime/world_life_adapter.py` | Result → AgentSuggestion 转换 |
| `runtime/world_life_tool_profile.py` | 工具白名单与角色规格 |

### 修改 Runtime (3 files)

| 文件 | 变更 |
|------|------|
| `runtime/agent_runtime_registry.py` | 注册 `world-life` 角色 |
| `runtime/tool_registry.py` | 注册 `event_stage_lookup`, `scene_context_lookup`, `npc_context_lookup` |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增世界活性权重 |

---

## 4. ComfyUI 节点 (7 nodes)

| 节点 ID | 显示名称 | 函数 |
|---------|----------|------|
| `AWPV2WorldLifeTrigger` | AWP V2 世界活性触发 | evaluate |
| `AWPV2WorldLifeRequest` | AWP V2 世界活性请求 | build |
| `AWPV2WorldLifeAgent` | AWP V2 世界活性Agent | run |
| `AWPV2WorldLifeValidator` | AWP V2 世界活性验证 | validate |
| `AWPV2WorldLifeRanker` | AWP V2 世界活性排序 | rank |
| `AWPV2WorldLifeResult` | AWP V2 世界活性结果 | output |
| `AWPV2WorldLifeDiagnostics` | AWP V2 世界活性诊断 | diagnose |

### 官方工作流

`workflows/official_world_life_agent_v2.json`

节点图:
```
Memory Recall → RoundSnapshot → DirectorPlan
→ WorldLifeTrigger → WorldLifeAgent → WorldLifeValidator → WorldLifeRanker
                                    ↓
                              SuggestionMerge → FinalTurnBrief → Writer → Quality / Commit
```

no-op 路径:
```
shouldTrigger = false → 空 WorldLifeResult(NO_TRIGGER) → SuggestionMerge 正常完成 → Writer 正常继续
```

---

## 5. 权限边界

### WorldLifeRoleSpec

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
| `worldbook_lookup` | 无 | ❌ | ❌ | ❌ |
| `timeline_lookup` | 无 | ❌ | ❌ | ❌ |
| `relationship_context_lookup` | 无 | ❌ | ❌ | ❌ |
| `accepted_turn_lookup` | 无 | ❌ | ❌ | ❌ |
| `active_memory_lookup` | 无 | ❌ | ❌ | ❌ |
| `rag_memory_lookup` | 无 | ❌ | ❌ | ❌ |
| `entity_alias_lookup` | 无 | ❌ | ❌ | ❌ |
| `event_stage_lookup` | 无 | ❌ | ❌ | ❌ |
| `scene_context_lookup` | 无 | ❌ | ❌ | ❌ |
| `npc_context_lookup` | 无 | ❌ | ❌ | ❌ |

---

## 6. Trigger Policy 触发条件

### 应触发场景

| 规则 | 匹配方式 | 风险等级 |
|------|----------|----------|
| 场景存在环境特征、天气、时间压力 | 关键词正则 | low |
| 地点具有可描写的空间氛围 | 关键词正则 | low |
| NPC 侧压力信号 | 关键词正则 | low |
| 事件阶段或进展信号 | 关键词正则 | medium |
| 世界书与当前地点/时间相关 | 内容检查 | low |
| DirectorPlan 指示需要世界在场感 | 字段检查 | medium |
| 连续多回合叙事过于封闭 | 输出模式检查 | low |
| 活跃记忆包含世界事件 | kind 检查 | low |
| RAG 记忆包含世界背景 | kind 检查 | low |

### 不应触发场景

1. 纯事实澄清、状态修复、重试、错误恢复
2. 当前 CardState 或历史事实存在未解决冲突
3. 玩家明确要求极简、纯信息、跳过描写的回应
4. 触发后只能通过编造新事件或新 NPC 才能产生建议
5. 当前回合已经有足够世界反应，继续添加会造成噪声
6. 当前场景需要高度专注于玩家明确的紧急行动
7. 仅为了增加子 Agent 调用次数

---

## 7. WorldLifeKind 种类

| kind | 说明 | 优先级权重 |
|------|------|-----------|
| `environmental_pressure` | 环境压力 | 0.85 |
| `weather_or_time_atmosphere` | 天气/时间氛围 | 0.80 |
| `npc_side_tension` | NPC 侧张力 | 0.78 |
| `event_stage_echo` | 事件阶段回声 | 0.75 |
| `location_life_detail` | 地点生命力细节 | 0.72 |
| `worldbook_resonance` | 世界书共振 | 0.70 |
| `social_background_signal` | 社会背景信号 | 0.65 |
| `scene_transition_pressure` | 场景过渡压力 | 0.60 |
| `offscreen_consequence_hint` | 画外后果暗示 | 0.55 |
| `ambient_rumor_signal` | 环境传闻信号 | 0.50 |

---

## 8. WorldLayer 种类

| layer | 说明 |
|-------|------|
| `environment` | 环境层 |
| `location` | 地点层 |
| `npc` | NPC 层 |
| `event_stage` | 事件阶段层 |
| `social_world` | 社会世界层 |
| `worldbook` | 世界书层 |
| `offscreen` | 画外层 |

---

## 9. VisibilityMode 种类

| mode | 说明 |
|------|------|
| `background` | 背景描写 |
| `subtle_signal` | 微妙信号 |
| `optional_dialogue_color` | 可选对话色彩 |
| `optional_action_cue` | 可选动作提示 |
| `director_only_warning` | 仅 Director 可见警告 |

---

## 10. 候选验证规则

WorldLifeValidator 拒绝以下候选:

| 规则 | 错误类型 |
|------|----------|
| 无 evidence_refs | missing_evidence |
| 无 foundation_facts | missing_foundation |
| mustNotAssertAsFact ≠ True | assertion_violation |
| mustNotCommitState ≠ True | state_commit |
| 包含"已经发生/突然闯入"等事件断言 | event_assertion |
| 包含"修改状态/推进时间/自动推进"等状态修改请求 | state_modification |
| 包含"玩家接受/代替玩家"等代理权侵犯 | player_agency |
| 包含"事件已经/关系已经/自动进入"等自动推进 | auto_advance |
| player_agency_risk > 0.5 | high_agency_risk |
| state_change_risk > 0.1 | high_state_risk |
| 包含 memory_commit / rag_commit 指令 | memory_commit |

---

## 11. 排序规则

WorldLifeRanker 确定性排序:

```
score = kind_weight * 0.30
      + relevance_score * 0.25
      + confidence * 0.20
      + novelty_score * 0.10
      + (1.0 - player_agency_risk) * 0.10
      + (1.0 - continuity_risk) * 0.05
```

- 默认最多返回 2 个可采纳候选
- 去重: 同 kind + 同 focus_entities + 同 focus_location 的候选只保留最高分的一个
- 超出 max_accepted 的候选标记为 "outranked"，不是 policy violation

---

## 12. 与 SuggestionMerge / FinalTurnBrief / Writer 的接入

### WorldLifeResult → AgentSuggestion

每个采纳的 WorldLifeCandidate 转换为一个 AgentSuggestion。
每个被拒绝的候选（policy violation）生成一个 WORLD_LIFE_WARNING 警告。

### FinalTurnBrief 新增字段

```python
accepted_world_life_candidates: list[dict]      # 已采纳世界活性候选
rejected_world_life_candidates: list[dict]      # 被拒绝世界活性候选
world_life_warnings: list[str]                  # 警告信息
world_life_evidence_refs: list[str]             # 证据引用
```

### Writer 规则

- Writer 只读取 FinalTurnBrief 中已采纳的世界活性候选
- Writer 必须将候选视为"可自然显现的背景、压力、动作前兆或场景质感"
- Writer 不得将候选视为"已经发生且必须强行写入的世界事件"
- Writer 无法读取原始 WorldLifeResult

---

## 13. no-op / 降级 / 失败行为

| 场景 | 行为 |
|------|------|
| shouldTrigger = false | status = NO_TRIGGER，空候选，SuggestionMerge 正常完成 |
| 无有效候选 | status = DEGRADED，degraded_reasons 记录原因 |
| 所有候选被验证拒绝 | status = DEGRADED，rejected_candidates 记录每个拒绝原因 |
| 候选被 outranked | 正常淘汰，不标记为 policy violation |
| Tool timeout | Gateway 返回 degraded，主链继续 |
| Runtime 失败 | 不阻断主链，Writer 不假设获得世界活性建议 |

---

## 14. 世界活性候选与既成事件的区别

| 维度 | World-Life Candidate (允许) | World Event (禁止) |
|------|---------------------------|-------------------|
| 本质 | 已有事实基础上的环境/氛围/压力提示 | 已经发生、修改世界的事实 |
| 状态影响 | 无 | 修改 CardState/关系/时间线 |
| 玩家代理 | 不代替玩家选择 | 代替玩家做决定 |
| 表述方式 | "可以/或许/可能显现" | "已经/将会/自动发生" |
| 证据要求 | 必须回溯到已有数据 | - |
| Writer 使用 | 可选的背景/氛围/压力 | 必须执行的剧情 |

### 允许的候选示例

- 已知雨势持续增强，可以在环境描写中体现湿冷、屋檐滴水或道路泥泞
- 已知 NPC 正处于事件阶段，可让其语气、停顿、出场前兆带有压力
- 已知节日、集市、宵禁或宗族活动临近，可作为远景噪声、环境气氛
- 已有冲突尚未解决，可让场景中出现克制、旁观者反应或未说出口的压力
- 已知地点的规则、氛围、声响、气味或人流可自然进入描写

### 禁止的候选示例

- "某 NPC 已经决定背叛并离开"
- "陌生 NPC 突然闯入并改变剧情"
- "三天自动过去，事件阶段自动推进"
- "玩家被迫前往某地"
- "关系值已经变化"
- "秘密已经曝光"

---

## 15. 测试命令与真实结果

```bash
python -m pytest tests/ -v
```

```
============================= 359 passed in 2.07s ==============================
```

| 测试集 | 数量 | 状态 |
|--------|------|------|
| P1 tests | 55 | ✅ 全部通过 |
| P2 tests | 51 | ✅ 全部通过 |
| M1 tests | 10+ | ✅ 全部通过 |
| C1 tests | 34 | ✅ 全部通过 |
| D1 tests | 40 | ✅ 全部通过 |
| D2 tests | 40 | ✅ 全部通过 |
| **D3 tests** | **41** | **✅ 全部通过** |
| **总计** | **359** | **✅ 全部通过** |

### D3 测试明细

| 测试类 | 数量 | 覆盖内容 |
|--------|------|----------|
| TestTriggerPolicy | 6 | 无风险/环境触发/NPC压力/世界书/重试恢复/禁止凑数 |
| TestWorldLifeValidator | 7 | 无证据/冲突/代理权/事件伪装/自动推进时间/自动推进事件 |
| TestWorldLifePermissions | 7 | Store/跨cardId/未授权工具/不可委派/不可写状态/不可写内存/不可生成正文 |
| TestWorldLifeRanker | 3 | 最多2个/高证据优先/去重 |
| TestSuggestionMergeWorldLife | 3 | 软Guidance/仅采纳/Writer不可读原始Result |
| TestNoOpPath | 1 | no-op路径完成 |
| TestToolFailureBehavior | 1 | timeout降级 |
| TestD3WorkflowValidation | 1 | 官方workflow JSON校验 |
| TestD3NodeRegistration | 2 | 节点注册/中文显示名 |
| TestD3ContractSerialization | 7 | 所有D3合同序列化/反序列化 |
| TestWorldLifeAdapter | 1 | Result→AgentSuggestion 转换 |
| TestD3E2ENormalPath | 1 | 完整世界活性采纳路径 |
| TestD3E2EViolationDegradation | 1 | 违规候选与降级路径 |

---

## 16. 已知限制

1. CandidateGenerator 使用 Fake Adapter（确定性生成），未使用真实 LLM
2. Query Planner 生成查询但未实际通过 ToolGateway 执行（Snapshot 模式直接收集证据）
3. Trigger Policy 使用简单正则，不支持同义词扩展
4. 排序算法基于固定权重，不支持动态调整
5. 去重仅基于 kind + focus_entities + focus_location，不支持语义去重
6. Validator 使用正则模式匹配事件断言，可能遗漏变体表述

---

## 17. 下一阶段推荐接入点

### D4: Emotion / Relationship Agent

- 可复用 DynamicSubAgentPool + AgentRuntimeRegistry 模式
- 可复用 ToolGateway + ToolPermissionPolicy
- 可复用 SuggestionMerge + FinalTurnBrief 接入方式
- 需要新增 `emotion-relationship` 角色和对应的 SuggestionKind

### 推荐接入步骤

1. 注册 `emotion-relationship` 角色到 AgentRuntimeRegistry
2. 实现 EmotionRelationshipTriggerPolicy
3. 实现 EmotionRelationshipRuntime
4. 新增合同 (EmotionRelationshipRequest, EmotionRelationshipResult)
5. 转换为 AgentSuggestion → SuggestionMerge → FinalTurnBrief

---

## 18. 禁止回归的架构约束

1. **WorldLifeAgent 不得写 CardState / TurnRecord / ActiveMemory / RAG**
2. **WorldLifeAgent 不得委派子 Agent**
3. **WorldLifeAgent 不得生成最终玩家正文**
4. **WorldLifeAgent 不得创建事件或推进时间线**
5. **WorldLifeAgent 不得修改关系或场景**
6. **所有工具调用必须经过 ToolGateway**
7. **未注册工具一律拒绝**
8. **无 evidence 的候选不得被采纳**
9. **世界活性不得伪装成已发生事件**
10. **世界活性不得自动推进时间、事件阶段或关系**
11. **Writer 只能读取 WriterInputBundle 中已采纳的世界活性候选**
12. **QualityGate reject 时零副作用**
13. **no-op 路径必须能完成正式回合**
