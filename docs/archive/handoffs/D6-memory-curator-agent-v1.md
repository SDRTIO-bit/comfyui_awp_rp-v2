# D6: Memory Curator Agent V1 — Handoff

## 基本信息

- **Branch:** `main`
- **HEAD:** `ac44455` (feat(D6): implement Memory Curator Agent V1)
- **Tag:** `d6-memory-curator-agent-v1`
- **Date:** 2026-06-27
- **Tests:** 497 total (451 existing + 46 D6-specific), all passing
- **Working tree:** clean

---

## 本阶段目标

实现正式动态子 Agent：**Memory Curator Agent**。

核心问题：在本回合已经通过 Quality Gate、CardState 已成功提交、TurnRecord 已成功提交之后，哪些"已经接受的事实"值得进入 ActiveMemory？哪些应沉淀为长期 RagMemory？哪些旧活跃记忆应合并、标记已解决、降级或归档？

---

## 启动核验结果

| 检查项 | 结果 |
|--------|------|
| `git status --short` | clean |
| `git branch --show-current` | `main` |
| `git log --oneline --decorate -n 5` | d5-continuity-agent-v1 is HEAD |
| `git tag --sort=-creatordate` | d1 through d5 present |
| `docs/reference/` | 目录不存在（架构原文缺失，如实报告） |
| 残留 Memory Curator 接口 | `memory-curator` role 存在于 BUILTIN_ROLES，仅 `MEMORY_CANDIDATE` kind，已更新 |
| 现有 MemoryCommitPlan | 存在且完整，复用而非重建 |
| 现有 MemoryCommitRuntime | ActiveMemoryCommitRuntime + RagMemoryCommitRuntime，复用 |
| TurnRecordCommit 完成时机 | QualityGate ACCEPT 后，Memory Commit 前 |
| retry/continue/resume 重复写风险 | 通过 `existing_curated_turn_ids` 幂等检查解决 |

---

## 现有 Memory Runtime 的复用方式

- **MemoryCommitPlan** (`contracts/memory_commit_plan.py`): 直接复用，不创建同名第二套
- **ActiveMemoryCommitRuntime** (`runtime/active_memory_commit_runtime.py`): 直接复用，8-step gate + retention
- **RagMemoryCommitRuntime** (`runtime/rag_memory_commit_runtime.py`): 直接复用，scope safety + idempotency
- **MemoryPolicy** (`policies/memory_policy.py`): 直接复用，validate_commit_plan + retention_score
- **ActiveMemoryRecord / RagMemoryRecord**: 直接复用，不修改 schema

---

## 新增合同

| 合同 | Schema ID | 用途 |
|------|-----------|------|
| `memory_curation_trigger_diagnostics` | `awp.rp.memory-curation-trigger-diagnostics.v1` | 触发策略输出 |
| `memory_curation_request` | `awp.rp.memory-curation-request.v1` | Curator 正式输入 |
| `memory_curation_candidate` | `awp.rp.memory-curation-candidate.v1` | 单条记忆操作提议 |
| `memory_curation_evidence` | `awp.rp.memory-curation-evidence.v1` | 候选的证据绑定 |
| `memory_curation_result` | `awp.rp.memory-curation-result.v1` | Curator 最终输出 |

---

## 新增运行时

| 运行时 | 职责 |
|--------|------|
| `memory_curation_trigger_policy` | 确定性触发规则：QualityGate=ACCEPT + CardStateCommit=SUCCESS + TurnRecordCommit=SUCCESS + 信号检测 |
| `memory_curation_runtime` | 编排器：trigger → request → query plan → adapter → result |
| `memory_curation_query_planner` | 确定性查询规划：focus entities, focus kinds, domains |
| `memory_candidate_generator` | Fake 模式确定性候选生成：RAG + active update/resolve + active create |
| `memory_curation_validator` | 确定性验证：evidence/source/summary length/prohibitions |
| `memory_curation_ranker` | 确定性排序：operation weight + kind importance + importance + confidence |
| `memory_plan_compiler` | 候选 → MemoryCommitPlan 转换 |
| `memory_curator_adapter` | Fake 适配器：generator + validator + ranker 管线 |
| `memory_curator_tool_profile` | 6 个只读工具白名单 |

---

## Memory Curator Runtime 执行流程

```
AcceptedTurnRecord
+ QualityDecision(ACCEPT)
+ CardStateCommit(SUCCESS)
+ TurnRecordCommit(SUCCESS)
+ RoundSnapshot (active_memories + rag_recall)
    ↓
MemoryCurationTriggerPolicy.evaluate()
    ↓ (should_trigger=true)
MemoryCurationRequest
    ↓
MemoryCurationQueryPlanner.plan()
    ↓
FakeMemoryCuratorAdapter.curate()
  ├── FakeMemoryCandidateGenerator.generate()
  ├── MemoryCurationValidator.validate_all()
  └── MemoryCurationRanker.rank()
    ↓
MemoryCurationResult
    ↓
MemoryPlanCompiler.compile()
    ↓
MemoryCommitPlan → ActiveMemoryCommitRuntime + RagMemoryCommitRuntime
```

