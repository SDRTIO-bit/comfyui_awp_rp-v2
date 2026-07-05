# AWP RP Runtime V2

ComfyUI RP Runtime V2：持久化会话 + 双主 Agent + 受控动态子 Agent + 确定性 CardState + 三层记忆 + 管理面板

---

## 1. 项目是什么

本项目是一个以 ComfyUI 工作流为编排骨架的 RP（角色扮演）运行时。

核心理念：

> **确定性负责让故事不乱；独立 Agent 的受控自由负责让故事不死。**

它不是把越来越长的提示词交给单一模型，也不是把所有功能塞进一个万能主 Agent。而是在 ComfyUI 节点图中显式暴露：

- **确定性节点层**：CardState、条件世界书、事件阶段、记忆读写、质量决策、状态提交、审计
- **Agent 推理层**：双主 Agent、动态子 Agent、工具调用、叙事决策、创意建议、写作与修订

两者不是竞争关系。节点层负责可验证、可回放、可测试、可持久化的事实和副作用；Agent 层负责理解、联想、判断、选择、调度、叙事表现。

---

## 2. 当前状态

**版本：** `playable-rp-runtime-management-v1`

这是一个**可玩的持久化 RP Runtime**，带管理面板。

### 已验证

- 持久化全链路：Bootstrap → Turn 1 → Turn 2+ → Replay，SQLite 持久化
- 会话恢复：ComfyUI 重启后仅凭 `sessionId` 恢复 L0/L1/L2/L3
- 幂等重放：同 `turnId` 重发返回 `replayed` receipt，零 Provider 调用
- 模型配置受控：白名单 profile（deepseek-v4-pro/flash, fake-*）
- 真实 DeepSeek：8/8 回合通过（Anthropic 端点）
- ComfyUI 实机：Bootstrap → 5 回合 → Replay 全部通过
- 真实酒馆卡加载：大型酒馆卡（263KB, 40 worldbook, 6 greetings）
- 世界书激活：constant 8 条/回合 + selective 关键词匹配
- 双 Agent 真实 LLM：Director (Flash+思考) + Writer (Pro+禁思考)
- 子 Agent LLM 调用：D1-D5 触发后调 DeepSeek Flash 产出具体分析
- 管理面板：React SPA + REST API，会话浏览/回合历史/角色卡列表
- 20 回合连续运行：前 14 回合稳定（1000+ 字），CardState 8 次演化
- 981 个测试全部通过

### 尚待解决

- 子 Agent 触发条件过保守（20 回合测试中 0/20 触发）
- 记忆系统全程 noop（Curator prompt 未明确要求返回 memory candidates）
- 长会话崩溃（T15+ Curator 返回 None 导致，已修复根因）
- 缓存命中率低（prompt 动态内容在前部，稳定前缀短）
- Director/Writer 无工具调用能力（设计中有 ToolGateway，实现未接入）

---

## 3. 核心设计原则

1. **Agent 不直接写 CardState**：只有 `CardStateCommitRuntime` 可以写入
2. **Agent 不直接写记忆**：只有 `ActiveMemoryCommitRuntime` / `RagMemoryCommitRuntime` 可以写入
3. **Writer 不用工具、不直接写状态**：Writer 只能读取 FinalTurnBrief，产出 RP 正文
4. **Director 不输出玩家正文**：Director 只产出 TurnBrief / DelegationPlan / DirectorResolution
5. **D6 不参与 Writer 前 SuggestionMerge**：D6 在 Commit 后运行
6. **只有 Commit Runtime 可以产生副作用**：Quality Gate reject = 零副作用
7. **玩家代理权约束不能被 Agent 覆盖**：Agent 不能代替玩家做决定
8. **World-Life / Opportunity / Emotion 的建议不能自动变成既成事实**：只能作为 Writer 参考

---

## 4. 持久化架构

```
RuntimeStoreFactory (profile + namespace → SQLite)
  ↓
SessionRuntimeStoreRegistry (10 stores, 1 connection)
  ├── CardSessionBindingStore     (L0)
  ├── OpeningRecordStore          (L0)
  ├── WorldbookBindingStore       (L0)
  ├── BootstrapReceiptStore       (L0)
  ├── CardStateStore              (L0+L1)
  ├── TurnRecordStore             (L1)
  ├── RoundSnapshotStore          (snapshot)
  ├── TraceStore                  (trace)
  ├── ActiveMemoryStore           (L2)
  └── RagMemoryStore              (L3)
```

所有持久化节点通过 `RuntimeStoreFactory.from_env()` 获取 store，不接受 `dbPath` 输入。

---

## 5. 完整回合生命周期

