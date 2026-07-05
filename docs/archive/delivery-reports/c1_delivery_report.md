# C1: Dual Main Agent + Governed Tool Gateway V1 — Delivery Report

**日期:** 2026-06-27
**Branch:** master
**HEAD:** ceb2a04 (pre-C1)

---

## 1. 基线测试结果

P1–P3 + M1: **204 passed** (0 failed, 0 skipped)

## 2. C1 新增/修改文件

### 新增合同 (14 files)
| 文件 | schemaId | 用途 |
|------|----------|------|
| `contracts/director_plan.py` | `awp.rp.director-plan.v1` | Director 结构化输出 |
| `contracts/tool_plan.py` | `awp.rp.tool-plan.v1` | 工具调用计划 |
| `contracts/tool_request.py` | `awp.rp.tool-request.v1` | 验证后的工具请求 |
| `contracts/tool_result.py` | `awp.rp.tool-result.v1` | 单个工具执行结果 |
| `contracts/tool_result_bundle.py` | `awp.rp.tool-result-bundle.v1` | 工具结果聚合 |
| `contracts/tool_permission.py` | `awp.rp.tool-permission.v1` | 权限检查结果 |
| `contracts/tool_execution_receipt.py` | `awp.rp.tool-execution-receipt.v1` | 审计收据 |
| `contracts/enrichment_bundle.py` | `awp.rp.enrichment-bundle.v1` | 丰富合并结果 |
| `contracts/final_turn_brief.py` | `awp.rp.final-turn-brief.v1` | 最终回合简报 |
| `contracts/writer_draft.py` | `awp.rp.writer-draft.v1` | Writer 输出草稿 |
| `contracts/quality_issue.py` | `awp.rp.quality-issue.v1` | 结构化质量问题 |
| `contracts/quality_gate_result.py` | `awp.rp.quality-gate-result.v1` | 单个 Gate 结果 |
| `contracts/revision_request.py` | `awp.rp.revision-request.v1` | 修订请求 |
| `contracts/revision_result.py` | `awp.rp.revision-result.v1` | 修订结果 |

### 修改合同 (1 file)
| 文件 | 变更 |
|------|------|
| `contracts/writer_input_bundle.py` | 增加 FinalTurnBrief、style/format/budget contract 字段，保持 P2 向后兼容 |

### 新增 Runtime (12 files)
| 文件 | 用途 |
|------|------|
| `runtime/tool_registry.py` | 显式工具注册表 |
| `runtime/tool_permission_policy.py` | 统一权限检查 |
| `runtime/tool_budget_runtime.py` | 预算和超时执行 |
| `runtime/tool_result_validator.py` | 工具结果验证 |
| `runtime/tool_gateway.py` | 统一工具网关 |
| `runtime/enrichment_merger.py` | 工具结果丰富合并 |
| `runtime/final_turn_brief_runtime.py` | 最终简报生成 |
| `runtime/director_v2_runtime.py` | Director V2 运行时 |
| `runtime/writer_v2_runtime.py` | Writer V2 运行时 |
| `runtime/reviser_runtime.py` | Reviser 运行时 |
| `runtime/quality_pipeline_runtime.py` | 质量检查流水线 |
| `runtime/writer_input_bundle_v2_builder.py` | WriterInputBundle V2 构建器 |

### 新增 LLM Adapters (6 files)
| 文件 | 用途 |
|------|------|
| `adapters/llm/__init__.py` | 模块导出 |
| `adapters/llm/base.py` | 抽象基类 |
| `adapters/llm/fake.py` | 测试用 Fake 适配器 |
| `adapters/llm/openai_compatible.py` | OpenAI 兼容适配器 |
| `adapters/llm/structured_output.py` | 结构化输出工具 |
| `adapters/llm/provider_config.py` | 提供者配置 |

### 新增 ComfyUI 节点 (11 files)
| 节点 | 显示名称 |
|------|----------|
| `AWPV2DirectorPlan` | AWP V2 Director规划 |
| `AWPV2ToolPlan` | AWP V2 工具计划 |
| `AWPV2ToolGateway` | AWP V2 工具网关 |
| `AWPV2EnrichmentMerge` | AWP V2 丰富合并 |
| `AWPV2FinalTurnBrief` | AWP V2 最终回合简报 |
| `AWPV2WriterV2` | AWP V2 写作节点V2 |
| `AWPV2WriterInputBundleV2` | AWP V2 Writer输入包V2 |
| `AWPV2QualityPipeline` | AWP V2 质量检查流水线 |
| `AWPV2Reviser` | AWP V2 修订器 |
| `AWPV2WriterOutput` | AWP V2 Writer输出 |
| `AWPV2ToolTrace` | AWP V2 工具追踪 |