---

## 触发规则

### 应触发（should_trigger=true）
1. 回合包含承诺/约定信号（`答应/承诺/保证/约定` 等）
2. 回合包含秘密/隐瞒信号（`秘密/隐瞒/隐藏/真相` 等）
3. 回合包含关系变化信号（`关系/信任/怀疑/和解` 等）
4. 回合包含目标/意图信号（`目标/计划/决定/决心` 等）
5. 回合包含事件阶段变化（`事件/阶段/进展/转折` 等）
6. 回合包含长期影响信号（`永远/长期/从此/改变` 等）
7. 活跃记忆接近上限（≥14/15）
8. 回合推进了既有活跃记忆（实体匹配 + kind 为 promise/secret 等）
9. CardState 已变更

### 不应触发（should_trigger=false）
1. Quality Gate reject
2. CardStateCommit 失败
3. TurnRecordCommit 失败
4. 该 turnId 已成功 curated（幂等）
5. 回合仅含无长期影响的闲聊
6. turnId/cardId/sessionId 无效

### no-op 路径
- `should_trigger=false` → 空 MemoryCurationResult → 空 MemoryCommitPlan → 不调用 MemoryCommitRuntime → 回合正常完成

---

## accepted-only 安全边界

| 约束 | 值 |
|------|-----|
| `must_use_accepted_facts_only` | `True`（固定） |
| `must_not_create_facts` | `True`（固定） |
| `must_not_write_storage` | `True`（固定） |
| `can_delegate` | `False` |
| `can_write_state` | `False` |
| `can_write_memory` | `False` |
| `can_generate_final_text` | `False` |

---

## ActiveMemory 15 条限制与排序规则

### 排序优先级
1. `MARK_RESOLVED` (0.95) — 释放槽位
2. `UPDATE_ACTIVE` (0.85) — 更新已有
3. `MERGE_ACTIVE` (0.80) — 合并重复
4. `CREATE_ACTIVE` (0.70) — 新建
5. `ARCHIVE_ACTIVE_TO_RAG` (0.65) — 归档

### Kind 重要度
- promise (0.95) > secret (0.90) > relationship_shift (0.85) > misunderstanding (0.82) > player_goal (0.78) > scene_pressure (0.72) > unresolved_thread (0.70)

### 超限处理
- RESOLVE 优先（释放槽位）
- 满时 CREATE 被拒绝
- 优先 merge → mark_resolved → demote → archive_with_provenance
- 不做无来源硬删除

---

## RagMemory 的 provenance 规则

- 每条 RagMemory 必须有 `provenance` 字段（格式：`curation:{turn_id}`）
- 每条必须有 `source_turn_ids`（至少包含当前 turn_id）
- 每条必须有 `evidence`（来源 turn_id 列表）
- 每条必须有 `tags`（`accepted_turn` 或具体 kind）
- 不得将未确认推测写入 RAG
- 不得将 AgentSuggestion 当成发生事实写入 RAG
- 不得将草稿内容写入 RAG

---

## MemoryCommitPlan 与幂等规则

- `memory_commit_id` 由 PlanCompiler 生成（UUID）
- `idempotency_key` = `{turn_id}:{memory_commit_id}`
- 同一 `cardId + sessionId + turnId + operationType` 在 retry/resume 中不得重复生效
- 已 curated 的 turnId 通过 `existing_curated_turn_ids` 检查跳过
- MemoryCommitRuntime 通过 `MemoryCommitReceipt` 保证幂等

---

## 失败、degraded、pending、retry 行为

| 场景 | 行为 |
|------|------|
| Memory Curator runtime failure | 返回 `degraded=True` + `degraded_reasons`，不影响 accepted turn |
| MemoryCommitRuntime failure | accepted turn / CardState / TurnRecord 保持有效，返回 operation 级别结果 |
| adapter timeout | 返回 `degraded=True`，不阻断回合 |
| 部分 operation 失败 | 通过 `MemoryCommitResult.status` 逐条报告 |
| retry 同一 turn | 通过 `existing_curated_turn_ids` 跳过，不重复写入 |

---

## ComfyUI 节点

