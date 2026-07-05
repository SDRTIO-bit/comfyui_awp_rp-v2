# 当前基线与分支复用结论

- **当前分支**: `feat/long-session-persistent-real-runtime-v1`
- **基线**: main @ `c99f2a6` (playable-rp-runtime-persistent-v1)
- **工作区**: 干净（仅新文件 + 有限修改）
- **检查的分支**: `feat/observability-autonomous-harness-v1`、`feat/real-provider-multiturn-playable-acceptance-v1`、`feat/persistent-session-roundsnapshot-integration-v1`、`feat/first-turn-execution-context-assembly-v1` — 全部完全合并入 main（0 commits ahead，都只是落后 main）
- **复用内容**: 没有要 cherry-pick 的内容；所有 4 个分支的内容都已存在于 main 中
- **拒绝内容**: 无

# 实现范围

## P0-A/P0-B/P0-C：用于真实持久化回合的共享引擎（`runtime/persistent_turn_engine.py`）

新建 `PersistentTurnEngine` 类，为 `AWPV2PersistentFirstTurn` 和 `AWPV2PersistentContinuationTurn` 提供共享代码路径。它在单个事务性回合中运行完整的管线：

```
Snapshot（含 L1/L2/L3 + Worldbook 证据）
→ Director（通过 provider_adapter_factory：fake 或真实 DeepSeek）
→ Writer（通过 provider_adapter_factory：fake 或真实 DeepSeek）
→ Quality Gate（确定性管道）
→ CardState Commit（SQLite，乐观并发控制）
→ TurnRecord Commit（SQLite，重复错误 = 幂等重放）
→ D6 Memory Curator（MemoryCurationRuntime → MemoryPlanCompiler → ActiveMemoryCommitRuntime → RagMemoryCommitRuntime）
→ Trace 持久化（SqliteTraceStore，所有阶段事件 + 证据字段）
```

Provider 适配器工厂（`runtime/provider_adapter_factory.py`）：
- 根据 `ModelProfileRegistry` 解析 `director_profile_id` / `writer_profile_id`
- 假 profile → `FakeDirectorV2Adapter` / `FakeWriterV2Adapter`
- 真实 profile → `DeepSeekAdapter` → `RealDirectorV2Adapter` / `RealWriterV2Adapter`
- 缺少 API key / 提供商调用失败 → 结构化故障，不静默降级为假

## P0-B：D6 接通

- `MemoryCurationRuntime`（含确定性 `FakeMemoryCandidateGenerator`）现在运行在**每个**被接受的（accepted）回合上
- 触发器策略评估信号（承诺、秘密、关系、目标、事件、长期影响）
- 当信号存在时 → `MemoryCurationResult` → `MemoryPlanCompiler` → `MemoryCommitPlan` → Active + RAG 提交运行时（提交运行时）
- 当无信号时 → `memory_curation_status = "noop"`（确定性，非静默）
- 失败产生 `memory_curation_status = "failed"`，绝不静默 `noop`
- 测试环境保留现有 fixture 路径以向后兼容 `test_persistent_session.py`

## P0-C：Trace + 证据闭环

- `PersistentTurnEngine` 创建 `ExecutionTrace`，为每个阶段追加 `TraceEvent`，并持久化至 `registry.trace_store`
- 阶段：`round_snapshot`、`director`、`writer`、`quality_gate`、`card_state_commit`、`turn_record_commit`、`memory_curation_triggered`、`memory_curator_called`、`memory_curator`、`active_memory_commit`、`rag_memory_commit`
- 每个事件记录：`success`、`duration_ms`、`details`（含 L1/L2/L3 ID、worldbook ID、导演计划引用、quality verdict、commit revisions、memory commit IDs）
- 绝不在 trace 中包含 API key、原始系统提示语或原始卡片内容
- `FirstTurnDiagnostics` 扩展了 23 个向后兼容的新字段（见下文）
- 重放收据（Replayed receipt）现在返回 `accepted_text=existing_record.writer_output[:200]`（可恢复的预览），而非永远为空

## P0-D：用户模拟长会话框架（Harness）

`testing/user_simulation_harness.py` — 独立 CLI，驱动持久化节点：

```powershell
python -m awp_rp_runtime_v2.testing.user_simulation_harness `
  --card-path "<角色卡路径>" `
  --turns 10 `
  --director-profile-id "deepseek-v4-pro-director" `
  --writer-profile-id "deepseek-v4-flash-writer" `
  --player-profile-id "simulated-player-v1" `
  --mode "debug-full" `
  --restart-after-turn 5 `
  --save-artifacts
```