```
Player Input
→ SessionRuntimeLoad (从 SQLite 恢复 L0/L1/L2/L3)
→ RoundSnapshotBuilder
→ DirectorPlan (tool_use / function calling)
→ Dynamic Agent Scheduler
→ Wave A (D1～D4 并发)
→ Continuity Barrier
→ D5 Continuity (Wave B)
→ Conflict Governance
→ Director Suggestion Resolution
→ FinalTurnBrief
→ Writer / Reviser
→ Quality Gate
→ State Proposal
→ CardState Commit (SQLite)
→ TurnRecord Commit (SQLite)
→ D6 Memory Curator
→ Deterministic Memory Commit (SQLite)
→ Completed Turn
```

---

## 6. ComfyUI 节点

共 **114** 个节点，覆盖完整 RP 生命周期。

### 持久化节点（用户直接使用）

| 节点 | 功能 | 输入 |
|------|------|------|
| `AWPV2PersistentBootstrap` | 导入卡片 + 创建会话 | source_path, session_id, greeting_id |
| `AWPV2PersistentFirstTurn` | 首回合执行 | session_id, player_input, profile_id |
| `AWPV2PersistentContinuationTurn` | 连续回合 + 幂等重放 | session_id, player_input, turn_id |
| `AWPV2ContinueTurnP1` | 正式 Continue 回合（P1 真实演化） | session_id, player_input, turn_id |
| `AWPV2SessionRuntimeLoad` | 加载会话状态 | session_id, player_input |
| `AWPV2TurnResultProbe` | history-safe 输出 | receipt, diagnostics |

所有持久化节点不接受 `dbPath`、`history`、`memory`、`CardState` 输入。

### 其他节点类别

| 类别 | 数量 | 说明 |
|------|------|------|
| CardState | ~15 | 卡片导入、规范化、绑定、状态提交 |
| Director/Writer | ~10 | 双主 Agent 编排 |
| D1-D6 子 Agent | ~40 | 历史回查、机会识别、世界活性、情绪关系、连续性、记忆治理 |
| Memory | ~8 | 活跃记忆、RAG 记忆、记忆编译 |
| Quality | ~5 | 质量门、质量管线 |
| Worldbook | ~5 | 条件世界书、会话绑定 |
| Trace/Diagnostics | ~10 | 执行追踪、诊断 |
| Integration | ~10 | 冲突治理、建议合并、工具网关 |

---

## 7. 幂等重放

同 `sessionId + turnId + requestId` 重发时：

```
TurnRecordStore.load(turn_id)
  ├── 存在 → 返回 replayed receipt (idempotency_status="replayed")
  │          不调用 Provider，不写 State，不写 Memory
  └── 不存在 → 正常执行
```

`idempotency_status` 值：
- `fresh`：正常执行
- `replayed`：返回既有结果
- `conflict`：session 不匹配
- `recovery_required`：未完成且不可恢复

---

## 8. 模型配置

受控白名单，未知 profileId → fail closed。

| Profile | Provider | Model | 用途 |
|---------|----------|-------|------|
| `deepseek-v4-flash-director` | deepseek | deepseek-v4-flash | Director（思考开启，reasoning_effort=high）|
| `deepseek-v4-pro-writer` | deepseek | deepseek-v4-pro | Writer（思考禁用）|
| `deepseek-v4-pro-director` | deepseek | deepseek-v4-pro | Director（兼容旧配置）|
| `deepseek-v4-flash-writer` | deepseek | deepseek-v4-flash | Writer（兼容旧配置）|
| `fake-director` | fake | fake_director_v1 | 测试 |
| `fake-writer` | fake | fake_writer_v1 | 测试 |

API workflow 不可覆盖 api_key、base_url、token_hard_limit。

---

## 9. DeepSeek Provider

支持双端点自动检测：

| 端点 | SDK | 特点 |
|------|-----|------|
| `api.deepseek.com/v1` | openai | function calling 结构化输出，**推荐** |
| `api.deepseek.com/anthropic` | anthropic | tool_use 结构化输出，ThinkingBlock 分离 |

> **注意**: DeepSeek Anthropic 端点当前不支持 `tool_choice` 参数，Director 的结构化输出必须使用 OpenAI 端点。

---

## 9.1 LLM 连接配置

### 环境变量

```powershell
# 必须：DeepSeek API Key
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxx"

# 可选：端点选择（默认 OpenAI /v1）
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"        # OpenAI 端点（推荐）
# $env:DEEPSEEK_BASE_URL = "https://api.deepseek.com/anthropic" # Anthropic 端点

# 可选：模型覆盖
$env:AWP_DIRECTOR_MODEL = "deepseek-v4-flash"
$env:AWP_WRITER_MODEL = "deepseek-v4-pro"
```