### 新增测试 (2 files)
| 文件 | 测试数 |
|------|--------|
| `tests/test_c1_dual_main_tool_gateway.py` | 32 tests (Tests 1-26) |
| `tests/test_c1_e2e.py` | 2 tests (happy path + failure path) |

### 新增工作流 (1 file)
| 文件 | 用途 |
|------|------|
| `workflows/official_dual_main_tool_gateway_v2.json` | 官方双主Agent工作流 |

---

## 3. Director / Writer / Reviser 职责矩阵

| 能力 | Director | Writer | Reviser |
|------|----------|--------|---------|
| 读取 RoundSnapshot | ✅ | ❌ (只读 WriterInputBundle) | ❌ |
| 生成 DirectorPlan | ✅ | ❌ | ❌ |
| 生成 ToolPlan | ✅ | ❌ | ❌ |
| 生成 DelegationPlan | ✅ (C1 不执行) | ❌ | ❌ |
| 生成 FinalTurnBrief | ✅ | ❌ | ❌ |
| 调用工具 | ❌ (通过 ToolGateway) | ❌ | ❌ |
| 生成玩家正文 | ❌ | ✅ | ✅ (修订) |
| 写 CardState | ❌ | ❌ | ❌ |
| 写 TurnRecord | ❌ | ❌ | ❌ |
| 写 Memory | ❌ | ❌ | ❌ |
| 输出 JSON/调试 | ❌ | ❌ | ❌ |
| 最大修订次数 | N/A | N/A | 1 (最大 2) |

---

## 4. ToolRegistry 与权限矩阵

### V1 注册工具
| toolId | 副作用 | 写状态 | 写内存 | 委派 | 默认超时 |
|--------|--------|--------|--------|------|----------|
| `worldbook_lookup` | 无 | ❌ | ❌ | ❌ | 30s |
| `rag_memory_lookup` | 无 | ❌ | ❌ | ❌ | 30s |
| `entity_alias_lookup` | 无 | ❌ | ❌ | ❌ | 30s |
| `timeline_lookup` | 无 | ❌ | ❌ | ❌ | 30s |
| `relationship_context_lookup` | 无 | ❌ | ❌ | ❌ | 30s |

### 权限策略
- **默认拒绝**: 未注册工具一律拒绝
- **显式 allowlist**: 只有 V1_ALLOWED_TOOLS 中的工具可执行
- **副作用检查**: side_effect_free=True 才允许
- **范围隔离**: cardId + sessionId 约束
- **输入过滤**: 阻止 env/file/http/import 等模式

---

## 5. ToolBudget / Timeout / 失败降级规则

| 约束 | 默认值 | 检查点 |
|------|--------|--------|
| max_request_count | 5 | Plan 验证 |
| max_parallelism | 1 | Plan 验证 (V1 顺序执行) |
| total_token_budget | 5000 | Plan 验证 + 执行跟踪 |
| total_time_budget_ms | 60000 | Plan 验证 + 执行跟踪 |
| 单请求 timeout | 30000ms | 执行时检查 |

### 失败降级
- **optional 工具失败** → 状态设为 `degraded` → Director 继续生成 FinalTurnBrief
- **required 工具失败** → 状态设为 `failed` → 记录 failure_reason → Writer 不假设结果存在
- **预算超限** → 状态设为 `budget_exceeded` → 跳过后续请求

---

## 6. Tool Result 进入/被拒绝进入 FinalTurnBrief

```
ToolResult → ToolResultValidator → EnrichmentMerger → FinalTurnBrief
```

- 成功结果 + 有效 sourceRefs → accepted_items → accepted_tool_findings
- 失败结果 或 无效 sourceRefs → rejected_items → rejected_tool_findings
- 降级结果 → degraded_items → accepted (带标记)
- Tool Result 与 CardState 冲突 → 被拒绝 (由 Director 决定)

---

## 7. Quality Pipeline 规则与 revise/reject 语义

