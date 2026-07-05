# P-CardImport: Character Card Import & Normalization V1

**Date**: 2026-06-27
**Branch**: feat/card-import-normalization-v1
**HEAD**: e227f5e
**Tag**: card-import-normalization-v1, card-import-normalization-v1.1
**Tests**: 615 passed (570 existing + 45 new)

---

## 1. 导入格式支持范围

| 格式 | 支持 | 说明 |
|---|---|---|
| SillyTavern V3 JSON | ✅ | 直接 JSON 解析 |
| SillyTavern V3 PNG | ✅ | tEXt / zTXt / iTXt chunks，chara/ccv3/card/character keys |
| PNG base64 payload | ✅ | 自动 base64 解码 |
| 其他格式 | ❌ | 返回 `unsupported_format` 错误 |

## 2. 字段映射

### SillyTavern V3 → CardProfile

| ST V3 字段 | CardProfile 字段 |
|---|---|
| `data.name` | `name` |
| `data.description` | `description` |
| `data.personality` | `personality` |
| `data.scenario` | `scenario` |
| `data.mes_example` | `mes_example` |
| `data.creator_notes` / `data.creatorcomment` | `creator_notes` |
| `data.tags` | `tags` |
| `data.extensions` | `extensions_summary`（仅 tags/world/talkativeness） |

### SillyTavern V3 → CardGreeting

| ST V3 字段 | CardGreeting |
|---|---|
| `data.first_mes` | `g0`，is_default=True |
| `data.alternate_greetings[N]` | `g1`+，支持 string 或 {greeting, label} |

### SillyTavern V3 → CardWorldbookEntry

| ST V3 字段 | 保留方式 |
|---|---|
| `entries[N].keys` | `keys` |
| `entries[N].secondary_keys` | `secondary_keys` |
| `entries[N].priority` | `priority` |
| `entries[N].constant` | `constant` |
| `entries[N].selective` | `selective` |
| `entries[N].disable` / `entries[N].enabled` | `enabled = not disabled` |
| `entries[N].uid` | `source_uid` |
| `entries[N].comment` / `entries[N].name` | `title` |
| 其他 activation 字段 | `activation_raw` |

### 未支持字段策略

未支持的字段保留 `raw metadata` 引用，在 ImportReport 中标记 `unsupported` / `deferred` / `requires_manual_mapping`。

## 3. 安全扫描与隔离策略

### 检测类别

| 类别 | 严重性 | 动作 |
|---|---|---|
| `javascript` (new Function) | CRITICAL | quarantined |
| `eval` | CRITICAL | quarantined |
| `ejs` | HIGH | quarantined |
| `setvar` / `addvar` | HIGH | quarantined |
| `getvar` | MEDIUM | quarantined |
| `script_tag` | CRITICAL | quarantined |
| `iframe` | HIGH | quarantined |
| `fetch` | HIGH | quarantined |
| `import_url` | HIGH | quarantined |
| `regex_script` | MEDIUM | quarantined |
| `variable_exec` | MEDIUM | quarantined |

### Greeting 清理

- `{{setvar:}}` / `{{getvar:}}` / `{{addvar:}}` → stripped + quarantined
- EJS `<% %>` → stripped + quarantined
- `<script>` → stripped + quarantined
- `{{status_bar}}` → stripped + quarantined
- 过多换行 → normalized

### 隔离记录

每条隔离记录包含：`record_id`, `kind`, `source_path`, `severity`, `evidence_preview`, `action`, `reason`。

绝不执行、不忽略后静默注入 Prompt、不自动转为 CardState patch、不发起网络请求。

## 4. CardDefinition 与 CardState 边界

| 概念 | 定义 | 导入时行为 |
|---|---|---|
| CardDefinition | 静态、版本化角色卡资源包 | ✅ 创建 |
| CardState | session 运行时状态 | ❌ 不创建 |
| ActiveMemory | 活跃记忆 | ❌ 不创建 |
| RagMemory | RAG 记忆 | ❌ 不创建 |
| TurnRecord | 回合记录 | ❌ 不创建 |

## 5. 世界书拆分与切片规则

- 短条目（≤1000 字符）→ 不切片，保留原始 CardWorldbookEntry
- 长条目（>1000 字符）→ 产生 CardWorldbookChunk
- 切片参数：chunk_size=1000, overlap=100
- 切片在句子边界断开（`.。!！?？\n`）
- 每个 chunk 有 `parent_entryId` 双向追溯
- 切片确定性、可重复、不依赖 LLM
- `disabled` entry 保存但 `enabled=False`
- `constant` entry 是标志，不等于无预算全量注入

## 6. Staged / Ready / Rejected 状态规则

| 状态 | 含义 |
|---|---|
| `staged` | 已解析，未批准 |
| `ready` | 可被 CardSessionBootstrap 使用 |
| `rejected` | 导入失败或用户拒绝 |
| `superseded` | 存在更新版本 |

显式批准通过 `CardImportApproval(decision="approve")` 完成。批准旧版本时自动 supersede。

## 7. 版本与幂等规则（V1.1 修正）

### 身份模型

| 字段 | 含义 | 生成方式 |
|---|---|---|
| `logical_card_id` | 同一逻辑角色卡的稳定身份 | `lcid_{uuid.uuid4().hex[:16]}` |
| `card_version` | logical_card_id 下的递增版本号 | 1, 2, 3, ... |
| `source_hash` | 精确导入 payload 的内容哈希 | SHA-256 |