- `simulated-player-v1` / `fake-player` 配置已加入 `ModelProfileRegistry`
- Player simulator（`SimulatedPlayerAgent`）读取上轮输出 + 角色信息 + 目标 + 调试上下文，产出下一条玩家输入
- `visible` 模式：仅限玩家可见的信息
- `debug-full` 模式：额外读取脱敏过的结构化运行时上下文（CardState 摘要、L1/L2/L3 回调 ID/摘要、世界书命中、质量结果、追踪摘要）
- 工件存入 `artifacts/long-session-runs/<run_id>/`（run_manifest、scenario、per-turn JSON + trace、final_report JSON + Markdown）
- 场景规格：`testing/scenarios/demo_long_session_v1.json` — 建立事实 → 修改关系 → 回调（无敏感内容）

## P0-E：重构后的真实提供商验收

`testing/real_provider_multiturn_acceptance.py` 重写为标准化的持久化路径（委托给框架）。旧版直接提供商冒烟测试保留为 `run_direct_provider_smoke()`，并明确标注为 NOT persistent acceptance。

## P0-F：离线测试 + 质量观察器

- `tests/test_long_session_v1.py`：30 个测试，覆盖所有 10 项离线验收标准
- `testing/quality_observer.py`：确定性、非阻断式质量观察器。检查 empty output、revision regression、memory-use evidence、repetition risk、format leaks、worldbook relevance。产生分项分数 + hard failures + warnings。

# 待补充
- D6 触发策略可能不会针对 D6 需要记录的 promise/secret 关键词筛选出模拟的 writer 输出（mock writer output）。L2 回调使用了 `player_input[:50]`——召回内容边界在真实运行中由所生成内容匹配上下文决定。

---

# 真实持久化链如何接通

1. `PersistentFirstTurn.execute()` / `PersistentContinuationTurn.execute()` 调用 `PersistentTurnEngine.execute()`
2. Engine 调用 `DirectorAdapterFactory.build(profile_id)` → `run_director()` → `DirectorPlan`
3. Engine 将 `DirectorPlan` 编译为 `FinalTurnBrief`，调用 `WriterInputBundleV2Builder.build(snapshot, brief)` → `WriterInputBundle`
4. Engine 调用 `WriterAdapterFactory.build(profile_id)` → `run_writer()` → candidate text
5. Engine 通过 `QualityPipelineRuntime.check()` 运行 Quality Gate
6. Engine 调用 `CardStateStore.commit()` → `TurnRecordStore.save()`
7. Engine 调用 `MemoryCurationRuntime.curate()` → `MemoryPlanCompiler.compile()` → Active + RAG commit runtimes
8. Engine 将 `ExecutionTrace`（含所有阶段事件 + 证据）保存至 `SqliteTraceStore`

# D6 和记忆提交如何接通

- `_run_d6()`（`persistent_turn_engine.py` L370-485）
- `MemoryCurationRuntime(curate)` 使用 `FakeMemoryCuratorAdapter`（确定性候选生成器）→ `MemoryCurationResult`
- `MemoryPlanCompiler(compile)` → `MemoryCommitPlan`（new_active_entries、new_rag_entries、resolved_active_ids）
- `ActiveMemoryCommitRuntime(commit_request)` — 门控验证（质量、card state 提交、turn record 提交、追溯 id 匹配、幂等键）
- `RagMemoryCommitRuntime(commit_request)` — 与上述相同，外加范围安全（scope safety）
- Commit IDs + 状态按 `turn_id` + `trace_id` 记录在 diagnostics 中

# Trace 与检测证据模型

- `ExecutionTrace` → `TraceEvent` 列表 → 以 `trace_id`、`turn_id` 存入 `SqliteTraceStore`
- 可查询方式：`registry.trace_store.get_by_turn(turn_id)`
- 证据字段包含在 diagnostics 中：`l1_turn_ids_recalled`、`l2_memory_ids_recalled`、`l3_memory_ids_recalled`、`worldbook_entry_ids_activated`、`round_snapshot_id`、`director_plan_ref`、`card_state_revision_before/after`、`memory_commit_ids`
- 安全属性：不含 API key、不含原始系统提示语、不含完整卡片内容。每个事件中的 `details` 字段仅包含 ID、数量、摘要哈希和状态代码。

# 用户模拟 Harness 使用方式

```powershell
# 离线（假配置，无需 API key）：
python -m awp_rp_runtime_v2.testing.user_simulation_harness --turns 10 --save-artifacts

# 真实模型（需要显式双重确认）：
$env:AWP_REAL_LLM_E2E = "1"
$env:DEEPSEEK_API_KEY = "..."
$env:AWP_ALLOW_EXTERNAL_CARD_CONTENT = "1"
python -m awp_rp_runtime_v2.testing.user_simulation_harness `
  --card-path "<角色卡路径>" `
  --turns 10 `
  --director-profile-id "deepseek-v4-pro-director" `
  --writer-profile-id "deepseek-v4-flash-writer" `
  --player-profile-id "simulated-player-v1" `
  --mode "debug-full" `
  --restart-after-turn 5 `
  --save-artifacts
```

# 新增或修改的文件

