# Comfy Multi-Session Long-Context Acceptance V1 — 交接文档

## 分支与提交

```
分支: feat/comfy-multisession-long-context-acceptance-v1
基线: feat/long-session-persistent-real-runtime-v1 (430da37)

aa65dc0 fix: L2 active memory recall — soft word match instead of strict substring
21f2aec feat: writer preset system + sub-agent triggers + quality gate + self-check
6edba0f feat: multi-session long-context acceptance harness + audit + tests
```

工作区干净，未提交内容仅 `testing/_run_acceptance_20x2.py`（临时验收脚本，可删除）。

---

## 架构概述

### 新增文件

```
presets/
  writer/kedai_heavy_v1.txt              # Writer 预设（郁达夫文风+禁词库+字数规范）
  writer_preset_loader.py                # 预设加载器（按名加载，静默回退）

testing/
  workflows/
    persistent_rp_long_session_first_turn_api.json       # Bootstrap + FirstTurn + Probe
    persistent_rp_long_session_continuation_turn_api.json # ContinuationTurn + Probe
  scenarios/
    session_a_secret_watch.json          # Session A 场景（青铜怀表保密）
    session_b_silver_bell.json           # Session B 场景（银铃公开）
  comfy_multisession_longrun_harness.py  # 主 Harness CLI（1206 行）
  cross_session_audit.py                 # 跨 session 隔离审计（10 项检查）

tests/
  test_comfy_multisession_longrun_v1.py  # 46 项离线测试
```

### 修改文件

| 文件 | 改动 |
|------|------|
| `adapters/llm/real_writer_adapter.py` | Writer 自检修订循环 + preset 注入 |
| `runtime/persistent_turn_engine.py` | D1-D5 子 Agent 触发 + Quality Gate 1000 字门槛 + preset 线程 |
| `runtime/provider_adapter_factory.py` | WriterAdapterFactory 接受 preset_text |
| `nodes/persistent_first_turn_node.py` | 新增 `writer_preset_path` 可选输入 |
| `nodes/persistent_continuation_turn_node.py` | 同上 |
| `storage/sqlite/active_memory_store.py` | L2 召回修复：严格子串 → 分词软匹配 |
| `testing/__init__.py` | 导入容错（try/except） |

### 执行路径

```
ComfyUI /prompt → workflow JSON
  → AWPV2PersistentBootstrap（角色卡导入 + SQLite 写入）
  → AWPV2PersistentFirstTurn（仅第 1 回合）
      → SessionRuntimeLoad（SQLite → Binding/CardState/Opening/Worldbook）
      → RoundSnapshotBuilder（L1/L2/L3 组装）
      → PersistentTurnEngine
          → Director（Flash 400B，叙事规划）
          → D1-D5 Trigger Policy（确定性正则，收集建议）
          → WriterInputBundleV2Builder（含 Agent 建议 enrichment）
          → Writer（Pro 1.6T，出文 + 自检修订）
          → Quality Gate（1000 字门槛）
          → CardState/TurnRecord Commit
          → D6 Memory Curator（策展 L2+L3 记忆）
      → AWPV2TurnResultProbe（安全投影 → /history）
  → AWPV2PersistentContinuationTurn（第 2+ 回合，同上但无 Bootstrap）
```

---

## 运行方式

### 离线测试

```bash
# 新测试
python -m pytest tests/test_comfy_multisession_longrun_v1.py -q

# 全部测试（预期 13 项预设失败，均为已删除的 official_* workflow 引用）
python -m pytest tests/ -q
```

### 离线 Dry-Run

```bash
python testing/comfy_multisession_longrun_harness.py \
  --card-path "<任意角色卡路径>" \
  --dry-run \
  --sessions 2 --turns 3 \
  --save-artifacts
```

### 真实 ComfyUI Smoke

```bash
# 需先启动 ComfyUI（确保节点代码最新）
python testing/comfy_multisession_longrun_harness.py \
  --card-path "<角色卡路径>" \
  --sessions 2 --turns 8 \
  --director-profile-id "fake-director" \
  --writer-profile-id "fake-writer" \
  --save-artifacts
```

### 真实模型验收

```bash
# 需要 DEEPSEEK_API_KEY 环境变量
export AWP_REAL_LLM_E2E=1
export AWP_ALLOW_EXTERNAL_CARD_CONTENT=1

python testing/comfy_multisession_longrun_harness.py \
  --card-path "<角色卡路径>" \
  --sessions 2 --turns 20 \
  --director-profile-id "deepseek-v4-flash-writer" \
  --writer-profile-id "deepseek-v4-pro-director" \
  --writer-preset "kedai_heavy_v1" \
  --restart-after-turn 10 --restart-mode "runtime" \
  --mode "debug-full" \
  --save-artifacts --real-model
```

