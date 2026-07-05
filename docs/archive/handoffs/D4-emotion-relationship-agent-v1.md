# D4: Emotion / Relationship Agent V1 — Handoff

**日期:** 2026-06-27
**Branch:** d4-emotion-relationship-agent-v1
**HEAD:** (pre-commit, working tree has D4 changes)
**Tag:** (to be created as `d4-emotion-relationship-agent-v1`)

---

## 1. 本阶段目标

实现第四个正式动态子 Agent：Emotion / Relationship Agent。

基于当前 RoundSnapshot、已确认关系事实、近忆、活跃记忆与当前输入，
识别人物之间的信任、戒备、愧疚、试探、嫉妒、压抑、靠近、回避等关系张力，
提出 Writer 可以选择性使用的情绪与关系建议。

**Relationship Interpretation ≠ Relationship Event。**
本 Agent 只能输出对现有事实支持的关系与情绪状态进行分析，不能断言关系变化已发生。

---

## 2. 已实现合同 (7 files)

| 文件 | schemaId | 用途 |
|------|----------|------|
| `contracts/emotion_relationship_candidate.py` | `awp.rp.emotion-relationship-candidate.v1` | 关系/情绪候选 |
| `contracts/relationship_evidence.py` | `awp.rp.relationship-evidence.v1` | 证据引用 |
| `contracts/emotion_relationship_request.py` | `awp.rp.emotion-relationship-request.v1` | 分析请求 |
| `contracts/emotion_relationship_result.py` | `awp.rp.emotion-relationship-result.v1` | 分析结果 |
| `contracts/relationship_risk.py` | `awp.rp.relationship-risk.v1` | 风险评估 |
| `contracts/emotion_relationship_suggestion.py` | `awp.rp.emotion-relationship-suggestion.v1` | 结构化建议 |
| `contracts/emotion_relationship_trigger_diagnostics.py` | `awp.rp.emotion-relationship-trigger-diagnostics.v1` | 触发诊断 |

### 修改合同 (2 files)

| 文件 | 变更 |
|------|------|
| `contracts/agent_suggestion.py` | 新增 12 个 SuggestionKind (ER_TRUST_TENSION 等) |
| `contracts/final_turn_brief.py` | 新增 4 个关系字段 (accepted_relationship_findings 等) |

---

## 3. 已实现 Runtime (8 files)

| 文件 | 用途 |
|------|------|
| `runtime/emotion_relationship_trigger_policy.py` | 确定性触发规则 |
| `runtime/emotion_relationship_runtime.py` | 主运行时 (快照 → 证据 → 候选 → 验证 → 排序 → 结果) |
| `runtime/emotion_relationship_query_planner.py` | 查询计划生成 (domain → tool 映射) |
| `runtime/emotion_relationship_candidate_generator.py` | 候选生成 (Fake Adapter) |
| `runtime/emotion_relationship_validator.py` | 候选验证 (拒绝无证据/关系事件/代理权侵犯) |
| `runtime/emotion_relationship_ranker.py` | 确定性排序 + 去重 |
| `runtime/emotion_relationship_adapter.py` | Result → AgentSuggestion 转换 |
| `runtime/emotion_relationship_tool_profile.py` | 工具白名单与角色规格 |

### 修改 Runtime (2 files)

| 文件 | 变更 |
|------|------|
| `runtime/agent_runtime_registry.py` | 注册 `emotion-relationship` 角色 |
| `runtime/suggestion_merger.py` | KIND_WEIGHTS 新增 12 个关系建议权重 |

---

## 4. ComfyUI 节点 (7 nodes)

| 节点 ID | 显示名称 | 函数 |
|---------|----------|------|
| `AWPV2EmotionRelationshipTrigger` | AWP V2 情绪关系触发 | evaluate |
| `AWPV2EmotionRelationshipRequest` | AWP V2 情绪关系请求 | build |
| `AWPV2EmotionRelationshipAgent` | AWP V2 情绪关系Agent | run |
| `AWPV2EmotionRelationshipValidator` | AWP V2 情绪关系验证 | validate |
| `AWPV2EmotionRelationshipRanker` | AWP V2 情绪关系排序 | rank |
| `AWPV2EmotionRelationshipResult` | AWP V2 情绪关系结果 | output |
| `AWPV2EmotionRelationshipDiagnostics` | AWP V2 情绪关系诊断 | diagnose |

### 官方工作流

`workflows/official_emotion_relationship_agent_v2.json`

节点图:
```
RoundSnapshot → DirectorPlan
→ EmotionRelationshipTrigger → EmotionRelationshipAgent
→ EmotionRelationshipValidator → EmotionRelationshipRanker
                                    ↓
                              SuggestionMerge → FinalTurnBrief → Writer
```

