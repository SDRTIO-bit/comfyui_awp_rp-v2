# Alpha 状态报告 V0.1

**版本:** v0.1.0-alpha
**日期:** 2026-06-27
**基线 Tag:** d-integration-dynamic-agent-conflict-governance-v1

---

## 已经完成的能力

### 核心架构

- 确定性 CardState（SQLite + 事务提交 + revision + patchId + 幂等）
- 三层记忆系统（L1 近忆窗口 + L2 活跃记忆 + L3 RAG）
- 双主 Agent 职责边界（Director / Writer）
- 合同驱动架构（所有数据结构带 schema_id + schema_version）

### 动态 Agent 系统

- D1 History/Recall Agent（历史证据回查）
- D2 Opportunity Agent（戏剧机会识别）
- D3 World-Life Agent（世界活性事件）
- D4 Emotion/Relationship Agent（情绪与关系解读）
- D5 Continuity Agent（连续性约束，Wave B）
- D6 Memory Curator Agent（accepted-turn 后记忆治理）

### 调度与治理

- Dynamic Agent Scheduler（Wave A / Wave B 调度）
- Continuity Barrier（Wave A → Wave B 标准化传递）
- Suggestion Conflict Governor（冲突检测与 resolution）
- Director Suggestion Resolution（结构化决议）
- 预算策略（Simple / Normal / Complex 三档）
- 超时与降级机制
- Agent Integration Trace（完整审计追踪）

### ComfyUI 节点

- 80+ ComfyUI 节点（CardState / RoundSnapshot / Director / Writer / Quality Gate / Commit / Memory / D1-D6 / Integration）
- 11 个官方 workflow JSON
- 中英文节点显示名称

### 测试

- 566 个测试全部通过
- 覆盖：合同、策略、存储、运行时、集成、端到端
- Fake Adapter 用于所有测试

---

## Fake Adapter 覆盖范围

| Adapter | 状态 | 说明 |
|---------|------|------|
| FakeLlmAdapter | ✅ 已实现 | 返回预设文本，用于测试 |
| FakeToolRunner | ✅ 已实现 | 模拟工具执行，用于测试 |
| FakeDirectorV2Adapter | ✅ 已实现 | 模拟 Director 输出 |
| FakeWriterV2Adapter | ✅ 已实现 | 模拟 Writer 输出 |
| FakeMemoryCuratorAdapter | ✅ 已实现 | 模拟 D6 输出 |
| FakeMemoryCandidateGenerator | ✅ 已实现 | 模拟记忆候选生成 |

---

## 测试覆盖范围

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| test_p1_card_state.py | ~20 | CardState 合同与操作 |
| test_p1_sqlite.py | ~15 | SQLite 存储层 |
| test_p1_turn_record.py | ~15 | TurnRecord 存储 |
| test_p1_e2e.py | ~10 | P1 端到端 |
| test_p1_nodes.py | ~25 | P1 ComfyUI 节点 |
| test_p2_contracts.py | ~15 | P2 合同 |
| test_p2_merger.py | ~15 | SuggestionMerger |
| test_p2_pool.py | ~15 | DynamicSubAgentPool |
| test_p2_registry.py | ~10 | Agent 注册表 |
| test_p2_e2e.py | ~10 | P2 端到端 |
| test_p2_nodes.py | ~5 | P2 节点 |
| test_m1_memory_foundation.py | ~80 | 三层记忆系统 |
| test_c1_dual_main_tool_gateway.py | ~80 | C1 双主 Agent + 工具网关 |
| test_c1_e2e.py | ~40 | C1 端到端 |
| test_d1_history_recall.py | ~50 | D1 历史回查 |
| test_d2_opportunity.py | ~50 | D2 戏剧机会 |
| test_d3_world_life.py | ~50 | D3 世界活性 |
| test_d4_emotion_relationship.py | ~50 | D4 情绪关系 |
| test_d5_continuity.py | ~60 | D5 连续性 |
| test_d6_memory_curator.py | ~60 | D6 记忆治理 |
| test_d_integration.py | 69 | D-Integration 集成 |

---

## 尚未验证的真实模型行为

- OpenAICompatibleAdapter 的 `generate_text()` 和 `generate_structured()` 尚未实现（当前抛出 `NotImplementedError`）
- 真实 LLM 调用的 token 计费、限流、重试行为未验证
- 真实模型对 AgentRoleSpec 的遵循程度未验证
- 真实模型对工具调用协议的遵循程度未验证
- Director / Writer / Reviser 的真实模型适配器返回格式未验证

---

## 尚未实现的前端能力

- ComfyUI 节点参数的可视化配置
- Agent 执行状态的实时观察面板
- 记忆系统的可视化管理界面
- 冲突 resolution 的交互式确认
- 执行 Trace 的可视化回放

---

## 尚未实现的产品化能力

- 一键安装即玩的完整 RP 体验
- 真实角色卡、世界书、预设的加载与管理
- 自动世界事件系统
- 无限制多 Agent 自主协作
- 稳定的第三方插件生态兼容性
- 多会话并发支持
- 持久化会话管理

---

## 已知限制

1. **Wave A 执行仍是顺序的**：DynamicSubAgentPool.execute 顺序遍历，真正的并发需要异步/线程池支持
2. **FinalTurnBrief 裁剪逻辑尚未实现自动截断**：当前由 DirectorResolution 输出裁剪元数据，Writer 端自行处理
3. **TurnOrchestrator 的 wave 路径需要显式注入**：scheduler/wave_executor/budget_policy 才会激活
4. **真实 LLM adapter 未实现**：OpenAICompatibleAdapter 仅检查 API key 是否存在，实际调用抛出 NotImplementedError
5. **docs/reference/ 架构文档已从 docs/ 根目录移入**：原始架构记录已随公开仓库发布
6. **LICENSE 尚未确定**：代码版权归项目作者所有

---

## 下一阶段候选方向

1. **真实 LLM Adapter 接入**：实现 OpenAICompatibleAdapter 的真实调用，验证 Agent 在真实模型下的行为
2. **ComfyUI 安装验证**：验证仓库可作为 ComfyUI 插件直接安装并加载节点
3. **前端可观测性**：Agent 执行状态、记忆系统、冲突 resolution 的可视化
4. **并发执行**：Wave A 的真正并发支持
5. **产品化集成**：真实角色卡、世界书、预设的加载与管理