注意：Director 用 Flash（400B，规划任务），Writer 用 Pro（1.6T，出文任务）。

### 交互式 RP 测试

```bash
# 单 session，逐回合手动推进
# 参考 testing/_run_acceptance_20x2.py 的 submit() 模式
```

---

## 测试覆盖矩阵

| 维度 | 离线 | ComfyUI Fake | ComfyUI Real |
|------|------|-------------|-------------|
| Bootstrap | ✅ | ✅ | ✅ |
| FirstTurn | ✅ | ✅ | ✅ |
| ContinuationTurn | ✅ | ✅ | ✅ |
| Replay | ✅ | ✅ | ✅ |
| L1 回合历史召回 | ✅ | ✅ | ✅ |
| L2 Active Memory 召回 | 🔧 | 🔧 | 🔧 |
| L3 RAG Memory 召回 | 🔧 | 🔧 | 🔧 |
| 世界书检索 | ✅ | ✅ | ✅ |
| D6 Memory Curator | ✅ | ✅ | ✅ |
| D1 History Recall Agent | ✅ | ✅ | ✅ |
| D2 Opportunity Agent | ✅ | ✅ | ✅ |
| D3 World Life Agent | ✅ | ✅ | ✅ |
| D4 Emotion Relation Agent | ✅ | ✅ | ✅ |
| D5 Continuity Agent | ✅ | ✅ | ✅ |
| Writer Preset 加载 | ✅ | ✅ | ✅ |
| Writer 自检修订 | ❌ | ❌ | ❌ |
| Quality Gate 1000 字 | ❌ | ❌ | ❌ |
| Player Simulator | ❌ | ❌ | ❌ |
| Runtime Restart | ❌ | ❌ | ❌ |
| 跨 Session 隔离 | ✅ | ✅ | ✅ |
| 2×20 全功能验收 | ❌ | ❌ | ❌ |

---

## 已知问题

### 1. ComfyUI 缓存导致间歇性 0 字输出

**症状**：ContinuationTurn 偶尔返回 `execution_cached`，不产生新内容。
**绕过**：重新提交时确保 `request_id`、`attempt_id`、`turn_id` 全部唯一。
**根本修复**：待研究 ComfyUI 0.3.62 的缓存行为。

### 2. L2/L3 记忆召回不工作

**原因**：`_filter_active` 中 query 匹配使用严格子串，对叙事文本不适用。
**修复**：已改为分词软匹配（`storage/sqlite/active_memory_store.py`），需重启 ComfyUI 加载。
**验证**：重启后观察 trace 中 `l2_memory_ids_recalled` 是否 > 0。

### 3. Writer 自检修订未测试

**原因**：新增功能，未被验收测试覆盖。
**验证方法**：故意给一个短 prompt，观察 Writer 是否自我修订并增加字数。

### 4. Quality Gate 1000 字门槛未测试

**同上**，需监控 trace 中 `verdict` 是否为 `revise` 当字数 < 1000 时。

### 5. Player Simulator 未接入

所有测试使用硬编码玩家输入。`testing/simulated_player_agent.py` 已存在且可用，需在 Harness 中启用 `--player-profile-id "simulated-player-v1"`。

### 6. 角色卡开场白 g0 为乱码

测试酒馆卡的 `first_mes` 为乱码时，g0 不可用。使用 `greeting_id: "g2"` 或更高索引。

---

## Artifact 目录结构

```
artifacts/comfy-multisession-runs/<run_id>/
  run_manifest.json           # 运行配置
  workflow_manifest.json      # workflow 模板信息
  scenarios/                  # 场景副本
    session-A.json
    session-B.json
  sessions/
    session-A/
      turn-001.json ...       # 每回合完整 artifact
      summary.json
    session-B/
      ...
  cross_session_audit.json    # 10 项隔离检查
```

---

## 模型 Profile

| Profile ID | 模型 | 用途 |
|------------|------|------|
| `deepseek-v4-pro-director` | deepseek-v4-pro | Writer（出文，1.6T） |
| `deepseek-v4-flash-writer` | deepseek-v4-flash | Director（规划，400B） |
| `simulated-player-v1` | deepseek-v4-flash | Player Simulator |
| `fake-director` | fake | 离线测试 |
| `fake-writer` | fake | 离线测试 |
| `fake-player` | fake | 离线测试 |

注意：尽管 profile 名称含 "director"/"writer"，实际使用中做了调换 — Pro 出文，Flash 规划。

---

## 下一步

1. 重启 ComfyUI，验证 L2/L3 召回修复
2. 测试 Writer 自检修订循环
3. 测试 Quality Gate 1000 字门槛
4. 接入 Player Simulator
5. 执行 Runtime Restart 测试
6. 完整 2×20 全功能验收