| 节点 | 显示名称 | 功能 |
|------|----------|------|
| `AWPV2MemoryCurationTrigger` | 记忆治理触发 | 确定性触发评估 |
| `AWPV2MemoryCurationRequest` | 记忆治理请求 | 构建正式请求 |
| `AWPV2MemoryCuratorAgent` | Memory Curator Agent | 完整管线执行 |
| `AWPV2MemoryCurationValidator` | 记忆候选验证 | 验证候选 |
| `AWPV2MemoryCurationRanker` | 记忆候选排序 | 排序候选 |
| `AWPV2MemoryCurationCommitPlan` | 记忆提交计划编译 | 候选 → MemoryCommitPlan |
| `AWPV2MemoryCurationDiagnostics` | 记忆治理诊断 | 诊断输出 |

---

## 官方 Workflow

`workflows/official_memory_curator_agent_v2.json`

位置：回合后段（QualityGate → StateProposal → CardStateCommit → TurnRecordCommit → **Memory Curation** → Memory Commit → Completed Turn）

不位于 Writer 前的 DynamicSubAgentPool。

no-op 路径：`shouldTrigger=false → 空 MemoryCommitPlan → Completed Turn`

---

## 测试命令与真实结果

```bash
python -m pytest tests/ -x -q
```

**结果：497 passed in 2.08s**

D6 专项测试（46 项）：
1. Quality Gate reject 时绝不触发 ✅
2. CardStateCommit 失败时绝不触发 ✅
3. TurnRecordCommit 失败时绝不触发 ✅
4. accepted Turn 且存在长期事实时可触发 ✅
5. 普通闲聊无长期价值时正常 no-op ✅
6. Curator 只能读取 accepted final output ✅
7. Curator 不能从 rejected output 提取记忆 ✅
8. 无 evidence candidate 被拒绝 ✅
9. 无 accepted sourceTurnId candidate 被拒绝 ✅
10. AgentSuggestion 不能直接沉淀为长期事实 ✅
11. ActiveMemory 30~80 中文字符限制 ✅
12. ActiveMemory 永远不超过 15 条 ✅
13. ActiveMemory 满时优先 merge/resolve/demote ✅
14. 未解决承诺优先于已解决闲聊 ✅
15. 当前回合推进旧承诺时更新既有 ActiveMemory ✅
16. 相同事实重复出现时不会无限写入 RagMemory ✅
17. RagMemory 必须有 tags/entityRefs/provenance ✅
18. 已解决 ActiveMemory 可被标记 resolved ✅
19. Curator 无法访问 Store/SQLite ✅
20. Curator 无法跨 cardId/sessionId 查询 ✅
21. Curator 无法调用未授权工具 ✅
22. Curator 无法递归委派 ✅
23. Curator 无法生成 StateUpdateProposal ✅
24. Curator 无法直接执行 MemoryCommit ✅
25. Curator 输出玩家正文时被拒绝 ✅
26. MemoryCommitPlan 必须携带 idempotencyKey ✅
27. 同一 turn retry 不得重复创建 ActiveMemory ✅
28. 同一 turn retry 不得重复创建 RagMemory ✅
29. MemoryCommitRuntime 部分 operation 失败可观测 ✅
30. Curator runtime timeout 返回 degraded ✅
31. MemoryCommitRuntime timeout/failure 不撤销 accepted turn ✅
32. no-op 路径正常完成 ✅
33. 所有既有测试持续通过 ✅
34. 官方 workflow JSON 结构校验通过 ✅
35. E2E 正常记忆整理路径 ✅
36. E2E 拒绝/失败/幂等路径 ✅
37-46. 合同序列化往返测试 ✅

---

## 已知限制

1. **Fake 模式**：当前使用 `FakeMemoryCandidateGenerator`（确定性规则），无真实 LLM 调用
2. **无语义相似度**：实体匹配基于简单字符串包含，无向量嵌入
3. **简单信号检测**：触发规则基于正则关键词，无 NLP 深度分析
4. **无跨卡检索**：严格 cardId + sessionId 隔离

---

## 下一阶段推荐接入点

**D-Integration: Dynamic Agent Integration & Conflict Governance V1**

推荐接入点：
1. 将 Memory Curator 集成到 DynamicSubAgentPool 的后段调度（可选）
2. 实现真实 LLM Adapter 替代 FakeMemoryCandidateGenerator
3. 多 Agent 并发调度与预算总控
4. Agent 间冲突治理

---

## 禁止回归的架构约束

1. 不得创建第二套 Memory Store
2. 不得创建第二套独立记忆 schema
3. 不得把 Memory Curator 放入 Writer 前的 DynamicSubAgentPool
4. 未通过 Quality Gate 的草稿不得被 Memory Curator 看见
5. CardStateCommit/TurnRecordCommit 失败时不得触发 Memory Curator
6. Memory Curator 失败不得撤销已接受的正文/CardState/TurnRecord
7. 同一 turn retry 不得重复写入记忆
8. Memory Curator canWriteMemory = false
9. ActiveMemory 不超过 15 条
10. 所有候选必须有 accepted evidence