---

## 5. 权限边界

### EmotionRelationshipRoleSpec

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

### 应触发场景

| 规则 | 匹配方式 | 风险等级 |
|------|----------|----------|
| 关系动作关键词 (承诺/拒绝/靠近/回避/误会/秘密/嫉妒/冲突/和解/道歉/对不起/试探/安慰/质问/冷落/邀请/原谅/背叛/信任/怀疑/表白/好感/敌意/依赖/防备/心虚/生气/在乎/冷淡/疏远) | 正则 | low |
| 情绪关键词 (犹豫/迟疑/欲言又止/沉默/叹气/紧张/期待/担心/害怕/矛盾/纠结/心酸/委屈/失落/温柔/愤怒/伤心/开心/感动/尴尬/不安/心疼/心虚/愧疚/后悔) | 正则 | low |
| ActiveMemory 关系类型 (relationship_shift/misunderstanding/promise/secret/emotional_trend) | kind 检查 | low |
| 近期回合显示情绪/关系变化 | 正则 | low |
| DirectorPlan 要求人物情绪/关系细节 | 字段检查 | medium |
| DirectorPlan 标记关系张力 | 字段检查 | medium |
| 历史回查确认关系事实 | 字段检查 | medium |
| RAG 记忆包含关系内容 | kind 检查 | low |

### 不应触发场景

1. 纯世界观问答
2. 纯物品、地点、数值或机械信息请求
3. 当前回合是状态修复、retry、错误恢复
4. 没有活跃关系对象
5. 触发后只能靠编造情感历史才能给建议
6. 玩家明确要求极简、跳过情绪描写
7. 仅为了增加子 Agent 调用次数

---

## 7. RelationshipKind 种类

| kind | 说明 | 优先级权重 |
|------|------|-----------|
| `relationship_boundary` | 关系边界 | 0.90 |
| `unresolved_hurt` | 未解决伤害 | 0.88 |
| `trust_tension` | 信任张力 | 0.85 |
| `guardedness` | 戒备 | 0.80 |
| `emotional_residue` | 情绪余波 | 0.78 |
| `misunderstanding_signal` | 误会信号 | 0.76 |
| `promise_pressure` | 承诺压力 | 0.75 |
| `jealousy_risk` | 嫉妒风险 | 0.73 |
| `conflict_deescalation` | 冲突降级 | 0.72 |
| `affection_restraint` | 情感克制 | 0.70 |
| `subtext_opportunity` | 潜文本机会 | 0.65 |

---

## 8. 候选验证规则

EmotionRelationshipValidator 拒绝以下候选:

| 规则 | 错误类型 |
|------|----------|
| 无 evidence_refs | missing_evidence |
| 无 foundation_facts | missing_foundation |
| mustNotAssertAsFact ≠ True | assertion_violation |
| mustNotModifyRelationship ≠ True | relationship_modification |
| 包含"已经原谅/已经接受/已经表白/已经背叛/已经和好"等关系事件断言 | relationship_event |
| 包含"突然告白/突然背叛/突然和好/突然翻脸"等突然关系跃迁 | sudden_shift |
| 包含"玩家接受/代替玩家/玩家被默认"等代理权侵犯 | player_agency |
| 包含"关系值.*增加/好感.*增加/修改关系"等关系修改 | relationship_modification |
| 包含"突然升温/突然冷漠/立刻原谅/立刻信任"等突然跃迁 | sudden_shift |
| player_agency_risk > 0.5 | high_agency_risk |
| sudden_shift_risk > 0.5 | high_shift_risk |
| 包含 memory_commit / rag_commit 指令 | memory_commit |

---

## 9. 排序规则

EmotionRelationshipRanker 确定性排序:

```
score = kind_weight * 0.30
      + confidence * 0.25
      + (1.0 - player_agency_risk) * 0.15
      + (1.0 - sudden_shift_risk) * 0.15
      + (1.0 - continuity_risk) * 0.10
      + evidence_bonus * 0.05
```

- 默认最多返回 2 个可采纳候选
- 去重: 同 kind + 同 focus_entities 的候选只保留最高分的一个
- 超出 max_accepted 的候选标记为 "outranked"

---

## 10. 与 SuggestionMerge / FinalTurnBrief / Writer 的接入

### EmotionRelationshipResult → AgentSuggestion

每个采纳的 EmotionRelationshipCandidate 转换为一个 AgentSuggestion。
被拒绝的候选（player_agency/relationship_event/sudden_shift）生成 ER_WARNING 警告。

### FinalTurnBrief 新增字段

```python
accepted_relationship_findings: list[str]
rejected_relationship_findings: list[dict]
relationship_warnings: list[str]
relationship_evidence_refs: list[str]
```

