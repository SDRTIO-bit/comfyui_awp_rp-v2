# Public Alpha Release Hygiene & Repository Documentation V1

**Date:** 2026-06-27
**Branch:** main
**HEAD:** 7228160
**Tag:** v0.1.0-alpha
**Tests:** 566 passed in 2.28s (0 failed, 0 skipped)
**Working Tree:** clean (post-merge)

---

## 1. 启动核验结果

| 检查项 | 结果 |
|--------|------|
| 分支基于包含 D1～D6 + D-Integration 的最新 origin/main | ✅ main @ 8c1fe69 |
| D1～D6 + D-Integration tags 全部存在 | ✅ d1-history-recall-v1 … d-integration-dynamic-agent-conflict-governance-v1 |
| 工作树干净 | ✅ (pre-branch, clean) |
| 全部测试通过 | ✅ 566 passed in 2.10s |
| 仓库类型判定 | B — 以 ComfyUI 节点与 Runtime 为目标的架构/原型仓库 |

---

## 2. Public Alpha 真实定位

**版本：** `v0.1.0-alpha`

这是一个 **ComfyUI RP Runtime V2 的 Alpha 架构实现**。

### 已完成

- 确定性 CardState（SQLite + 事务提交 + revision + patchId + 幂等）
- 三层记忆系统（L1 近忆窗口 + L2 活跃记忆 + L3 RAG）
- 双主 Agent 的职责边界（Director / Writer）
- D1～D5 Writer 前受控动态 Agent（Wave A / Wave B）
- D6 accepted-turn 后记忆治理
- 动态 Agent 调度、预算、冲突治理、降级、Trace
- ComfyUI 节点与官方 workflow JSON
- Fake Adapter 集成测试（566 测试全部通过）

### 尚未承诺

- 生产级真实模型接入体验
- 一键安装即玩的完整 RP 产品
- 完整前端 UI
- 自动世界事件系统
- 无限制多 Agent 自主协作
- 稳定的第三方插件生态兼容性

---

## 3. README 与文档新增/修改清单

### 修改文件 (2)

| 文件 | 修改内容 |
|------|----------|
| `.gitignore` | 新增安全模式（secrets, logs, caches, env, venv, OS files） |
| `README.md` | 完整重写：中文为主，17 个章节，准确描述能力边界 |

### 新增文件 (9)

| 文件 | 内容 |
|------|------|
| `docs/architecture/overview-v1.md` | 系统总览：项目目标、双主 Agent、确定性状态、三层记忆、受控动态 Agent |
| `docs/architecture/turn-lifecycle-v1.md` | 完整回合生命周期：Wave A/B、Continuity Barrier、D6 位置、retry/idempotency |
| `docs/architecture/agent-boundaries-v1.md` | D1～D6 权限边界表：职责、输入、输出、工具、降级 |
| `docs/architecture/memory-governance-v1.md` | 记忆治理：三层记忆、accepted-only、D6 触发、幂等、保留优先级 |
| `docs/architecture/conflict-governance-v1.md` | 冲突治理：证据优先级、玩家代理权、事实泄漏防护、resolution 类型 |
| `docs/alpha-status-v0.1.md` | Alpha 状态报告：已完成能力、Fake Adapter 覆盖、已知限制 |
| `docs/contributing.md` | 贡献指南：最小流程、schema 兼容、权限声明、安全检查 |
| `docs/security.md` | 安全政策：敏感信息禁止、Fake Adapter 默认、报告流程 |
| `docs/reference/README.md` | 参考文档索引：原始架构记录 + 架构文档体系 + handoff 列表 |

### 移动文件 (1)

| 文件 | 变更 |
|------|------|
| `docs/RP_ComfyUI_双主Agent_记忆与动态子Agent_架构记录_v0.1.md` | → `docs/reference/RP_ComfyUI_双主Agent_记忆与动态子Agent_架构记录_v0.1.md` |

---

## 4. D1～D6 与 D-Integration 在公开文档中的表达方式

| Agent | README 描述位置 | 架构文档 |
|-------|----------------|----------|
| D1 History/Recall | Agent 总览表 + 执行拓扑 | agent-boundaries-v1.md |
| D2 Opportunity | Agent 总览表 + 执行拓扑 | agent-boundaries-v1.md |
| D3 World-Life | Agent 总览表 + 执行拓扑 | agent-boundaries-v1.md |
| D4 Emotion/Relationship | Agent 总览表 + 执行拓扑 | agent-boundaries-v1.md |
| D5 Continuity | Agent 总览表 + 执行拓扑（Wave B） | agent-boundaries-v1.md |
| D6 Memory Curator | Agent 总览表 + 执行拓扑（Post-Commit） | agent-boundaries-v1.md |
| D-Integration | 执行拓扑 + 安全边界 | conflict-governance-v1.md + turn-lifecycle-v1.md |

---

## 5. 工作流与节点说明

### 官方 Workflow (11)