### 幂等规则

- 同一 `source_hash` 重复导入 → `ALREADY_EXISTS`，返回已有 `logical_card_id + card_version`
- 新建卡 → 新建 `logical_card_id`，`card_version = 1`
- 指定 `existing_logical_card_id` → 新版本，`card_version + 1`
- 同名但未指定 `existing_logical_card_id` → 新建独立 `logical_card_id`（不自动合并）
- 旧 ready 版本被新版本 approve 后自动 `superseded`
- 已有 session 不受影响

### 嵌套合同校验

CardDefinition.validate() 递归校验：
- CardProfile: schema_id, schema_version
- CardGreeting: schema_id, schema_version
- CardWorldbookEntry: schema_id, schema_version
- CardWorldbookChunk: schema_id, schema_version, parent_entry_id 引用完整性
- CardStructureHints: schema_id, schema_version

to_dict() / from_dict() 通过强类型合同序列化，不使用自由 dict 直接持久化。

后续 session 绑定 `logical_card_id + card_version`

## 8. ComfyUI 节点与官方 Workflow

### 节点列表

| 节点 | 显示名 | 功能 |
|---|---|---|
| AWPV2CardSourceLoad | 角色卡源读取 | 读取 JSON/PNG 文件 |
| AWPV2CardPayloadParse | 角色卡结构解析 | 解析 profile/greetings/worldbook/hints |
| AWPV2CardSecurityScan | 角色卡安全扫描 | 检测危险内容 |
| AWPV2CardNormalize | 角色卡规范化 | 清理 greetings、切片 worldbook、组装 CardDefinition |
| AWPV2CardImportReview | 角色卡导入审核 | 生成审核报告 |
| AWPV2CardImportApproval | 角色卡导入批准 | 显式 approve/reject |
| AWPV2CardDefinitionCommit | 角色卡定义提交 | 提交到存储 |
| AWPV2CardCatalogLookup | 角色卡目录查询 | 查询 CardDefinition |
| AWPV2CardImportDiagnostics | 角色卡导入诊断 | Markdown 诊断报告 |

### Workflow

`workflows/official_card_import_normalization_v1.json` — 9 节点流水线。

## 9. 测试命令与结果

```bash
python -m pytest tests/ -q
# 615 passed in 2.49s
```

### 新增测试覆盖

| # | 测试 | 状态 |
|---|---|---|
| 1 | 合法 V3 JSON 可导入 | ✅ |
| 2 | 合法 V3 PNG 可导入 | ✅ |
| 3 | 非 PNG 伪装被拒绝 | ✅ |
| 4 | PNG 无 metadata 被拒绝 | ✅ |
| 5 | 无 spec/data 被拒绝 | ✅ |
| 6 | 不支持 spec 不报错 | ✅ |
| 7 | 同 sourceHash 幂等 | ✅ |
| 8 | 同名不同 hash 新卡 | ✅ |
| 9 | 默认 Greeting 提取 | ✅ |
| 10 | 多 alternate greetings 顺序 | ✅ |
| 11 | setvar/EJS/script 隔离 | ✅ |
| 12 | Worldbook flags 保留 | ✅ |
| 13 | disabled entry 保存 | ✅ |
| 14 | constant ≠ 无限预算 | ✅ |
| 15 | 长条目切片可追溯 | ✅ |
| 16 | 短条目不切片 | ✅ |
| 17 | chunk 可回溯 parent | ✅ |
| 18 | JS/eval/fetch/iframe 隔离 | ✅ |
| 19 | 变量 → variableHints | ✅ |
| 20 | 阶段提示仅 metadata | ✅ |
| 21-25 | 导入不创建 Memory/State | ✅ |
| 26 | staged 不可用 | ✅ |
| 27 | approved 可查询 | ✅ |
| 28 | 报告不泄漏内容 | ✅ |
| 29 | 跨版本隔离 | ✅ |
| 30 | workflow JSON | ✅ |
| 31 | 已有合同不破坏 | ✅ |
| E2E A | 正常卡全流程 | ✅ |
| E2E B | 复杂卡全流程 | ✅ |
| 32 | 同 source_hash 幂等 logical_card_id | ✅ |
| 33 | 新卡 version=1 | ✅ |
| 34 | existing_logical_card_id version 递增 | ✅ |
| 35 | 新版本不破坏旧 session | ✅ |
| 36 | 同名不自动合并 | ✅ |
| 37 | 旧版本 superseded | ✅ |
| 38 | profile 校验 | ✅ |
| 39 | greeting schema 校验 | ✅ |
| 40 | worldbook entry schema 校验 | ✅ |
| 41 | chunk parent 引用校验 | ✅ |
| 42 | Store round-trip 类型正确 | ✅ |
| 43 | structure_hints schema 校验 | ✅ |

## 10. 已知限制

- PNG 仅支持 tEXt/zTXt/iTXt chunks
- Greeting 清理基于正则，不覆盖所有混淆
- 世界书 activation 语义未完全模拟 SillyTavern
- CatalogLookup 节点为桩实现（返回空）
- 无网络请求能力（设计如此）
- 无向量化 / Embedding（设计如此）

## 11. 下一阶段建议

**P-CardSession Bootstrap & Worldbook Binding V1**

- 用户选择 Greeting → OpeningRecord
- CardDefinition → CardState 初始化
- Worldbook 检索接入（budget-aware）
- 变量初始化映射
- Session 创建