### ComfyUI 节点中使用

持久化节点通过 `director_profile_id` / `writer_profile_id` 选择模型：

```
fake-director / fake-writer          → 测试用，不调用 API
deepseek-v4-flash-director           → Director（Flash + 思考）
deepseek-v4-pro-writer               → Writer（Pro + 禁思考）
```

未知 profileId 会 fail closed（拒绝执行）。

### 快速验证

```powershell
# 1. 设置 API Key
$env:DEEPSEEK_API_KEY = "sk-xxx"

# 2. 测试基础文本生成
python -c "
import os
from openai import OpenAI
client = OpenAI(
    api_key=os.environ['DEEPSEEK_API_KEY'],
    base_url='https://api.deepseek.com/v1',
)
resp = client.chat.completions.create(
    model='deepseek-v4-flash', max_tokens=50,
    messages=[{'role': 'user', 'content': '你好'}],
)
print(resp.choices[0].message.content)
"
```

### 破限声明

Director 和 Writer 的 prompt 中自动追加虚构创作声明，以应对 DeepSeek 的 NSFW 限制。

---

## 10. D1～D6 Agent 总览

| Agent | 代号 | 职责 | 运行位置 | LLM 调用 |
|-------|------|------|----------|----------|
| D1 History/Recall | history-recall | 历史证据回查 | Wave A（Writer 前） | DeepSeek Flash |
| D2 Opportunity | opportunity | 戏剧机会识别 | Wave A（Writer 前） | DeepSeek Flash |
| D3 World-Life | world-life | 世界活性事件 | Wave A（Writer 前） | DeepSeek Flash |
| D4 Emotion/Relationship | emotion-relationship | 情绪与关系解读 | Wave A（Writer 前） | DeepSeek Flash |
| D5 Continuity | continuity | 连续性约束 | Wave B（Continuity Barrier 后） | DeepSeek Flash |
| D6 Memory Curator | memory-curator | accepted-turn 后记忆治理 | Post-Commit（Writer 后） | TurnEvolutionCurator |

子 Agent 工作方式：
1. 规则触发器决定"是否触发"（基于关键词/快照/世界书/NPC）
2. 触发后，每个 Agent 调一次 DeepSeek Flash（禁思考）
3. 产出 2-3 句具体分析，进入 Writer prompt 的 `accepted_guidance`
4. 每条截断 200 字，最多取前 8 条

---

## 11. 三层记忆

| 层级 | 内容 | 上限 | 描述 |
|------|------|------|------|
| L1 近忆窗口 | 最近 accepted TurnRecord | 5 条 | 完整回合记录 |
| L2 活跃记忆 | 剧情注意力卡片 | 15 条 | 30-80 字符 |
| L3 RAG 记忆 | 长期可搜索记忆 | 每轮 ≤10 条 | FTS5 + LIKE |

> **注意**: 当前记忆系统在真实 LLM 运行中全程 noop，需要强化 Curator prompt 或分离 D6 Memory Curator。

---

## 12. 管理面板

React SPA + REST API，ComfyUI 启动后访问 `http://localhost:8188/awp/`。

### API 端点

```
GET    /awp/api/v1/sessions                         -> 会话列表
POST   /awp/api/v1/sessions                         -> 从已有角色卡创建会话
GET    /awp/api/v1/sessions/{id}                    -> 会话详情
DELETE /awp/api/v1/sessions/{id}                    -> 删除会话及其持久化记录
GET    /awp/api/v1/sessions/{id}/turns              -> 回合历史
GET    /awp/api/v1/sessions/{id}/opening            -> 开场白
POST   /awp/api/v1/sessions/{id}/turn               -> 玩家输入回合
POST   /awp/api/v1/sessions/{id}/first-turn         -> 首回合
POST   /awp/api/v1/sessions/{id}/continue           -> AI 自走续写回合
GET    /awp/api/v1/cards                            -> 角色卡列表
POST   /awp/api/v1/cards/import                     -> 导入角色卡
GET    /awp/api/v1/cards/{card_id}/greetings        -> 角色卡开场白列表
DELETE /awp/api/v1/cards/{card_id}                  -> 删除角色卡及其会话
GET    /awp/api/v1/workflows                        -> 可用 API workflow
GET    /awp/api/v1/presets/writer                   -> Writer preset 列表
GET    /awp/api/v1/presets/writer/{name}            -> Writer preset 内容
GET    /awp/{tail:.*}                               -> SPA 静态文件
```