**新增文件 (7)**:
- `runtime/persistent_turn_engine.py` — 共享回合引擎
- `runtime/provider_adapter_factory.py` — 假/真实适配器工厂
- `testing/simulated_player_agent.py` — 玩家模拟器代理
- `testing/quality_observer.py` — 确定性质量观察器
- `testing/user_simulation_harness.py` — 主框架 CLI
- `testing/scenarios/demo_long_session_v1.json` — 示例场景
- `tests/test_long_session_v1.py` — 30 个离线验收测试

**修改文件 (6)**:
- `adapters/llm/model_profile_registry.py` — +2 个配置（simulated-player-v1、fake-player）
- `contracts/first_turn_diagnostics.py` — +23 个证据/profile/trace 字段（向后兼容）
- `nodes/persistent_first_turn_node.py` — 重构为引擎用户，修复重放文本
- `nodes/persistent_continuation_turn_node.py` — 重构为引擎用户，修复重放文本
- `testing/real_provider_multiturn_acceptance.py` — 重写为标准化持久化路径
- `tests/test_persistent_session.py` — test_17 适配新的适配器工厂 API

# 离线测试结果

```
tests/test_long_session_v1.py ......... 30 passed in 2.33s
tests/test_persistent_session.py ...... 36 passed in 4.55s
tests/test_real_provider.py ........... 31 passed in 1.04s
All relevant test suites pass (no regressions outside pre-existing workflow-JSON failures).
```

12 个预先存在的失败（`test_p1_nodes`、`test_p2_nodes`、`test_d4`、`test_d5`、`test_d6`、`test_d_integration`、`test_m1`、`test_d2`、`test_d3`），原因均在于测试引用了在提交 `ead5f48` 中被删除的、但测试仍然需要的工作流 JSON 文件，与此次变更无关。

# 真实模型验收结果

**未执行** — 原因：无 API key / 无可用真实角色卡。通过采用共享引擎和 provider 提供工厂 + 故障闭环机制，代码管线在架构上已经准备就绪。

假 profile 的端到端验证结果：
```
3/3 回合通过，3 个 accepted TurnRecords，3 个 traces，3 个 D6 commits
L1 历史回调：第 2 回合 1 个回合，第 3 回合 2 个回合
所有回合：outcome=success，quality=accept，card_state + turn_record committed
每回合 trace：所有 9 个阶段事件均记录 + persisted
```

# 已知限制与未做事项

1. **D6 候选生成器（D6 Candidate Generator）是确定性的**（基于规则），而非基于 LLM。如果触发信号（promise、secret 等关键词）在 writer 输出中不存在，则会跳过记忆写入。
2. **L2 回调使用 `player_input[:50]` 作为查询**——如果活跃记忆摘要与玩家输入不完全匹配，则可能无法成功匹配。在离线假运行中存在内容边界限制（假 writer 产生的是模板文本），但在真实运行中是一个功能性修复。
3. **Director Plan 不持久化**为独立于 trace 的第一类对象——仅保持哈希。
4. **未实现 LLM 质量评估器（LLM quality evaluator）**——质量观察器目前是确定性的。LLM 评估器扩展需要明确支持真实测试。
5. **真实模型验收未经执行**，原因是环境限制（API key 和角色卡不可用，框架也不应猜测 API key）。
6. **半回合断电恢复（Mid-turn crash recovery）**不在本次 scope 内——这是未来的工作。

# 状态矩阵

| 状态 | 含义 |
|-----------|---------|
| 代码存在 | ✅ RealDirectorV2Adapter、RealWriterV2Adapter、ExecutionTrace、SqliteTraceStore、D6 Runtime 全部存在且已 wire |
| 离线假测试通过 | ✅ 30 个单元测试 + 36 个持久化测试 + 31 个 provider 测试全部通过 |
| 真实 Provider 调用通过 | ❓ 未执行（需要 API key）— 架构通过 provider 工厂 + 故障闭环实现 ready |
| 真实持久化节点链通过 | ❓ 未执行（需要 API key + 角色卡）— 框架调用 PersistentBootstrap/FirstTurn/ContinuationTurn，架构 ready |
| 真实长会话通过 | ❓ 未执行（需要 API key + 10 回合运行时）— 框架通过 fake 跑通了 10 回合 + 重启 |

# 建议的下一步

1. **真实模型验收**：在 API key 可用时，对真实 DeepSeek 模型运行 10 回合的 `user_simulation_harness`。
2. **LLM 质量评估器**：添加一个可选的、以真实测试为标志的 evaluator（如 DeepSeek 回调），用于叙事质量评分。
3. **D6 LLM 适配器**：用 LLM 替换确定性 `FakeMemoryCandidateGenerator`，以在真实模型中产生更丰富的记忆候选。
4. **Director/Writing 提示语与现有 prompt 编译工具的集成**：目前使用 `RealDirectorV2Adapter._build_plan_prompt` 和 `RealWriterV2Adapter._build_writer_prompt`——应使用完整的 `MemoryContextAssembler` + WriterInputBundle 数据来丰富提示语。