| 文件 | 用途 | 类型 |
|------|------|------|
| `official_stateful_turn_v2.json` | 完整有状态回合流程 | 示例工作流 |
| `official_director_delegation_v2.json` | Director 委派流程 | 示例工作流 |
| `official_memory_runtime_v2.json` | 记忆运行时流程 | 示例工作流 |
| `official_dual_main_tool_gateway_v2.json` | 双主 Agent + 工具网关 | 示例工作流 |
| `official_history_recall_agent_v2.json` | D1 历史回查 Agent | 观察工作流 |
| `official_opportunity_agent_v2.json` | D2 戏剧机会 Agent | 观察工作流 |
| `official_world_life_agent_v2.json` | D3 世界活性 Agent | 观察工作流 |
| `official_continuity_agent_v2.json` | D5 连续性 Agent | 观察工作流 |
| `official_emotion_relationship_agent_v2.json` | D4 情绪关系 Agent | 观察工作流 |
| `official_memory_curator_agent_v2.json` | D6 记忆治理 Agent | 观察工作流 |
| `official_dynamic_agent_integration_v1.json` | 完整动态 Agent 集成 | 观察工作流 |

> 工作流 JSON 已完成结构校验，但普通用户尚不能一键打开并获得真实模型 RP 体验。

---

## 6. 依赖、安装、测试方式

### 依赖

- Python ≥ 3.10
- pydantic ≥ 2.0
- pytest ≥ 7.0（开发）
- pytest-asyncio ≥ 0.21（开发）

### 安装

```bash
git clone https://github.com/SDRTIO-bit/comfyui_awp_rp-v2.git
cd comfyui_awp_rp-v2
pip install -e ".[dev]"
```

### 测试

```bash
python -m pytest tests/ -q
```

**真实结果：566 passed in 2.28s**

---

## 7. 敏感信息扫描结论

### 扫描命令

```bash
git grep -nI -E "(sk-[A-Za-z0-9_-]{10,}|api[_-]?key|secret|password|authorization: bearer|anthropic[_-]?auth|openai[_-]?api)" -- . || true
git ls-files | grep -E "(^|/)(\.env|.*\.db|.*\.sqlite|.*\.sqlite3|.*\.log)$" || true
```

### 扫描结果

- **密钥扫描**：未发现真实密钥。所有 `api_key` 引用均为环境变量名（如 `AWP_LLM_API_KEY`）或领域概念（如 `secret` 作为记忆类型）。`docs/c1_delivery_report.md` 中的 `export AWP_LLM_API_KEY="your-api-key"` 为占位符示例。
- **敏感文件扫描**：未发现被 git 追踪的 `.env`、`.db`、`.sqlite`、`.sqlite3`、`.log` 文件。

---

## 8. `.gitignore` 变更

新增模式：

```gitignore
# Secrets and local environment
.env
.env.*
!.env.example

# Virtual environments
.venv/
venv/
env/

# Logs and traces
*.log
logs/
traces/

# Test / coverage / type-checker caches
.coverage
.coverage.*
coverage/
htmlcov/
.mypy_cache/
.pyre/
.ruff_cache/

# Jupyter / OS
.ipynb_checkpoints/
.DS_Store
Thumbs.db

# SQLite sidecar files
*.db-journal
*.sqlite-journal
*.sqlite3
```

保留原有：`__pycache__/`、`*.pyc`、`*.db`、`*.sqlite`、`.pytest_cache/`、`.claude/`

---

## 9. 原始架构文档是否入库

**是。** 原始架构文档 `RP_ComfyUI_双主Agent_记忆与动态子Agent_架构记录_v0.1.md` 已存在于仓库 `docs/` 根目录，已移入 `docs/reference/` 目录，保留原始标题、版本、日期与内容，未擅自扩写、改写或伪造作者意图。

---

## 10. License 状态

**License 尚未确定。** 仓库无 LICENSE 文件。README 中明确标记："License 尚未确定；除非另有明确授权，代码版权归项目作者所有。" `docs/alpha-status-v0.1.md` 中记录了该公开项目治理缺口。

---

## 11. 测试命令、通过数、跳过数、失败数

| 项目 | 结果 |
|------|------|
| 测试命令 | `python -m pytest tests/ -q` |
| 通过数 | 566 |
| 跳过数 | 0 |
| 失败数 | 0 |
| 耗时 | 2.28s |

---

## 12. 是否成功创建并推送 Alpha tag

**是。**

- Tag: `v0.1.0-alpha`
- HEAD: `7228160`
- 已推送到 `origin/main` 和 `origin/v0.1.0-alpha`

---

## 13. 下一阶段建议

1. **真实 LLM Adapter 接入**：实现 OpenAICompatibleAdapter 的真实调用，验证 Agent 在真实模型下的行为
2. **ComfyUI 安装验证**：验证仓库可作为 ComfyUI 插件直接安装并加载节点
3. **前端可观测性**：Agent 执行状态、记忆系统、冲突 resolution 的可视化
4. **Wave A 并发执行**：DynamicSubAgentPool 的真正并发支持
5. **产品化集成**：真实角色卡、世界书、预设的加载与管理

---

## 14. 禁止回归的架构约束（确认）

1. CardState 只能通过 CardStateCommitRuntime 写入 ✅
2. TurnRecord 只能通过 TurnRecordCommitRuntime 写入 ✅
3. ActiveMemory / RagMemory 只能通过各自的 CommitRuntime 写入 ✅
4. D6 永远不在 Writer 前 DynamicSubAgentPool 中 ✅
5. Writer 只能读取 WriterInputBundle，不能读取原始 Agent 输出 ✅
6. QualityGate reject = zero side effects ✅
7. 所有 Agent 只读、不可委托、不可写状态/记忆 ✅
8. 每个 Agent 有 no-op 路径 ✅

本阶段未修改任何运行时行为。
