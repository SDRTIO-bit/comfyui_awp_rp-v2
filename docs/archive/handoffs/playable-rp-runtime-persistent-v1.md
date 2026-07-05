# Playable RP Runtime Persistent V1

## 冻结合入说明

本 handoff 标志着持久化 RP Runtime 达到"可玩"里程碑，合入 main 分支。

---

## 已验证（通过）

### 1. 持久化全链路

| 路径 | 验证方式 | 结果 |
|------|----------|------|
| Bootstrap → SQLite | 单元测试 + 实机 | PASS |
| Turn 1 → CardState + TurnRecord | 单元测试 + 实机 | PASS |
| Turn 2+ → SessionRuntimeLoad 恢复 L0/L1/L2/L3 | 单元测试 | PASS |
| ComfyUI 重启 → 同 sessionId 恢复 | 验收测试 28/28 | PASS |
| 同 turnId 重发 → idempotent replay | 单元测试 + 实机 | PASS |
| replay 后继续回合 → 上下文不损坏 | 验收测试 Turn 3 | PASS |

### 2. ComfyUI 实机执行

| 操作 | 结果 |
|------|------|
| Bootstrap 节点 (AWPV2PersistentBootstrap) | PASS |
| 首回合节点 (AWPV2PersistentFirstTurn) | PASS |
| 连续回合节点 (AWPV2PersistentContinuationTurn) | PASS |
| TurnResultProbe 输出 | PASS |
| Playable E2E (Bootstrap→T1→T2-5→Replay) | 7/7 PASS |

### 3. 真实 DeepSeek Provider

| 端点 | 结果 | 重试 |
|------|------|------|
| Anthropic (`api.deepseek.com/anthropic`) | 8/8 PASS | 零重试 |
| OpenAI (`api.deepseek.com`) | 7/8 PASS | 多次重试 |

- Director: tool_use (Anthropic) / function calling (OpenAI) 结构化输出
- Writer: 标准文本生成
- 模型: deepseek-v4-pro (director) + deepseek-v4-flash (writer)

### 4. 模型配置

| Profile | Model | 受控 |
|---------|-------|------|
| deepseek-v4-pro-director | deepseek-v4-pro | 白名单 |
| deepseek-v4-flash-writer | deepseek-v4-flash | 白名单 |
| fake-director | fake_director_v1 | 白名单 |
| fake-writer | fake_writer_v1 | 白名单 |

未知 profileId → fail closed。

### 5. 测试覆盖

```
852 tests passed
Playable E2E: 7/7
Persistence: 28/28
Real DeepSeek: 8/8 (Anthropic)
```

---

## 尚待验证（下一阶段）

### 1. 真实 DeepSeek 持久化链

当前真实 Provider 测试使用直接 Python API 调用（绕过 ComfyUI 节点）。
需要验证：在 ComfyUI 实机中，使用真实 DeepSeek profile 的持久化节点连续运行。

前置条件：
- 持久化节点支持真实 Provider（当前内部使用 FakeAdapter）
- 或创建真实 Provider 版本的持久化节点

### 2. 真实 D6 MemoryCommitPlan

当前 D6 在 test profile 下使用 test fixture 生成 MemoryCommitPlan。
需要验证：真实模型输出下，D6 是否产生有意义的 MemoryCommitPlan。

前置条件：
- 真实 Provider 连续运行
- D6 接收真实 writer_output 而非 fake 文本

### 3. 叙事质量

当前使用 fake-director / fake-writer 产出固定模板文本。
需要验证：
- 真实角色卡的叙事连贯性
- 角色一致性（跨回合人格不漂移）
- 世界书关键词命中质量
- L1 历史回查对叙事的影响

---

## 架构概览

```
用户输入
  ↓
AWPV2PersistentBootstrap (一次性)
  ↓ SQLite: L0 (Binding, Opening, Worldbook)
AWPV2PersistentFirstTurn (Turn 1)
  ↓ SQLite: L1 (TurnRecord), L2 (ActiveMemory), CardState
AWPV2PersistentContinuationTurn (Turn 2+)
  ↓ SessionRuntimeLoad → RoundSnapshotBuilder
  ↓ 恢复 L0 + L1 + L2 + L3
  ↓ Director → Writer → Quality → CardState → TurnRecord → D6
  ↓ SQLite: 全量持久化
同 turnId 重发 → idempotent replay (零 Provider 调用)
```

## 关键文件

| 文件 | 职责 |
|------|------|
| `runtime/runtime_store_factory.py` | SQLite 工厂 (profile + namespace) |
| `runtime/session_runtime_load.py` | L0-L3 恢复 |
| `runtime/round_snapshot_builder.py` | L1/L2/L3 组装 |
| `adapters/llm/deepseek_adapter.py` | 双端点 (Anthropic/OpenAI) 适配 |
| `adapters/llm/model_profile_registry.py` | 模型白名单 |
| `nodes/persistent_bootstrap_node.py` | Bootstrap 节点 |
| `nodes/persistent_first_turn_node.py` | 首回合节点 |
| `nodes/persistent_continuation_turn_node.py` | 连续回合节点 |
| `testing/playable_e2e_test.py` | 实机 E2E 测试 |