生成类端点支持双轨执行参数：

```
?mode=hybrid|python&workflow=<workflow_name>
```

- `AWP_EXECUTION_MODE=hybrid|python` 控制默认轨道，未设置时默认 `hybrid`。
- `hybrid` 轨道通过 ComfyUI API workflow 排队执行；`python` 轨道直接调用运行时节点类。
- 默认 workflow 映射：`turn -> send_turn`，`first_turn -> first_turn`，`continue -> continue_world`。

### 前端技术栈

- React + TypeScript
- Vite 构建
- Ant Design 组件库
- 页面：Sessions（会话列表/新建/删除）、SessionChat（开场白+历史回合/玩家输入/续写）、Cards（导入/删除/greetings 详情）
- SessionChat 提供高级工作流选择器，可在 `hybrid` 与 `python` 间切换并指定 API workflow。
- SessionChat 提供 Writer preset 查看器，便于确认当前 preset 内容和本地文件路径。

---

## 13. 测试

```bash
# 全部测试
python -m pytest tests/ -q
# 981 collected

# 快速试玩（绕过 ComfyUI，直接调用 persistent 节点）
python -m awp_rp_runtime_v2.testing.quick_playtest --card "<角色卡路径>.json" --turns 8

# 20 回合压力测试
python -m awp_rp_runtime_v2.testing.twenty_turn_test --card "<角色卡路径>.json"

# 线性调试工具
python -m awp_rp_runtime_v2.testing.linear_persistent_rp_debug \
    --card "<角色卡路径>.json" --greeting-id g1 --verbose

# 实机 E2E (需要 ComfyUI 运行)
python -m awp_rp_runtime_v2.testing.playable_e2e_test --turns 8

# 持久化验收
python -m awp_rp_runtime_v2.testing.real_comfy_persistence_acceptance --restart-after-turn --turns 3

# 真实 DeepSeek (需要 DEEPSEEK_API_KEY)
$env:AWP_REAL_LLM_E2E = "1"
$env:AWP_ALLOW_EXTERNAL_CARD_CONTENT = "1"
$env:AWP_REAL_CARD_PATH = "<path>"
python -m awp_rp_runtime_v2.testing.real_provider_multiturn_acceptance --card-path $env:AWP_REAL_CARD_PATH --turns 8

# 离线长会话测试（fake，无需 API Key）
python -m awp_rp_runtime_v2.testing.user_simulation_harness \
    --turns 10 --restart-after-turn 5 --save-artifacts
```

---

## 14. 项目结构

```
awp_rp_runtime_v2/
├─ contracts/          # 数据合同 (schema_id + schema_version)
├─ policies/           # 纯策略 (无 I/O)
├─ storage/            # 存储接口 + SQLite 实现 (10 stores)
├─ runtime/            # 运行时编排 (~115 文件)
│   ├─ persistent_turn_engine.py    # 主引擎
│   ├─ turn_evolution_curator.py    # LLM 驱动状态+记忆策展
│   ├─ sub_agent_llm_runner.py      # 子 Agent LLM 调用
│   ├─ management_api.py            # REST API + SPA 路由
│   ├─ dynamic_subagent_pool.py     # 动态子 Agent 池
│   ├─ dynamic_agent_scheduler.py   # Wave A/B 调度
│   └─ ...
├─ nodes/              # ComfyUI 节点 (114 个)
├─ adapters/           # 外部接口
│   ├─ llm/            # DeepSeek Anthropic/OpenAI 双端点
│   ├─ character_card.py
│   ├─ worldbook.py
│   └─ preset.py
├─ services/           # 业务服务层
│   ├─ card_state_service.py
│   ├─ memory_service.py
│   ├─ trace_service.py
│   └─ worldbook_service.py
├─ web/                # 管理面板前端 (React + Vite + Antd)
├─ testing/            # 验收测试 + E2E + 调试工具
├─ tests/              # 单元测试 (981 个)
├─ presets/             # Writer 预设
├─ workflows/          # ComfyUI 工作流 JSON (14 个)
│   ├─ api/            # API 工作流
│   └─ persistent_rp_*.json  # 持久化 RP 工作流
├─ test_fixtures/      # 测试夹具
├─ frontend/           # 前端资源
├─ scripts/            # 脚本工具
└─ docs/               # 文档
   ├─ handoffs/        # 阶段验收报告 (19 份)
   ├─ architecture/    # 架构文档 (12 份)
   ├─ decisions/       # 决策记录
   ├─ reference/       # 参考文档
   └─ testing/         # 测试文档
```

---

## 15. 环境要求