### Gate 列表
| Gate | 检查内容 | 错误级别 |
|------|----------|----------|
| IdentityGate | 角色名称一致性 | WARNING |
| SceneGate | 场景位置一致性 | WARNING |
| LengthGate | 最小/最大长度 | ERROR/WARNING |
| FormatGate | JSON泄露、调试标记、工具调用文本 | ERROR |

### 聚合规则
- 任何 ERROR → `revise`
- 仅 WARNING → `revise`
- 无问题 → `accept`

### 修订语义
- `revise` → 允许 Reviser 修订 (最大 1 次，可配置，上限 2)
- 修订后仍不通过 → `reject`
- `reject` → 零副作用 (不写 CardState/TurnRecord/Memory)

---

## 8. 真实 LLM Adapter 启用方式与安全边界

### 启用方式
```bash
# 设置环境变量
export AWP_LLM_API_KEY="your-api-key"
export AWP_LLM_BASE_URL="https://api.openai.com/v1"

# Director/Writer/Reviser 可使用不同配置
export AWP_DIRECTOR_API_KEY="..."
export AWP_WRITER_API_KEY="..."
export AWP_REVISER_API_KEY="..."
```

### 安全边界
- API Key **永不**写入代码、Trace、数据库、工作流 JSON
- `ProviderConfig.to_safe_dict()` 排除所有敏感值
- 真实 LLM 调用可通过环境变量关闭 (不设置 key = 不可用)
- Structured Output 失败时显式报错，不默默降级
- Smoke test 标记为 opt-in，不作为普通 CI 必跑测试

---

## 9. ComfyUI 节点输入输出与官方工作流

### 节点图数据流
```
CardStateInit → RoundSnapshot → DirectorPlan → ToolPlan → ToolGateway
→ EnrichmentMerge → FinalTurnBrief → WriterInputBundleV2 → WriterV2
→ QualityPipeline → [Reviser (条件)] → StateUpdateProposal
→ CardStateCommit → TurnRecordCommit → ActiveMemoryCommit / RagMemoryCommit
→ WriterOutput / ToolTrace
```

### 官方工作流
`workflows/official_dual_main_tool_gateway_v2.json` 包含 18 个节点、25 条连接、5 个分组。

---

## 10. 测试结果

```
============================= 238 passed in 1.74s ==============================
```

| 测试集 | 数量 | 状态 |
|--------|------|------|
| P1 tests | 52 | ✅ 全部通过 |
| P2 tests | 50 | ✅ 全部通过 |
| M1 tests | 10+ | ✅ 全部通过 |
| 其他 (contract/policy/runtime/storage/integration) | 92 | ✅ 全部通过 |
| **C1 tests** | **34** | **✅ 全部通过** |
| **总计** | **238** | **✅ 全部通过** |

---

## 11. 是否存在绕过路径

| 绕过风险 | 状态 |
|----------|------|
| 绕过 ToolGateway 直接调用工具 | ❌ 不存在 — 所有工具调用必须经过 ToolGateway |
| 绕过 QualityGate 进入 Commit | ❌ 不存在 — `assert_side_effects_allowed()` 强制检查 |
| Writer 访问 Store | ❌ 不存在 — WriterV2Runtime 无 Store 引用 |
| Writer 调用 ToolGateway | ❌ 不存在 — WriterV2Runtime 无 Gateway 引用 |
| Reviser 修改事实约束 | ❌ 不存在 — Reviser 只修订文本，不修改 Bundle |
| 动态子 Agent 成为主路径依赖 | ❌ 不存在 — DelegationPlan 默认为空，C1 不执行 |

---

## 12. 进入 D1 条件

C1 完成以下能力，可以进入 D1：History / Recall Agent：

- ✅ Director 与 Writer 基于同一 RoundSnapshot
- ✅ Director 不直接生成玩家正文
- ✅ Writer 只读 WriterInputBundle
- ✅ 所有工具调用经过 ToolGateway
- ✅ 工具有权限、预算、超时、结果摘要、Trace、失败降级
- ✅ Writer 输出经过 Quality Pipeline
- ✅ Reviser 有最大修订次数限制
- ✅ reject 时零副作用
- ✅ Fake 模式完整测试
- ✅ 真实 LLM Adapter 接口就绪 (opt-in)
- ✅ 官方工作流 JSON 结构校验通过
- ✅ 所有 238 个测试通过