### Writer 规则

- Writer 只读取 FinalTurnBrief 中已采纳的关系建议
- Writer 必须将建议视为"软性 Writer Guidance"
- Writer 不得将建议视为"已发生的关系事件"
- Writer 无法读取原始 EmotionRelationshipResult

---

## 11. no-op / 降级 / 失败行为

| 场景 | 行为 |
|------|------|
| shouldTrigger = false | status = NO_TRIGGER，空候选，SuggestionMerge 正常完成 |
| 无有效候选 | status = DEGRADED，degraded_reasons 记录原因 |
| 所有候选被验证拒绝 | status = DEGRADED，rejected_candidates 记录每个拒绝原因 |
| 候选被 outranked | 正常淘汰，不标记为 policy violation |
| Tool timeout | Gateway 返回 degraded，主链继续 |
| Runtime 失败 | 不阻断主链，Writer 不假设获得关系建议 |

---

## 12. 测试命令与真实结果

```bash
python -m pytest tests/ -v
```

```
============================= 401 passed in 1.99s ==============================
```

| 测试集 | 数量 | 状态 |
|--------|------|------|
| P1 tests | 55 | ✅ 全部通过 |
| P2 tests | 51 | ✅ 全部通过 |
| M1 tests | 10+ | ✅ 全部通过 |
| C1 tests | 34 | ✅ 全部通过 |
| D1 tests | 40 | ✅ 全部通过 |
| D2 tests | 40 | ✅ 全部通过 |
| **D4 tests** | **40** | **✅ 全部通过** |
| **总计** | **401** | **✅ 全部通过** |

### D4 测试明细

| 测试类 | 数量 | 覆盖内容 |
|--------|------|----------|
| TestTriggerPolicy | 8 | 无风险/承诺/误会/道歉/试探/冲突/秘密/禁止凑数 |
| TestEmotionRelationshipValidator | 6 | 无证据/关系修改/突然表白/代理权/关系事件/必须不修改关系 |
| TestEmotionRelationshipPermissions | 7 | Store/跨cardId/未授权工具/不可委派/不可写状态/不可写内存/不可生成正文 |
| TestEmotionRelationshipRanker | 3 | 最多2个/高证据优先/去重 |
| TestSuggestionMergeEmotionRelationship | 3 | 软Guidance/仅采纳/Writer不可读原始Result |
| TestNoOpPath | 1 | no-op路径完成 |
| TestToolFailureBehavior | 1 | timeout降级 |
| TestD4WorkflowValidation | 1 | 官方workflow JSON校验 |
| TestD4NodeRegistration | 2 | 节点注册/中文显示名 |
| TestD4ContractSerialization | 7 | 所有D4合同序列化/反序列化 |
| TestEmotionRelationshipAdapter | 1 | Result→AgentSuggestion 转换 |
| TestD4E2ENormalPath | 1 | 完整关系建议采纳路径 |
| TestD4E2EViolationDegradation | 1 | 违规候选与降级路径 |

---

## 13. 已知限制

1. CandidateGenerator 使用 Fake Adapter（确定性生成），未使用真实 LLM
2. Query Planner 生成查询但未实际通过 ToolGateway 执行（Snapshot 模式直接收集证据）
3. Trigger Policy 使用简单正则，不支持同义词扩展
4. 排序算法基于固定权重，不支持动态调整
5. 去重仅基于 kind + focus_entities，不支持语义去重
6. Validator 使用正则模式匹配关系事件断言，可能遗漏变体表述

---

## 14. 下一阶段推荐接入点

### D5: Continuity Agent

- 可复用 DynamicSubAgentPool + AgentRuntimeRegistry 模式
- 可复用 ToolGateway + ToolPermissionPolicy
- 可复用 SuggestionMerge + FinalTurnBrief 接入方式
- 需要新增 `continuity` 角色和对应的 SuggestionKind

---

## 15. 禁止回归的架构约束

1. **EmotionRelationshipAgent 不得写 CardState / TurnRecord / ActiveMemory / RAG**
2. **EmotionRelationshipAgent 不得委派子 Agent**
3. **EmotionRelationshipAgent 不得生成最终玩家正文**
4. **EmotionRelationshipAgent 不得修改关系值**
5. **所有工具调用必须经过 ToolGateway**
6. **未注册工具一律拒绝**
7. **无 evidence 的候选不得被采纳**
8. **关系候选不得断言关系变化已发生**
9. **关系候选不得代替玩家做情感选择**
10. **Writer 只能读取 WriterInputBundle 中已采纳的关系建议**
11. **QualityGate reject 时零副作用**
12. **no-op 路径必须能完成正式回合**