- Python ≥ 3.10
- pydantic ≥ 2.0
- openai ≥ 1.0 (DeepSeek OpenAI 端点)
- anthropic ≥ 0.100 (DeepSeek Anthropic 端点)
- pytest ≥ 7.0 (开发)
- Node.js ≥ 18 (管理面板前端构建)

---

## 16. 安装

```bash
git clone https://github.com/SDRTIO-bit/comfyui_awp_rp-v2.git
cd comfyui_awp_rp-v2
pip install -e ".[dev]"
```

作为 ComfyUI 插件：

```bash
cd /path/to/ComfyUI/custom_nodes/
ln -s /path/to/comfyui_awp_rp-v2 awp_rp_runtime_v2
```

管理面板前端构建（可选）：

```bash
cd web/
npm install
npm run build
```

---

## 17. 路线图

### 已完成里程碑

| 里程碑 | Tag | 测试 | 说明 |
|--------|-----|------|------|
| Card Import Normalization | `card-import-normalization-v1` | ~100 | 卡片导入规范化 |
| Card Session Bootstrap | `card-session-bootstrap-worldbook-binding-v1` | ~200 | 会话引导 + 世界书绑定 |
| D1 History Recall | `d1-history-recall-v1` | ~240 | 历史证据回查 Agent |
| D2 Opportunity | `d2-opportunity-agent-v1` | ~280 | 戏剧机会识别 Agent |
| D3 World-Life | `d3-world-life-agent-v1` | ~320 | 世界活性事件 Agent |
| D4 Emotion/Relationship | `d4-emotion-relationship-agent-v1` | ~400 | 情绪关系解读 Agent |
| D5 Continuity | `d5-continuity-agent-v1` | ~450 | 连续性约束 Agent |
| D6 Memory Curator | `d6-memory-curator-agent-v1` | ~500 | 记忆治理 Agent |
| D-Integration | `d-integration-dynamic-agent-conflict-governance-v1` | 566 | Wave 调度 + 冲突治理 |
| Observability | `observability-autonomous-harness-v1` | 680 | 自主测试框架 |
| CardSession Bootstrap | — | 711 | 确定性引导链 |
| First Turn Execution | `first-turn-execution-context-assembly-v1` | 764 | 首回合管线 |
| Real Provider | `real-provider-multiturn-playable-acceptance-v1` | 795 | DeepSeek 适配器 |
| Canonical Turn | — | 816 | TurnResultProbe + Continuation |
| Persistent Session | `persistent-session-roundsnapshot-integration-v1` | 831 | SQLite 会话存储 |
| Persistent E2E | — | 839 | 统一 Bootstrap/Turn1/Turn2+ |
| Idempotent Replay | `persistent-runtime-live-acceptance-idempotent-replay-v1` | 852 | 幂等重放 + 模型注册 |
| Playable Persistent | `playable-rp-runtime-persistent-v1` | 852 | 合入 main 的可玩里程碑 |
| Multi-Session | `comfy-multisession-long-context-acceptance-v1` | 960 | 多会话长上下文 |
| P1 Real RP Evolution | — | ~980 | TurnEvolutionCurator + 条件世界书 |
| P2 Management | `playable-rp-runtime-management-v1` | 981 | 管理面板 + 子 Agent LLM |

### 下一阶段

- **PromptCompiler V2**：L0/L1/L2/L3 分层缓存，提升 DeepSeek 前缀缓存命中率
- **子 Agent 接入**：DynamicSubAgentPool + Wave A/B + ToolGateway 真实接入
- **记忆系统修复**：强化 Curator prompt 或分离 D6 Memory Curator
- **Director 工具调用**：通过 ToolGateway 调用 worldbook/memory/timeline
- **缓存观测**：`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 记录
- **Chat Surface / Playable RP UI**：玩家直接交互界面
- **叙事质量与角色一致性**：长期优化目标

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/P2_HANDOFF.md](docs/P2_HANDOFF.md) | P2 管理面板 + 子 Agent LLM 交接 |
| [docs/P1_HANDOFF.md](docs/P1_HANDOFF.md) | P1 真实 RP 演化交接 |
| [docs/alpha-status-v0.1.md](docs/alpha-status-v0.1.md) | Alpha 状态报告 |
| [docs/handoffs/](docs/handoffs/) | 全部阶段验收报告（19 份） |
| [docs/architecture/](docs/architecture/) | 架构文档（12 份） |
| [docs/reference/](docs/reference/) | 参考文档 |
| [docs/decisions/](docs/decisions/) | 决策记录 |
| [docs/security.md](docs/security.md) | 安全文档 |
| [docs/contributing.md](docs/contributing.md) | 贡献指南 |
